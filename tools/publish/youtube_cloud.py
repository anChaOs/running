#!/usr/bin/env python3
"""Local CLI to trigger remote YouTube upload via GCP Cloud Run Jobs.

Supports two staging backends (default: gcs; manually switchable to drive):
  - gcs   (default): upload directly to GCS bucket staging/<slug>/, then fire Cloud Run Job async.
  - drive (manual) : stage chunks via stage_drive_chunks.py + metadata.json into Google Drive,
                     verify cloud readiness via Drive API, then fire Cloud Run Job async.

After the async trigger returns, the Mac can safely sleep or go offline.
Run `youtube_cloud.py result --media-dir ...` later to fetch the YouTube URL and mark todo done.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import log_timeline  # noqa: E402
import todo_list  # noqa: E402

DEFAULT_CONFIG_PATH = Path("~/Movies/running-content/.yt-cloud/config.json").expanduser()
DEFAULT_LOCAL_TOKEN = Path("~/Movies/running-content/.yt-cloud/token.json").expanduser()
DRIVE_LEAVES = ("我的云端硬盘", "My Drive")


def find_gcloud() -> str:
    for candidate in (
        os.environ.get("GCLOUD_BIN"),
        str(Path("~/google-cloud-sdk/bin/gcloud").expanduser()),
        shutil.which("gcloud"),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return "gcloud"


def load_cloud_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_section(markdown: str, heading_pattern: str, stop_pattern: str) -> str:
    lines = markdown.splitlines()
    in_section = False
    out: list[str] = []
    for line in lines:
        if not in_section:
            if re.match(heading_pattern, line.strip()):
                in_section = True
            continue
        if re.match(stop_pattern, line.strip()):
            break
        out.append(line)
    return "\n".join(out).strip()


def parse_plan_youtube(plan_path: Path) -> dict[str, Any]:
    """Parse title, YouTube description, and YouTube tags from episodes/<slug>/plan.md."""
    text = plan_path.read_text(encoding="utf-8")

    # 1. Title
    title_sec = _extract_section(text, r"^##\s+标题\s*$", r"^##\s+")
    title = ""
    for line in title_sec.splitlines():
        s = line.strip().lstrip(">").strip()
        if not s:
            continue
        if "发这个" in s:
            m = re.search(r"发这个[：:]\s*(.+)$", s)
            if m and m.group(1).strip():
                title = m.group(1).strip()
                break
            continue
        if not title:
            title = s
    if not title:
        raise ValueError(f"Could not parse ## 标题 from {plan_path}")

    # 2. YouTube description (must not contain http:// or https:// per p3-subs)
    desc = _extract_section(text, r"^###\s+YouTube\s*$", r"^#{2,3}\s+")
    if not desc:
        raise ValueError(f"Could not parse ### YouTube description from {plan_path}")
    if re.search(r"https?://", desc, flags=re.IGNORECASE):
        raise ValueError("YouTube description in plan.md must not contain http:// or https:// links")

    # 3. YouTube tags
    tags_sec = _extract_section(text, r"^##\s+标签\s*$", r"^##\s+")
    yt_tags: list[str] = []
    m_yt = re.search(r"YouTube\s*标签[：:]\s*```[^\n]*\n(.*?)```", tags_sec, flags=re.DOTALL)
    if m_yt:
        raw_tags = m_yt.group(1).strip()
        yt_tags = [t.strip().lstrip("#") for t in re.split(r"[,，\n]+", raw_tags) if t.strip()]
    if not yt_tags:
        raise ValueError(f"Could not parse YouTube tags from {plan_path}")

    return {"title": title, "description": desc, "tags": yt_tags}


def read_pack_sha256(media_dir: Path, video_name: str) -> str | None:
    sha_file = media_dir / "logs" / "pack-sha256.txt"
    if not sha_file.is_file():
        return None
    for raw in sha_file.read_text(encoding="utf-8").splitlines():
        parts = raw.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            if Path(parts[1].strip()).name == video_name:
                return parts[0].lower()
    return None


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_upload_assets(media_dir: Path) -> tuple[Path, Path, Path | None]:
    upload_dir = media_dir / "upload"
    if not upload_dir.is_dir():
        raise FileNotFoundError(f"upload/ directory not found in {media_dir}; run pack_upload.py first")
    mp4s = sorted(p for p in upload_dir.glob("*.mp4") if p.is_file())
    if len(mp4s) != 1:
        raise ValueError(f"Expected exactly 1 .mp4 in {upload_dir}, found {len(mp4s)}: {[p.name for p in mp4s]}")
    cover = upload_dir / "cover-16x9-1920x1080.jpg"
    if not cover.is_file():
        raise FileNotFoundError(f"Missing 16:9 cover in upload/: {cover}")
    srt = upload_dir / "subtitles.srt"
    return mp4s[0], cover, (srt if srt.is_file() else None)


def build_metadata(
    media_dir: Path,
    episode_dir: Path,
    *,
    privacy: str = "public",
    category_id: str = "22",
    language: str = "zh-Hans",
) -> tuple[dict[str, Any], Path, Path, Path | None]:
    slug = media_dir.name
    plan_path = episode_dir / "plan.md"
    if not plan_path.is_file():
        raise FileNotFoundError(f"plan.md not found: {plan_path}")
    parsed = parse_plan_youtube(plan_path)
    video_path, cover_path, srt_path = resolve_upload_assets(media_dir)
    sha256 = read_pack_sha256(media_dir, video_path.name) or compute_sha256(video_path)
    meta = {
        "slug": slug,
        "title": parsed["title"],
        "description": parsed["description"],
        "tags": parsed["tags"],
        "privacy_status": privacy,
        "category_id": category_id,
        "language": language,
        "video_filename": video_path.name,
        "video_bytes": video_path.stat().st_size,
        "sha256": sha256,
        "gcs_video_object": f"staging/{slug}/video.mp4",
        "gcs_cover_object": f"staging/{slug}/cover-16x9.jpg",
        "gcs_srt_object": f"staging/{slug}/subtitles.srt" if srt_path else None,
    }
    return meta, video_path, cover_path, srt_path


def find_local_drive_root(drive_root_name: str) -> Path:
    cloud = Path("~/Library/CloudStorage").expanduser()
    if cloud.is_dir():
        for account in sorted(cloud.glob("GoogleDrive-*")):
            for leaf in DRIVE_LEAVES:
                candidate = account / leaf / drive_root_name
                if candidate.is_dir():
                    return candidate
    raise FileNotFoundError(f"Could not locate local Google Drive folder '{drive_root_name}' under ~/Library/CloudStorage")


def build_execute_cmd(
    gcloud: str,
    *,
    project: str,
    region: str,
    job: str,
    slug: str,
    source: str,
    bucket: str,
    drive_root: str,
    wait: bool,
    keep_staging: bool,
) -> list[str]:
    env_pairs = [
        f"YT_SLUG={slug}",
        f"YT_SOURCE={source}",
        f"YT_DRIVE_ROOT={drive_root}",
    ]
    if bucket:
        env_pairs.append(f"YT_GCS_BUCKET={bucket}")
    if keep_staging:
        env_pairs.append("YT_KEEP_STAGING=1")
    cmd = [
        gcloud, "run", "jobs", "execute", job,
        "--project", project,
        "--region", region,
        "--update-env-vars", ",".join(env_pairs),
    ]
    cmd.append("--wait" if wait else "--async")
    return cmd


def stage_to_gcs(
    gcloud: str,
    bucket: str,
    slug: str,
    meta: dict[str, Any],
    video_path: Path,
    cover_path: Path,
    srt_path: Path | None,
    *,
    dry_run: bool,
) -> None:
    prefix = f"gs://{bucket}/staging/{slug}"
    with tempfile.TemporaryDirectory(prefix="yt-meta-") as tmp:
        meta_path = Path(tmp) / "metadata.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        transfers = [
            (video_path, f"{prefix}/video.mp4"),
            (cover_path, f"{prefix}/cover-16x9.jpg"),
            (meta_path, f"{prefix}/metadata.json"),
        ]
        if srt_path:
            transfers.append((srt_path, f"{prefix}/subtitles.srt"))
        for src, dst in transfers:
            cmd = [gcloud, "storage", "cp", str(src), dst]
            print(f"[gcs] $ {' '.join(cmd)}", flush=True)
            if not dry_run:
                subprocess.run(cmd, check=True)


def stage_to_drive(
    media_dir: Path,
    slug: str,
    drive_root_name: str,
    meta: dict[str, Any],
    video_path: Path,
    cover_path: Path,
    srt_path: Path | None,
    *,
    dry_run: bool,
) -> Path:
    drive_root = find_local_drive_root(drive_root_name)
    ep_drive = drive_root / slug
    chunks_dir = ep_drive / "chunks"
    work_dir = media_dir / "yt-drive-chunks"

    # Reuse existing Drive chunks if manifest.txt already matches our current SHA-256.
    reuse_chunks = False
    existing_manifest = chunks_dir / "manifest.txt"
    if existing_manifest.is_file():
        if meta["sha256"] in existing_manifest.read_text(encoding="utf-8"):
            reuse_chunks = True
            print(f"[drive] Reusing existing chunks in {chunks_dir} (SHA-256 matches)", flush=True)

    if not reuse_chunks:
        stage_script = Path(__file__).resolve().parent / "stage_drive_chunks.py"
        cmd = [
            sys.executable, str(stage_script),
            "--src", str(video_path),
            "--drive-folder", f"{drive_root_name}/{slug}/chunks",
            "--work-dir", str(work_dir),
        ]
        print(f"[drive] $ {' '.join(cmd)}", flush=True)
        if not dry_run:
            subprocess.run(cmd, check=True)

    if not dry_run:
        ep_drive.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cover_path, ep_drive / cover_path.name)
        if srt_path:
            shutil.copy2(srt_path, ep_drive / srt_path.name)
        (ep_drive / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[drive] Staged cover, subtitles, and metadata.json into {ep_drive}", flush=True)
    return ep_drive


def verify_drive_cloud_ready(token_path: Path, drive_root_name: str, slug: str, timeout_s: int = 600) -> bool:
    """Verify via Drive API that metadata.json and all manifest chunks have stable cloud ids & full sizes."""
    if not token_path.is_file():
        print(f"[drive] Local token not found at {token_path}; skipping local Drive API verification (Cloud Run Job will wait/verify).", flush=True)
        return False

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import io

    # Import manifest parser from cloud_yt/job_main.py
    sys.path.insert(0, str(Path(__file__).resolve().parent / "cloud_yt"))
    from job_main import parse_manifest  # noqa: E402

    info = json.loads(token_path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info)
    creds.refresh(Request())
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder_mime = "application/vnd.google-apps.folder"

    def find_child(parent_id: str | None, name: str, mime: str | None = None) -> dict | None:
        safe = name.replace("\\", "\\\\").replace("'", "\\'")
        q = [f"name = '{safe}'", "trashed = false"]
        if parent_id:
            q.append(f"'{parent_id}' in parents")
        if mime:
            q.append(f"mimeType = '{mime}'")
        files = drive.files().list(q=" and ".join(q), fields="files(id,name,size,mimeType)", pageSize=20).execute().get("files", [])
        return files[0] if files else None

    def list_children(folder_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        pt = None
        while True:
            resp = drive.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken,files(id,name,size,mimeType)",
                pageSize=200,
                pageToken=pt,
            ).execute()
            for item in resp.get("files", []):
                out[item["name"]] = item
            pt = resp.get("nextPageToken")
            if not pt:
                break
        return out

    deadline = time.monotonic() + timeout_s
    while True:
        root = find_child(None, drive_root_name, folder_mime)
        ep = find_child(root["id"], slug, folder_mime) if root else None
        if ep:
            children = list_children(ep["id"])
            chunks_folder = children.get("chunks")
            if chunks_folder and "metadata.json" in children:
                cfiles = list_children(chunks_folder["id"])
                if "manifest.txt" in cfiles:
                    buf = io.BytesIO()
                    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=cfiles["manifest.txt"]["id"]))
                    done = False
                    while not done:
                        _, done = dl.next_chunk()
                    chunks, _, _ = parse_manifest(buf.getvalue().decode("utf-8"))
                    missing = [
                        f"{n}({cfiles.get(n, {}).get('size', -1)}/{sz})"
                        for n, sz in chunks
                        if n not in cfiles or int(cfiles[n].get("size", -1)) != sz
                    ]
                    if not missing:
                        print(f"[drive] Drive API confirmed all {len(chunks)} chunks + metadata.json synced!", flush=True)
                        return True
                    status = f"{len(chunks) - len(missing)}/{len(chunks)} chunks synced (missing: {', '.join(missing[:3])})"
                else:
                    status = "waiting for chunks/manifest.txt in Drive API"
            else:
                status = "waiting for chunks/ and metadata.json in Drive API"
        else:
            status = f"waiting for {drive_root_name}/{slug} folder in Drive API"

        if time.monotonic() >= deadline:
            raise TimeoutError(f"Drive API sync check timed out after {timeout_s}s: {status}")
        print(f"[drive] {status}; rechecking in 10s...", flush=True)
        time.sleep(10)


def cmd_upload(args: argparse.Namespace) -> int:
    media_dir = Path(args.media_dir).expanduser().resolve()
    slug = media_dir.name
    episode_dir = Path(args.episode_dir).expanduser().resolve() if args.episode_dir else Path("episodes") / slug

    cfg = load_cloud_config(Path(args.config).expanduser())
    project = args.project or cfg.get("project") or ""
    region = args.region or cfg.get("region") or "us-west1"
    bucket = args.bucket or cfg.get("bucket") or ""
    job = args.job or cfg.get("job") or "running-yt-upload"
    drive_root = args.drive_root or cfg.get("drive_root") or "跑步成片"
    source = args.source or cfg.get("default_source") or "gcs"

    if not project:
        raise SystemExit("Missing GCP project. Run tools/publish/cloud_yt/deploy.sh first or pass --project.")
    if source == "gcs" and not bucket:
        raise SystemExit("Missing GCS bucket for --source gcs. Pass --bucket or set it in config.json.")

    if not args.dry_run:
        status = todo_list.load(media_dir)
        if status.get("pack-upload") != "done":
            raise SystemExit("logs/todo.md requires pack-upload: done before uploading to YouTube.")

    meta, video_path, cover_path, srt_path = build_metadata(
        media_dir, episode_dir, privacy=args.privacy
    )
    gcloud = find_gcloud()

    print(f"Slug    : {slug}")
    print(f"Source  : {source} (default=gcs; switchable via --source gcs|drive)")
    print(f"Title   : {meta['title']}")
    print(f"Video   : {video_path.name} ({meta['video_bytes'] / (1024**3):.2f} GiB, sha256={meta['sha256'][:12]}...)")
    print(f"Tags    : {', '.join(meta['tags'])}")

    if source == "gcs":
        if not args.dry_run:
            log_timeline.start(media_dir, "drive-stage")
        try:
            stage_to_gcs(gcloud, bucket, slug, meta, video_path, cover_path, srt_path, dry_run=args.dry_run)
        except Exception as exc:
            if not args.dry_run:
                log_timeline.fail(media_dir, "drive-stage", note=f"gcs stage failed: {exc}")
            raise
        if not args.dry_run:
            log_timeline.end(media_dir, "drive-stage", note=f"gcs gs://{bucket}/staging/{slug}/")
            todo_list.mark(media_dir, "drive", "done")
    else:
        stage_to_drive(media_dir, slug, drive_root, meta, video_path, cover_path, srt_path, dry_run=args.dry_run)
        if not args.dry_run and not args.no_verify_drive:
            verify_drive_cloud_ready(Path(args.token_file).expanduser(), drive_root, slug, timeout_s=args.drive_wait_s)
        if not args.dry_run:
            todo_list.mark(media_dir, "drive", "done")

    exec_cmd = build_execute_cmd(
        gcloud,
        project=project,
        region=region,
        job=job,
        slug=slug,
        source=source,
        bucket=bucket,
        drive_root=drive_root,
        wait=args.wait,
        keep_staging=args.keep_staging,
    )
    print(f"[cloud-run] $ {' '.join(exec_cmd)}", flush=True)
    if args.dry_run:
        return 0

    log_timeline.start(media_dir, "youtube-upload")
    proc = subprocess.run(exec_cmd)
    if proc.returncode != 0:
        log_timeline.fail(media_dir, "youtube-upload", rc=proc.returncode, note=f"cloud run execute failed ({source})")
        return proc.returncode

    if args.wait:
        return cmd_result(args)

    print(
        "\nCloud Run Job triggered asynchronously! You can safely close/sleep your Mac now.\n"
        f"Check result later with:\n"
        f"  .venv/bin/python tools/publish/youtube_cloud.py result --media-dir {media_dir}",
        flush=True,
    )
    return 0


def cmd_result(args: argparse.Namespace) -> int:
    media_dir = Path(args.media_dir).expanduser().resolve()
    slug = media_dir.name
    cfg = load_cloud_config(Path(args.config).expanduser())
    project = args.project or cfg.get("project") or ""
    region = args.region or cfg.get("region") or "us-west1"
    bucket = args.bucket or cfg.get("bucket") or ""
    job = args.job or cfg.get("job") or "running-yt-upload"
    gcloud = find_gcloud()

    if not bucket:
        raise SystemExit("Missing GCS bucket to read results/<slug>.json. Pass --bucket.")

    result_uri = f"gs://{bucket}/results/{slug}.json"
    proc = subprocess.run(
        [gcloud, "storage", "cat", result_uri],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"Result not ready yet at {result_uri}. Checking recent Cloud Run Job executions...", flush=True)
        if project:
            subprocess.run(
                [gcloud, "run", "jobs", "executions", "list", "--job", job, "--project", project, "--region", region, "--limit", "5"],
                check=False,
            )
        return 1

    result = json.loads(proc.stdout)
    out_log = media_dir / "logs" / "youtube-upload-result.json"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_log.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    url = result.get("url", "")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if url:
        status = todo_list.load(media_dir)
        if status.get("youtube") != "done":
            if log_timeline.unmatched_start((media_dir / "logs" / "timeline.txt").read_text(encoding="utf-8"), "youtube-upload"):
                log_timeline.end(media_dir, "youtube-upload", note=f"{url} ({result.get('source', 'cloud')})")
            todo_list.mark(media_dir, "youtube", "done")
            print(f"\nMarked youtube: done in {media_dir / 'logs' / 'todo.md'} ({url})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cloud Run Jobs YouTube upload trigger (GCS default, Drive switchable)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--media-dir", required=True, help="~/Movies/running-content/YYYY-MM-DD-slug")
        sp.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
        sp.add_argument("--project", default="")
        sp.add_argument("--region", default="")
        sp.add_argument("--bucket", default="")
        sp.add_argument("--job", default="")

    sp_up = sub.add_parser("upload", help="Stage episode to GCS (default) or Drive and trigger Cloud Run Job")
    add_common(sp_up)
    sp_up.add_argument("--episode-dir", default="", help="Default: episodes/<slug>")
    sp_up.add_argument("--source", choices=("gcs", "drive"), default=None, help="Staging backend: gcs (default) or drive")
    sp_up.add_argument("--drive-root", default="", help="Drive root folder name (default: 跑步成片)")
    sp_up.add_argument("--privacy", choices=("public", "unlisted", "private"), default="public")
    sp_up.add_argument("--wait", action="store_true", help="Wait for Cloud Run Job to finish instead of async return")
    sp_up.add_argument("--keep-staging", action="store_true", help="Do not delete GCS/Drive staging files after upload")
    sp_up.add_argument("--no-verify-drive", action="store_true", help="Skip local Drive API sync wait in --source drive mode")
    sp_up.add_argument("--drive-wait-s", type=int, default=600)
    sp_up.add_argument("--token-file", default=str(DEFAULT_LOCAL_TOKEN))
    sp_up.add_argument("--dry-run", action="store_true")
    sp_up.set_defaults(func=cmd_upload)

    sp_res = sub.add_parser("result", help="Fetch Cloud Run YouTube upload result JSON and mark todo done")
    add_common(sp_res)
    sp_res.set_defaults(func=cmd_result)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
