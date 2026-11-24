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
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

DEFAULT_TOKEN = Path("~/Movies/running-content/.yt-cloud/token.json").expanduser()
DEFAULT_MEDIA_ROOT = Path("~/Movies/running-content").expanduser()
DEFAULT_DRIVE_ROOT = "running-retrospect"
SHANGHAI = ZoneInfo("Asia/Shanghai")
FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB guard: text/json/html logs only
ALLOWED_SUFFIXES = {".txt", ".md", ".json", ".log", ".html", ".csv", ".yaml", ".yml"}
REPO_FILES = ("episode.md", "plan.md", "assets.md")


def load_drive_service(token_path: Path):
    if not token_path.is_file():
        raise FileNotFoundError(
            f"OAuth token not found: {token_path}. Run tools/publish/cloud_yt/auth_oauth.py first."
        )
    info = json.loads(token_path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info)
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _escape_q(val: str) -> str:
    return val.replace("\\", "\\\\").replace("'", "\\'")


def ensure_folder(drive, parent_id: str | None, name: str) -> str:
    clauses = [f"name = '{_escape_q(name)}'", f"mimeType = '{FOLDER_MIME}'", "trashed = false"]
    if parent_id:
        clauses.append(f"'{parent_id}' in parents")
    else:
        clauses.append("'root' in parents")
    resp = drive.files().list(q=" and ".join(clauses), fields="files(id, name)", pageSize=5).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    body: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]
    created = drive.files().create(body=body, fields="id").execute()
    return created["id"]


def list_children_map(drive, folder_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    pt = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=200,
            pageToken=pt,
        ).execute()
        for item in resp.get("files", []):
            out[item["name"]] = item
        pt = resp.get("nextPageToken")
        if not pt:
            break
    return out


def upsert_file(drive, parent_id: str, existing: dict[str, dict[str, Any]], local_path: Path, name: str | None = None) -> str:
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


def upsert_text(drive, parent_id: str, existing: dict[str, dict[str, Any]], name: str, text: str, mime: str = "text/markdown") -> str:
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
        ep_existing = list_children_map(drive, ep_folder_id)

        if log_files:
            logs_folder_id = ensure_folder(drive, ep_folder_id, "logs")
            logs_existing = list_children_map(drive, logs_folder_id)
            for lf in log_files:
                upsert_file(drive, logs_folder_id, logs_existing, lf)

        if repo_files:
            repo_folder_id = ensure_folder(drive, ep_folder_id, "episode-repo")
            repo_existing = list_children_map(drive, repo_folder_id)
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
        bili = r["bilibili"] or "-"
        yt = r["youtube"] or "-"
        logs_col = f"{len(r['logs_files'])} files" if r["logs_files"] else "missing"
        repo_col = ", ".join(r["repo_files"]) if r["repo_files"] else "missing"
        rep_col = "yes" if r["has_report"] else "no"
        title = r["title"].replace("|", "\\|")
        lines.append(
            f"| `{r['slug']}` | {title} | `{r['status']}` | {bili} | {yt} | {logs_col} | {repo_col} | {rep_col} |"
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
            if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}-", p.name)
        )
    else:
        targets = [Path(args.media_dir).expanduser().resolve()]

    if not targets:
        raise SystemExit("No episode media directories found to sync.")

    drive = None if args.dry_run else load_drive_service(Path(args.token_file).expanduser())
    root_id = "" if args.dry_run else ensure_folder(drive, None, args.drive_root)

    records: list[dict[str, Any]] = []
    for media_dir in targets:
        ep_dir = episodes_root / media_dir.name
        records.append(sync_episode(drive, root_id, media_dir, ep_dir, dry_run=args.dry_run))

    # When syncing a single episode, rebuild INDEX.md across all local media folders for completeness.
    index_records = records
    if not args.all:
        media_root = targets[0].parent
        all_local = sorted(
            p for p in media_root.iterdir()
            if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}-", p.name)
        )
        by_slug = {r["slug"]: r for r in records}
        for p in all_local:
            if p.name not in by_slug:
                ep_dir = episodes_root / p.name
                by_slug[p.name] = {
                    **parse_episode_summary(ep_dir, p.name),
                    "logs_files": [f.name for f in eligible_log_files(p / "logs")],
                    "repo_files": [n for n in REPO_FILES if (ep_dir / n).is_file()],
                    "has_report": (p / "publish-report.html").is_file(),
                }
        index_records = list(by_slug.values())

    index_md = render_index(index_records)
    if args.dry_run:
        print("\n--- INDEX.md preview ---")
        print(index_md)
    else:
        root_existing = list_children_map(drive, root_id)
        upsert_text(drive, root_id, root_existing, "INDEX.md", index_md)
        print(f"Synced {len(records)} episode(s) and updated {args.drive_root}/INDEX.md (folder id: {root_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
