#!/usr/bin/env python3
"""Sync episode retrospect logs, repo metadata, and publish-report.html to Google Drive.

Uploads only small text/JSON/HTML files (never video, FIT, images, or .pid) into:
  <Drive root>/running-retrospect/
    INDEX.md
    <YYYY-MM-DD-slug>/
      logs/
      episode-repo/
      publish-report.html

Idempotent: existing files with the same name are updated in place (no duplicates).
Merges existing remote INDEX.md / Drive episode folders when rebuilding INDEX.md so
historical episodes archived off the local Mac are never erased.
"""

from __future__ import annotations

import argparse
import io
import mimetypes
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _google_common import (  # noqa: E402
    DEFAULT_LOCAL_TOKEN,
    FOLDER_MIME,
    drive_download_bytes,
    drive_find_child,
    drive_list_children_map,
    load_drive_service,
)

DEFAULT_TOKEN = DEFAULT_LOCAL_TOKEN
DEFAULT_MEDIA_ROOT = Path("~/Movies/running-content").expanduser()
DEFAULT_DRIVE_ROOT = "running-retrospect"
SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB guard: text/json/html logs only
ALLOWED_SUFFIXES = {".txt", ".md", ".json", ".log", ".html", ".csv", ".yaml", ".yml"}
REPO_FILES = ("episode.md", "plan.md", "assets.md")
SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def ensure_folder(drive, parent_id: str | None, name: str) -> str:
    found = drive_find_child(
        drive,
        parent_id,
        name,
        mime_type=FOLDER_MIME,
        root_only=(parent_id is None),
    )
    if found:
        return found["id"]
    body: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]
    created = drive.files().create(body=body, fields="id").execute()
    return created["id"]


def upsert_file(
    drive,
    parent_id: str,
    existing: dict[str, dict[str, Any]],
    local_path: Path,
    name: str | None = None,
) -> str:
    target_name = name or local_path.name
    mime = mimetypes.guess_type(target_name)[0] or "text/plain"
    if target_name.endswith(".md"):
        mime = "text/markdown"
    elif target_name.endswith(".json"):
        mime = "application/json"
    elif target_name.endswith(".html"):
        mime = "text/html"
    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=False)
    if target_name in existing:
        fid = existing[target_name]["id"]
        drive.files().update(fileId=fid, media_body=media, fields="id").execute()
        return fid
    created = drive.files().create(
        body={"name": target_name, "parents": [parent_id]},
        media_body=media,
        fields="id",
    ).execute()
    existing[target_name] = {"id": created["id"], "name": target_name}
    return created["id"]


def upsert_text(
    drive,
    parent_id: str,
    existing: dict[str, dict[str, Any]],
    name: str,
    text: str,
    mime: str = "text/markdown",
) -> str:
    media = MediaIoBaseUpload(io.BytesIO(text.encode("utf-8")), mimetype=mime, resumable=False)
    if name in existing:
        fid = existing[name]["id"]
        drive.files().update(fileId=fid, media_body=media, fields="id").execute()
        return fid
    created = drive.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id",
    ).execute()
    existing[name] = {"id": created["id"], "name": name}
    return created["id"]


def eligible_log_files(logs_dir: Path) -> list[Path]:
    if not logs_dir.is_dir():
        return []
    result: list[Path] = []
    for p in sorted(logs_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith(".") or p.suffix.lower() == ".pid":
            continue
        if p.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        result.append(p)
    return result


def parse_episode_summary(episode_dir: Path, slug: str) -> dict[str, str]:
    ep_file = episode_dir / "episode.md"
    info = {"slug": slug, "title": slug, "status": "unknown", "youtube": "", "bilibili": "", "douyin": ""}
    if not ep_file.is_file():
        return info
    text = ep_file.read_text(encoding="utf-8")
    for key in ("title", "status"):
        m = re.search(rf"^{key}:\s*(.+)$", text, flags=re.MULTILINE)
        if m:
            info[key] = m.group(1).strip().strip('"').strip("'")
    for label, field in (("YouTube", "youtube"), ("Bilibili", "bilibili"), ("抖音", "douyin")):
        m = re.search(rf"^-\s*{label}[：:]\s*(\S+)", text, flags=re.MULTILINE)
        if m:
            info[field] = m.group(1).strip()
    return info


def _split_md_row(line: str) -> list[str]:
    """Split a Markdown table row while preserving escaped pipes (`\\|`)."""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", inner)]


def parse_index_md(text: str) -> dict[str, dict[str, Any]]:
    """Parse existing INDEX.md rows into slug -> record dicts so archived episodes stay preserved."""
    out: dict[str, dict[str, Any]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = _split_md_row(line)
        if len(cells) < 8:
            continue
        slug = cells[0].strip("` ")
        if not SLUG_RE.match(slug):
            continue
        logs_col = cells[5]
        repo_col = cells[6]
        out[slug] = {
            "slug": slug,
            "title": cells[1],
            "status": cells[2].strip("` "),
            "bilibili": "" if cells[3] == "-" else cells[3],
            "youtube": "" if cells[4] == "-" else cells[4],
            "logs_display": logs_col,
            "repo_files": [] if repo_col in ("", "missing") else [x.strip() for x in repo_col.split(",") if x.strip()],
            "has_report": cells[7].lower() == "yes",
        }
    return out


def merge_index_records(
    *,
    synced: list[dict[str, Any]],
    local_only: list[dict[str, Any]],
    remote_index: dict[str, dict[str, Any]],
    remote_folders: dict[str, dict[str, Any]] | None = None,
    episodes_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Merge freshly synced, local-present, and archived-remote episodes without dropping history.

    Priority (highest wins): synced > local_only > remote_index > remote_folders.
    For remote-only (archived) episodes, title/status/links are refreshed from git repo
    `episodes/<slug>/episode.md` if present, while preserving remote logs/report columns.
    """
    by_slug: dict[str, dict[str, Any]] = {}

    if remote_folders:
        for slug, rec in remote_folders.items():
            by_slug[slug] = dict(rec)

    for slug, rec in remote_index.items():
        merged = dict(rec)
        if episodes_root is not None:
            ep_dir = episodes_root / slug
            if (ep_dir / "episode.md").is_file():
                fresh = parse_episode_summary(ep_dir, slug)
                for k in ("title", "status", "bilibili", "youtube"):
                    if fresh.get(k):
                        merged[k] = fresh[k]
        by_slug[slug] = merged

    for rec in local_only:
        by_slug[rec["slug"]] = rec

    for rec in synced:
        by_slug[rec["slug"]] = rec

    return list(by_slug.values())


def inspect_remote_episode(drive, folder_id: str, slug: str, episodes_root: Path) -> dict[str, Any]:
    """Inspect a remote Drive episode folder when it was missing from INDEX.md."""
    children = drive_list_children_map(drive, folder_id)
    logs_files: list[str] = []
    if "logs" in children and children["logs"].get("mimeType") == FOLDER_MIME:
        logs_files = sorted(drive_list_children_map(drive, children["logs"]["id"]).keys())
    repo_files: list[str] = []
    if "episode-repo" in children and children["episode-repo"].get("mimeType") == FOLDER_MIME:
        repo_files = sorted(drive_list_children_map(drive, children["episode-repo"]["id"]).keys())
    return {
        **parse_episode_summary(episodes_root / slug, slug),
        "logs_files": logs_files,
        "repo_files": repo_files,
        "has_report": "publish-report.html" in children,
    }


def sync_episode(
    drive,
    root_id: str,
    media_dir: Path,
    episode_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    slug = media_dir.name
    summary = parse_episode_summary(episode_dir, slug)
    log_files = eligible_log_files(media_dir / "logs")
    repo_files = [episode_dir / name for name in REPO_FILES if (episode_dir / name).is_file()]
    report_file = media_dir / "publish-report.html"
    has_report = report_file.is_file()

    if not dry_run:
        ep_folder_id = ensure_folder(drive, root_id, slug)
        ep_existing = drive_list_children_map(drive, ep_folder_id)

        if log_files:
            logs_folder_id = ensure_folder(drive, ep_folder_id, "logs")
            logs_existing = drive_list_children_map(drive, logs_folder_id)
            for lf in log_files:
                upsert_file(drive, logs_folder_id, logs_existing, lf)

        if repo_files:
            repo_folder_id = ensure_folder(drive, ep_folder_id, "episode-repo")
            repo_existing = drive_list_children_map(drive, repo_folder_id)
            for rf in repo_files:
                upsert_file(drive, repo_folder_id, repo_existing, rf)

        if has_report:
            upsert_file(drive, ep_folder_id, ep_existing, report_file)

    record = {
        **summary,
        "logs_files": [f.name for f in log_files],
        "repo_files": [f.name for f in repo_files],
        "has_report": has_report,
    }
    print(
        f"[{'DRY' if dry_run else 'OK'}] {slug}: logs={len(log_files)} repo={len(repo_files)} report={'yes' if has_report else 'no'}",
        flush=True,
    )
    return record


def render_index(records: list[dict[str, Any]]) -> str:
    now_str = datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S +08:00")
    lines = [
        "# Running Retrospect Index",
        "",
        f"最后同步：{now_str}",
        "",
        "| Slug | 标题 | 状态 | Bilibili | YouTube | logs | episode-repo | publish-report.html |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(records, key=lambda x: x["slug"], reverse=True):
        bili = r.get("bilibili") or "-"
        yt = r.get("youtube") or "-"
        if "logs_files" in r:
            logs_col = f"{len(r['logs_files'])} files" if r["logs_files"] else "missing"
        else:
            logs_col = r.get("logs_display") or "missing"
        repo_col = ", ".join(r.get("repo_files") or []) or "missing"
        rep_col = "yes" if r.get("has_report") else "no"
        title = str(r.get("title") or r["slug"]).replace("|", "\\|")
        lines.append(
            f"| `{r['slug']}` | {title} | `{r.get('status', 'unknown')}` | {bili} | {yt} | {logs_col} | {repo_col} | {rep_col} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync running episode retrospect logs and reports to Google Drive")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--media-dir", help="Single episode media directory, e.g. ~/Movies/running-content/2026-11-24-lsd-short")
    group.add_argument("--all", action="store_true", help="Sync all YYYY-MM-DD-* directories under --media-root")
    parser.add_argument("--media-root", default=str(DEFAULT_MEDIA_ROOT))
    parser.add_argument("--episodes-root", default="episodes")
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--token-file", default=str(DEFAULT_TOKEN))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    episodes_root = Path(args.episodes_root).expanduser().resolve()
    if args.all:
        media_root = Path(args.media_root).expanduser().resolve()
        targets = sorted(
            p for p in media_root.iterdir()
            if p.is_dir() and SLUG_RE.match(p.name)
        )
    else:
        targets = [Path(args.media_dir).expanduser().resolve()]

    if not targets:
        raise SystemExit("No episode media directories found to sync.")

    drive = None if args.dry_run else load_drive_service(Path(args.token_file).expanduser())
    root_id = "" if args.dry_run else ensure_folder(drive, None, args.drive_root)

    synced_records: list[dict[str, Any]] = []
    for media_dir in targets:
        ep_dir = episodes_root / media_dir.name
        synced_records.append(sync_episode(drive, root_id, media_dir, ep_dir, dry_run=args.dry_run))

    # Collect other local media folders (for --media-dir runs) so they stay represented in INDEX.md.
    local_only: list[dict[str, Any]] = []
    synced_slugs = {r["slug"] for r in synced_records}
    if not args.all:
        media_root = targets[0].parent
        if media_root.is_dir():
            for p in sorted(media_root.iterdir()):
                if p.is_dir() and SLUG_RE.match(p.name) and p.name not in synced_slugs:
                    ep_dir = episodes_root / p.name
                    local_only.append({
                        **parse_episode_summary(ep_dir, p.name),
                        "logs_files": [f.name for f in eligible_log_files(p / "logs")],
                        "repo_files": [n for n in REPO_FILES if (ep_dir / n).is_file()],
                        "has_report": (p / "publish-report.html").is_file(),
                    })

    # Merge existing remote INDEX.md and any remote-only episode folders (e.g. archived off local Mac).
    remote_index: dict[str, dict[str, Any]] = {}
    remote_folders: dict[str, dict[str, Any]] = {}
    root_existing: dict[str, dict[str, Any]] = {}
    if not args.dry_run:
        root_existing = drive_list_children_map(drive, root_id)
        if "INDEX.md" in root_existing:
            try:
                old_text = drive_download_bytes(drive, root_existing["INDEX.md"]["id"]).decode("utf-8")
                remote_index = parse_index_md(old_text)
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] Could not read existing remote INDEX.md: {exc}", flush=True)
        known_slugs = synced_slugs | {r["slug"] for r in local_only} | set(remote_index.keys())
        for name, item in root_existing.items():
            if item.get("mimeType") == FOLDER_MIME and SLUG_RE.match(name) and name not in known_slugs:
                remote_folders[name] = inspect_remote_episode(drive, item["id"], name, episodes_root)

    index_records = merge_index_records(
        synced=synced_records,
        local_only=local_only,
        remote_index=remote_index,
        remote_folders=remote_folders,
        episodes_root=episodes_root,
    )

    index_md = render_index(index_records)
    if args.dry_run:
        print("\n--- INDEX.md preview ---")
        print(index_md)
    else:
        upsert_text(drive, root_id, root_existing, "INDEX.md", index_md)
        print(
            f"Synced {len(synced_records)} episode(s) and updated {args.drive_root}/INDEX.md "
            f"({len(index_records)} total indexed; folder id: {root_id})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
