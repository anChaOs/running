#!/usr/bin/env python3
"""Cloud Run Job: upload a GCS-staged running episode to Bilibili (dual cover).

Environment variables (overridable via CLI flags):
  BILI_SLUG          Episode slug, e.g. 2026-11-27-taper-week (required)
  BILI_GCS_BUCKET    GCS bucket for staging/<slug>/ and results/<slug>-bili.json
  BILI_COOKIE_FILE   biliup cookies.json path, default "/secrets/bili/cookies.json"
  BILI_LINE          UPOS line, default "ws" (us-west1 -> upcdntxa)
  BILI_LIMIT         Concurrent chunk upload workers, default "6"
  BILI_RETRIES       Extra attempts after a chunk or merge failure, default "3"
  BILI_RUN_ID        Echoed into the result JSON. bili_metadata.json run_id wins.
  BILI_KEEP_STAGING  "1" / "true" to keep staging files after success (default true)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from google.cloud import storage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bilibili_upload as bu  # noqa: E402


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_staging(
    storage_client: storage.Client,
    bucket_name: str,
    slug: str,
    work_dir: Path,
) -> tuple[dict[str, Any], Path, Path, Path]:
    """Download the staged episode. Local names are fixed; metadata filenames are not paths."""
    bucket = storage_client.bucket(bucket_name)
    prefix = f"staging/{slug}/"

    meta_blob = bucket.blob(f"{prefix}bili_metadata.json")
    if not meta_blob.exists():
        raise FileNotFoundError(f"gs://{bucket_name}/{prefix}bili_metadata.json not found")
    meta = json.loads(meta_blob.download_as_text(encoding="utf-8"))

    video_path = work_dir / "video.mp4"
    cover16_path = work_dir / "cover-16x9.jpg"
    cover43_path = work_dir / "cover-4x3.jpg"
    downloads = [
        (f"{prefix}video.mp4", video_path),
        (f"{prefix}cover-16x9.jpg", cover16_path),
        (f"{prefix}cover-4x3.jpg", cover43_path),
    ]
    for obj_name, dst in downloads:
        blob = bucket.blob(obj_name)
        if not blob.exists():
            raise FileNotFoundError(f"gs://{bucket_name}/{obj_name} not found")
        log(f"Downloading gs://{bucket_name}/{obj_name} -> {dst.name}")
        blob.download_to_filename(str(dst))

    expected_bytes = meta.get("video_bytes")
    if expected_bytes is not None and video_path.stat().st_size != int(expected_bytes):
        raise RuntimeError(
            f"Video size mismatch: got {video_path.stat().st_size}, expected {expected_bytes}"
        )
    expected_sha = str(meta.get("sha256") or "").strip().lower()
    if not expected_sha:
        raise RuntimeError("bili_metadata.json missing sha256")
    actual_sha = file_sha256(video_path)
    if actual_sha != expected_sha:
        raise RuntimeError(f"SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")
    log(f"SHA-256 verified: {actual_sha[:16]}...")
    return meta, video_path, cover16_path, cover43_path


def write_result(
    storage_client: storage.Client,
    bucket_name: str,
    slug: str,
    result: dict[str, Any],
) -> None:
    bucket = storage_client.bucket(bucket_name)
    obj = f"results/{slug}-bili.json"
    bucket.blob(obj).upload_from_string(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json; charset=utf-8",
    )
    log(f"Wrote result to gs://{bucket_name}/{obj}")


def cleanup_staging(storage_client: storage.Client, bucket_name: str, slug: str) -> None:
    """Delete this slug's staging prefix unless YouTube's metadata.json is still there.

    video.mp4 is shared. Removing it while metadata.json exists would break a YouTube
    retry. The bucket lifecycle rule deletes staging/ after a day.
    """
    bucket = storage_client.bucket(bucket_name)
    prefix = f"staging/{slug}/"
    if bucket.blob(f"{prefix}metadata.json").exists():
        log(f"Keeping gs://{bucket_name}/{prefix} because metadata.json is present")
        return
    for blob in bucket.list_blobs(prefix=prefix):
        log(f"Deleting staging object gs://{bucket_name}/{blob.name}")
        blob.delete()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Cloud Run Job Bilibili dual-cover uploader")
    ap.add_argument("--slug", default=os.environ.get("BILI_SLUG", ""))
    ap.add_argument("--bucket", default=os.environ.get("BILI_GCS_BUCKET", ""))
    ap.add_argument("--cookie-file", default=os.environ.get("BILI_COOKIE_FILE", "/secrets/bili/cookies.json"))
    ap.add_argument("--line", default=os.environ.get("BILI_LINE", "ws"))
    ap.add_argument("--limit", type=int, default=int(os.environ.get("BILI_LIMIT", "6")))
    ap.add_argument("--retries", type=int, default=int(os.environ.get("BILI_RETRIES", "3")))
    ap.add_argument(
        "--keep-staging",
        action="store_true",
        default=os.environ.get("BILI_KEEP_STAGING", "1").lower() in ("1", "true", "yes"),
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.slug:
        raise SystemExit("BILI_SLUG / --slug is required")
    if not args.bucket:
        raise SystemExit("BILI_GCS_BUCKET / --bucket is required")
    if args.limit < 1:
        raise SystemExit(f"--limit must be >= 1, got {args.limit}")
    if args.retries < 0:
        raise SystemExit(f"--retries must be >= 0, got {args.retries}")

    t0 = time.monotonic()
    storage_client = storage.Client()
    work_dir = Path("/tmp/bili_work") / args.slug
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("BILI_RUN_ID", "")

    try:
        cookies = bu.load_cookies(Path(args.cookie_file))
        meta, video_path, cover16_path, cover43_path = download_staging(
            storage_client, args.bucket, args.slug, work_dir
        )
        if meta.get("run_id"):
            run_id = str(meta["run_id"])

        ready = bu.EpisodeUpload(
            media_dir=work_dir,
            episode_dir=work_dir,
            title=str(meta["title"]),
            description=str(meta["description"]),
            tags=[str(tag) for tag in meta.get("tags") or []],
            video=video_path,
            cover_16x9=cover16_path,
            cover_4x3=cover43_path,
            cookies=cookies,
            pack_state="done",
        )
        session = requests.Session()
        try:
            res = bu.upload_episode(
                ready,
                line=args.line,
                limit=args.limit,
                retries=args.retries,
                session=session,
                tid=int(meta.get("tid", bu.TID)),
                copyright=int(meta.get("copyright", bu.COPYRIGHT)),
            )
        finally:
            session.close()
        elapsed_s = round(time.monotonic() - t0, 1)
        result_payload = {
            "slug": args.slug,
            "status": "ok",
            "bvid": res["bvid"],
            "aid": res.get("aid"),
            "url": res["url"],
            "title": meta["title"],
            "line": args.line,
            "run_id": run_id,
            "elapsed_s": elapsed_s,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        write_result(storage_client, args.bucket, args.slug, result_payload)
        log(f"Done: {res['url']} in {elapsed_s}s")
    except Exception as exc:
        error_payload = {
            "slug": args.slug,
            "status": "error",
            "error": str(exc),
            "run_id": run_id,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            write_result(storage_client, args.bucket, args.slug, error_payload)
        except Exception as write_exc:
            log(f"Failed to write error result: {write_exc}")
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if not args.keep_staging:
        cleanup_staging(storage_client, args.bucket, args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
