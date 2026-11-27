#!/usr/bin/env python3
"""Local CLI to trigger remote Bilibili dual-cover upload via GCS + GCP Cloud Run Jobs.

Shares gs://<bucket>/staging/<slug>/video.mp4 with youtube_cloud.py so the Mac only
uploads the large video once. Reuse requires the same byte size and the same sha256
recorded in staging/<slug>/bili_metadata.json or metadata.json.

Subcommands:
  upload        Stage covers + bili_metadata.json (+ video.mp4 if missing) and execute Cloud Run Job
  result        Fetch gs://<bucket>/results/<slug>-bili.json and mark bilibili: done
  sync-cookies  Upload local biliup cookies.json to GCP Secret Manager (bilibili-cookies)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bilibili_upload as bu  # noqa: E402
import log_timeline  # noqa: E402
import pack_upload  # noqa: E402
import todo_list  # noqa: E402

CONFIG_PATH = Path("~/Movies/running-content/.bili-cloud/config.json").expanduser()
YT_CONFIG_PATH = Path("~/Movies/running-content/.yt-cloud/config.json").expanduser()
DEFAULT_GCLOUD = Path("~/google-cloud-sdk/bin/gcloud").expanduser()
DEFAULT_REGION = "us-west1"
DEFAULT_JOB = "running-bili-upload"
DEFAULT_SECRET = "bilibili-cookies"
DEFAULT_LINE = "ws"
DEFAULT_LIMIT = 6
RUN_RECORD = "bilibili-upload-run.json"


def find_gcloud() -> str:
    if DEFAULT_GCLOUD.is_file():
        return str(DEFAULT_GCLOUD)
    found = shutil.which("gcloud")
    if found:
        return found
    raise FileNotFoundError("gcloud CLI not found; install Google Cloud SDK or set PATH")


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.is_file():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if YT_CONFIG_PATH.is_file():
        yt = json.loads(YT_CONFIG_PATH.read_text(encoding="utf-8"))
        project = yt.get("project", "")
        return {
            "project": project,
            "region": yt.get("region", DEFAULT_REGION),
            "bucket": yt.get("bucket") or (f"running-yt-stage-{project}" if project else ""),
            "job": DEFAULT_JOB,
            "secret_name": DEFAULT_SECRET,
            "default_line": DEFAULT_LINE,
            "default_limit": DEFAULT_LIMIT,
        }
    return {}


def resolve_episode_dir(media_dir: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidate = bu.REPO_ROOT / "episodes" / media_dir.name
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(f"Episode directory not found: {candidate}; pass --episode-dir")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def gcs_object_size(gcloud: str, gs_uri: str) -> int | None:
    res = subprocess.run(
        [gcloud, "storage", "ls", "-l", gs_uri],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    for line in res.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[-1] == gs_uri and parts[0].isdigit():
            return int(parts[0])
    return None


def remote_staged_sha256s(gcloud: str, bucket: str, slug: str) -> list[str]:
    """sha256 values recorded beside staging/<slug>/video.mp4.

    YouTube writes metadata.json. Bilibili writes bili_metadata.json. Both describe
    the shared video object. An empty list means neither file recorded a hash.
    """
    prefix = f"gs://{bucket}/staging/{slug}"
    found: list[str] = []
    for name in ("bili_metadata.json", "metadata.json"):
        res = subprocess.run(
            [gcloud, "storage", "cat", f"{prefix}/{name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0 or not (res.stdout or "").strip():
            continue
        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        sha = str(data.get("sha256") or "").strip().lower()
        if sha:
            found.append(sha)
    return found


def bilibili_inflight(media_dir: Path) -> bool:
    """True when timeline has a START bilibili-upload that no later END/FAIL closed."""
    path = Path(media_dir) / "logs" / "timeline.txt"
    if not path.is_file():
        return False
    return log_timeline.unmatched_start(path.read_text(encoding="utf-8"), bu.STEP) is not None


def read_run_id(media_dir: Path) -> str | None:
    path = Path(media_dir) / "logs" / RUN_RECORD
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    run_id = str(data.get("run_id") or "").strip()
    return run_id or None


def write_run_id(media_dir: Path, slug: str, run_id: str) -> None:
    path = Path(media_dir) / "logs" / RUN_RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"slug": slug, "run_id": run_id}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refuse_duplicate_upload(media_dir: Path, force: bool) -> None:
    if force:
        return
    todo = todo_list.load(media_dir)
    if todo.get("bilibili") == "done":
        raise SystemExit("logs/todo.md bilibili is already done; pass --force to override")
    if bilibili_inflight(media_dir):
        raise SystemExit(
            f"logs/timeline.txt has START {bu.STEP} without END/FAIL; pass --force to override"
        )
    prior = bu.successful_bilibili_note(media_dir)
    if prior:
        raise SystemExit(
            f"logs/timeline.txt already has END {bu.STEP} ({prior}); pass --force to override"
        )


def prepare_metadata(
    media_dir: Path,
    episode_dir: Path,
    *,
    tid: int = bu.TID,
    copyright: int = bu.COPYRIGHT,
) -> tuple[dict[str, Any], Path, Path, Path]:
    todo = todo_list.load(media_dir)
    if todo.get("pack-upload") != "done":
        raise ValueError(
            f"pack-upload is '{todo.get('pack-upload', 'missing')}'; run pack_upload.py first"
        )
    upload_dir = media_dir / "upload"
    if not upload_dir.is_dir():
        raise FileNotFoundError(f"upload/ directory not found in {media_dir}")

    plan_path = episode_dir / "plan.md"
    parsed = bu.parse_plan_bilibili(plan_path)
    title = str(parsed["title"])
    bu.check_bilibili_title(title)

    description = str(parsed["description"])
    if not description:
        raise ValueError(f"### B 站 description missing in {plan_path}")
    bu.check_bilibili_desc_length(description)

    tags = [str(t) for t in parsed["tags"]]
    if not tags:
        raise ValueError(f"B 站 tags missing in {plan_path}")
    bu.check_bilibili_tags(tags)

    mp4s = sorted(upload_dir.glob("*.mp4"))
    if len(mp4s) != 1:
        raise ValueError(f"Expected exactly 1 .mp4 in {upload_dir}, found {len(mp4s)}")
    video_path = mp4s[0]

    cover16_path = upload_dir / bu.COVER_16X9
    cover43_path = upload_dir / bu.COVER_4X3
    if not cover16_path.is_file():
        raise FileNotFoundError(f"16:9 cover not found: {cover16_path}")
    if not cover43_path.is_file():
        raise FileNotFoundError(f"4:3 cover not found: {cover43_path}")

    slug = media_dir.name
    sha256 = compute_sha256(video_path)
    meta = {
        "slug": slug,
        "title": title,
        "description": description,
        "tags": tags,
        "tid": tid,
        "copyright": copyright,
        "video_filename": video_path.name,
        "video_bytes": video_path.stat().st_size,
        "sha256": sha256,
        "gcs_video_object": f"staging/{slug}/video.mp4",
        "gcs_cover_16x9_object": f"staging/{slug}/cover-16x9.jpg",
        "gcs_cover_4x3_object": f"staging/{slug}/cover-4x3.jpg",
    }
    return meta, video_path, cover16_path, cover43_path


def stage_to_gcs(
    gcloud: str,
    bucket: str,
    slug: str,
    meta: dict[str, Any],
    video_path: Path,
    cover16_path: Path,
    cover43_path: Path,
    *,
    dry_run: bool,
) -> bool:
    prefix = f"gs://{bucket}/staging/{slug}"
    video_dst = f"{prefix}/video.mp4"
    reused_video = False
    if not dry_run:
        existing_size = gcs_object_size(gcloud, video_dst)
        local_sha = str(meta.get("sha256") or "").strip().lower()
        recorded = remote_staged_sha256s(gcloud, bucket, slug) if existing_size is not None else []
        size_ok = existing_size is not None and existing_size == int(meta["video_bytes"])
        sha_ok = bool(local_sha) and bool(recorded) and all(item == local_sha for item in recorded)
        if size_ok and sha_ok:
            reused_video = True
            print(
                f"[gcs] Reusing existing {video_dst} ({existing_size} bytes, sha256 matches)",
                flush=True,
            )
        elif existing_size is not None:
            print(
                f"[gcs] Not reusing {video_dst}: size or sha256 does not match the local video",
                flush=True,
            )

    with tempfile.TemporaryDirectory(prefix="bili-meta-") as tmp:
        meta_path = Path(tmp) / "bili_metadata.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        transfers: list[tuple[Path, str]] = []
        if not reused_video:
            transfers.append((video_path, video_dst))
        transfers.extend([
            (cover16_path, f"{prefix}/cover-16x9.jpg"),
            (cover43_path, f"{prefix}/cover-4x3.jpg"),
            (meta_path, f"{prefix}/bili_metadata.json"),
        ])
        gcs_env = os.environ.copy()
        gcs_env.setdefault("CLOUDSDK_STORAGE_PROCESS_COUNT", "4")
        gcs_env.setdefault("CLOUDSDK_STORAGE_THREAD_COUNT", "2")
        gcs_env.setdefault("CLOUDSDK_STORAGE_PARALLEL_COMPOSITE_UPLOAD_COMPONENT_SIZE", "20M")
        for src, dst in transfers:
            cmd = [gcloud, "storage", "cp", str(src), dst]
            print(f"[gcs] $ {' '.join(cmd)}", flush=True)
            if not dry_run:
                subprocess.run(cmd, check=True, env=gcs_env)
    return reused_video


def build_execute_cmd(
    gcloud: str,
    *,
    project: str,
    region: str,
    job: str,
    slug: str,
    bucket: str,
    line: str,
    limit: int,
    wait: bool,
    keep_staging: bool,
    run_id: str = "",
) -> list[str]:
    env_pairs = [
        f"BILI_SLUG={slug}",
        f"BILI_GCS_BUCKET={bucket}",
        f"BILI_LINE={line}",
        f"BILI_LIMIT={limit}",
        f"BILI_KEEP_STAGING={'1' if keep_staging else '0'}",
    ]
    if run_id:
        env_pairs.append(f"BILI_RUN_ID={run_id}")
    cmd = [
        gcloud, "run", "jobs", "execute", job,
        "--project", project,
        "--region", region,
        "--update-env-vars", ",".join(env_pairs),
    ]
    cmd.append("--wait" if wait else "--async")
    return cmd


def resolve_line(args: argparse.Namespace, cfg: dict[str, Any]) -> str:
    """CLI flag wins. Omitted flag uses config default_line, then ws."""
    if args.line:
        return str(args.line)
    return str(cfg.get("default_line") or DEFAULT_LINE)


def resolve_limit(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """CLI flag wins. Omitted flag uses config default_limit, then 6."""
    if args.limit is None:
        return int(cfg.get("default_limit") or DEFAULT_LIMIT)
    return int(args.limit)


def cmd_upload(args: argparse.Namespace) -> int:
    media_dir = Path(args.media_dir).expanduser().resolve()
    refuse_duplicate_upload(media_dir, args.force)
    episode_dir = resolve_episode_dir(media_dir, args.episode_dir)

    cfg = load_config()
    project = args.project or cfg.get("project") or ""
    region = args.region or cfg.get("region") or DEFAULT_REGION
    job = args.job or cfg.get("job") or DEFAULT_JOB
    bucket = args.bucket or cfg.get("bucket") or (f"running-yt-stage-{project}" if project else "")
    line = resolve_line(args, cfg)
    limit = resolve_limit(args, cfg)

    if not project or not bucket:
        raise SystemExit("Missing GCP project or bucket. Run tools/publish/cloud_bili/deploy.sh <PROJECT_ID> first.")
    if line not in bu.LINES:
        known = ", ".join(bu.LINES)
        raise SystemExit(f"unknown line {line}; choose from {known}")
    if limit < 1:
        raise SystemExit(f"--limit must be >= 1, got {limit}")

    meta, video_path, cover16_path, cover43_path = prepare_metadata(
        media_dir, episode_dir, tid=args.tid, copyright=args.copyright
    )
    run_id = uuid.uuid4().hex
    meta["run_id"] = run_id
    slug = meta["slug"]
    print(f"Slug   : {slug}", flush=True)
    print(f"Line   : {line} (limit={limit})", flush=True)
    print(f"Title  : {meta['title']}", flush=True)
    print(f"Video  : {video_path.name} ({meta['video_bytes'] / (1024 ** 3):.2f} GiB)", flush=True)
    print(f"Tags   : {', '.join(meta['tags'])}", flush=True)

    gcloud = "gcloud" if args.dry_run else find_gcloud()
    stage_to_gcs(
        gcloud,
        bucket,
        slug,
        meta,
        video_path,
        cover16_path,
        cover43_path,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        write_run_id(media_dir, slug, run_id)
        log_timeline.start(media_dir, bu.STEP)

    exec_cmd = build_execute_cmd(
        gcloud,
        project=project,
        region=region,
        job=job,
        slug=slug,
        bucket=bucket,
        line=line,
        limit=limit,
        wait=args.wait,
        keep_staging=args.keep_staging,
        run_id=run_id,
    )
    print(f"[cloud-run] $ {' '.join(exec_cmd)}", flush=True)
    if args.dry_run:
        return 0

    try:
        subprocess.run(exec_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        log_timeline.fail(media_dir, bu.STEP, rc=exc.returncode, note="cloud run execute failed")
        raise

    if args.wait:
        return cmd_result(args)

    print(
        "\nCloud Run Job triggered asynchronously! You can safely close/sleep your Mac now.\n"
        "Check result later with:\n"
        f"  .venv/bin/python tools/publish/bilibili_cloud.py result --media-dir {media_dir}",
        flush=True,
    )
    return 0


def cmd_result(args: argparse.Namespace) -> int:
    media_dir = Path(args.media_dir).expanduser().resolve()
    slug = media_dir.name
    cfg = load_config()
    project = args.project or cfg.get("project") or ""
    region = args.region or cfg.get("region") or DEFAULT_REGION
    job = args.job or cfg.get("job") or DEFAULT_JOB
    bucket = args.bucket or cfg.get("bucket") or (f"running-yt-stage-{project}" if project else "")
    if not bucket:
        raise SystemExit("Missing GCS bucket.")

    gcloud = find_gcloud()
    gs_res = f"gs://{bucket}/results/{slug}-bili.json"
    proc = subprocess.run([gcloud, "storage", "cat", gs_res], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(f"Result not ready yet at {gs_res}. Checking recent executions...", flush=True)
        if project:
            subprocess.run(
                [gcloud, "run", "jobs", "executions", "list", "--job", job, "--project", project, "--region", region, "--limit", "5"],
                check=False,
            )
        return 2

    payload = json.loads(proc.stdout)
    out_log = media_dir / "logs" / "bilibili-upload-result.json"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_log.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

    if payload.get("slug") != slug:
        print(
            f"Result slug mismatch: expected {slug}, got {payload.get('slug')!r}",
            file=sys.stderr,
        )
        return 1

    expected_run = read_run_id(media_dir)
    got_run = str(payload.get("run_id") or "").strip()
    if expected_run and got_run != expected_run:
        print(
            f"Stale result run_id {got_run or '(missing)'} != expected {expected_run}",
            file=sys.stderr,
        )
        return 1

    if payload.get("status") == "error":
        err = str(payload.get("error") or "bilibili upload failed")
        log_timeline.fail(media_dir, bu.STEP, rc=1, note=err)
        print(f"bilibili upload failed: {err}", file=sys.stderr)
        return 1

    bvid = str(payload.get("bvid") or "").strip()
    if not bvid:
        print("Result missing bvid; not marking bilibili done", file=sys.stderr)
        return 1

    url = payload.get("url", "")
    note = f"{bvid} {url} (gcs-{payload.get('line', 'ws')})".strip()
    log_timeline.end(media_dir, bu.STEP, note=note)
    todo_list.mark(media_dir, "bilibili", "done")
    print(f"\nVerified bilibili: done in {media_dir / 'logs' / 'todo.md'} ({url})", flush=True)
    return 0


def cmd_sync_cookies(args: argparse.Namespace) -> int:
    cookie_path = Path(args.cookies).expanduser()
    bu.load_cookies(cookie_path)
    cfg = load_config()
    project = args.project or cfg.get("project") or ""
    secret = args.secret or cfg.get("secret_name") or DEFAULT_SECRET
    if not project:
        raise SystemExit("Missing GCP project; pass --project or deploy first.")
    gcloud = find_gcloud()
    cmd = [
        gcloud, "secrets", "versions", "add", secret,
        "--project", project,
        "--data-file", str(cookie_path),
    ]
    print(f"[secret] $ {' '.join(cmd)}", flush=True)
    if not args.dry_run:
        subprocess.run(cmd, check=True)
    print(f"Synced {cookie_path} -> Secret Manager {secret}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Cloud Run Jobs Bilibili dual-cover upload CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="Stage to GCS (reusing video.mp4 if present) and execute Cloud Run Job")
    up.add_argument("--media-dir", required=True)
    up.add_argument("--episode-dir")
    up.add_argument("--project")
    up.add_argument("--region")
    up.add_argument("--job")
    up.add_argument("--bucket")
    up.add_argument(
        "-l",
        "--line",
        default=None,
        choices=tuple(bu.LINES),
        help="UPOS line. Omitted: config default_line, then ws",
    )
    up.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Chunk workers. Omitted: config default_limit, then 6",
    )
    up.add_argument("--tid", type=int, default=bu.TID)
    up.add_argument("--copyright", type=int, default=bu.COPYRIGHT)
    up.add_argument("--keep-staging", action=argparse.BooleanOptionalAction, default=True)
    up.add_argument("--wait", action="store_true")
    up.add_argument("--force", action="store_true")
    up.add_argument("--dry-run", action="store_true")
    up.set_defaults(func=cmd_upload)

    res = sub.add_parser("result", help="Fetch Bilibili Cloud Run Job result JSON and mark bilibili done")
    res.add_argument("--media-dir", required=True)
    res.add_argument("--project")
    res.add_argument("--region")
    res.add_argument("--job")
    res.add_argument("--bucket")
    res.set_defaults(func=cmd_result)

    sc = sub.add_parser("sync-cookies", help="Sync local biliup cookies.json to GCP Secret Manager")
    sc.add_argument("--cookies", default=str(bu.DEFAULT_COOKIE))
    sc.add_argument("--project")
    sc.add_argument("--secret")
    sc.add_argument("--dry-run", action="store_true")
    sc.set_defaults(func=cmd_sync_cookies)

    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
