#!/usr/bin/env python3
"""Cloud Run Job: upload a staged running episode from GCS (default) or Google Drive to YouTube.

Environment variables (overridable via CLI flags):
  YT_SLUG          Episode slug, e.g. 2026-11-24-lsd-short (required)
  YT_SOURCE        "gcs" (default) or "drive"
  YT_GCS_BUCKET    GCS bucket for staging (gcs mode) and results/<slug>.json (both modes)
  YT_DRIVE_ROOT    Google Drive root folder name, default "跑步成片"
  YT_TOKEN_FILE    OAuth token JSON path, default "/secrets/youtube-oauth/token.json"
  YT_KEEP_STAGING  "1" / "true" to keep staging files after success (default false)
  YT_DRIVE_WAIT_S  Max seconds to wait for Drive chunks to finish syncing (default 300)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.cloud import storage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

UPLOAD_CHUNK_BYTES = 16 * 1024 * 1024
RETRIABLE_HTTP_STATUS = {500, 502, 503, 504}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def parse_manifest(text: str) -> tuple[list[tuple[str, int]], int | None, str | None]:
    """Parse stage_drive_chunks.py manifest.txt -> ([(chunk_name, size)], total_bytes, sha256)."""
    chunks: list[tuple[str, int]] = []
    total: int | None = None
    sha256: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] == "TOTAL" and len(parts) >= 2:
            total = int(parts[1])
        elif parts[0] == "SHA256" and len(parts) >= 2:
            sha256 = parts[1].lower()
        elif parts[0].startswith("chunk-") and len(parts) >= 2:
            chunks.append((parts[0], int(parts[1])))
    if not chunks:
        raise ValueError("manifest.txt contains no chunk entries")
    return chunks, total, sha256


def parse_sha256_file(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            return line.split()[0].lower()
    raise ValueError("original.sha256 is empty")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_credentials(token_file: Path) -> Credentials:
    if not token_file.is_file():
        raise FileNotFoundError(f"OAuth token file not found: {token_file}")
    info = json.loads(token_file.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info)
    if not creds.refresh_token:
        raise ValueError("OAuth token.json is missing refresh_token")
    log("Refreshing Google OAuth access token...")
    creds.refresh(Request())
    return creds


# ---------------------------------------------------------------------------
# GCS source
# ---------------------------------------------------------------------------

def stage_from_gcs(bucket_name: str, slug: str, work_dir: Path) -> tuple[dict[str, Any], Path, Path | None, Path | None]:
    if not bucket_name:
        raise ValueError("YT_GCS_BUCKET / --bucket is required for --source gcs")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = f"staging/{slug}/"

    meta_blob = bucket.blob(f"{prefix}metadata.json")
    if not meta_blob.exists():
        raise FileNotFoundError(f"Missing gs://{bucket_name}/{prefix}metadata.json")
    meta = json.loads(meta_blob.download_as_text(encoding="utf-8"))

    video_blob_name = meta.get("gcs_video_object") or f"{prefix}video.mp4"
    video_blob = bucket.blob(video_blob_name)
    if not video_blob.exists():
        raise FileNotFoundError(f"Missing gs://{bucket_name}/{video_blob_name}")

    video_path = work_dir / "video.mp4"
    log(f"Downloading gs://{bucket_name}/{video_blob_name} -> {video_path} ...")
    t0 = time.monotonic()
    video_blob.download_to_filename(str(video_path))
    size_mb = video_path.stat().st_size / (1024 * 1024)
    log(f"Downloaded video ({size_mb:.1f} MiB) in {time.monotonic() - t0:.1f}s")

    expected_sha = (meta.get("sha256") or "").strip().lower()
    if expected_sha:
        actual_sha = file_sha256(video_path)
        if actual_sha != expected_sha:
            raise RuntimeError(f"SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")
        log(f"SHA-256 verified: {actual_sha[:16]}...")

    cover_path: Path | None = None
    for candidate in (meta.get("gcs_cover_object"), f"{prefix}cover-16x9.jpg", f"{prefix}cover-16x9-1920x1080.jpg"):
        if not candidate:
            continue
        blob = bucket.blob(candidate)
        if blob.exists():
            cover_path = work_dir / "cover-16x9.jpg"
            blob.download_to_filename(str(cover_path))
            log(f"Downloaded cover gs://{bucket_name}/{candidate}")
            break

    srt_path: Path | None = None
    for candidate in (meta.get("gcs_srt_object"), f"{prefix}subtitles.srt"):
        if not candidate:
            continue
        blob = bucket.blob(candidate)
        if blob.exists():
            srt_path = work_dir / "subtitles.srt"
            blob.download_to_filename(str(srt_path))
            log(f"Downloaded subtitles gs://{bucket_name}/{candidate}")
            break

    return meta, video_path, cover_path, srt_path


def cleanup_gcs_staging(bucket_name: str, slug: str) -> int:
    """Delete staging/<slug>/ unless a Bilibili job still needs the shared video.

    bili_metadata.json means bilibili_cloud.py is using the same video.mp4. Leave the
    prefix for that job; the bucket lifecycle rule removes staging/ after a day.
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = f"staging/{slug}/"
    if bucket.blob(f"{prefix}bili_metadata.json").exists():
        log(f"Keeping gs://{bucket_name}/{prefix} because bili_metadata.json is present")
        return 0
    blobs = list(client.list_blobs(bucket, prefix=prefix))
    for blob in blobs:
        blob.delete()
    log(f"Cleaned {len(blobs)} staged object(s) under gs://{bucket_name}/{prefix}")
    return len(blobs)


def write_gcs_result(bucket_name: str, slug: str, result: dict[str, Any]) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    obj = f"results/{slug}.json"
    blob = bucket.blob(obj)
    blob.upload_from_string(json.dumps(result, ensure_ascii=False, indent=2) + "\n", content_type="application/json")
    uri = f"gs://{bucket_name}/{obj}"
    log(f"Wrote result to {uri}")
    return uri


# ---------------------------------------------------------------------------
# Google Drive source (compatible with stage_drive_chunks.py)
# ---------------------------------------------------------------------------

def _drive_find_child(drive, parent_id: str | None, name: str, mime_type: str | None = None) -> dict[str, Any] | None:
    safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
    clauses = [f"name = '{safe_name}'", "trashed = false"]
    if parent_id:
        clauses.append(f"'{parent_id}' in parents")
    if mime_type:
        clauses.append(f"mimeType = '{mime_type}'")
    resp = drive.files().list(
        q=" and ".join(clauses),
        fields="files(id, name, mimeType, size)",
        pageSize=20,
    ).execute()
    files = resp.get("files", [])
    return files[0] if files else None


def _drive_list_children(drive, folder_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _drive_download_bytes(drive, file_id: str) -> bytes:
    buf = io.BytesIO()
    req = drive.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def _drive_download_file(creds: Credentials, file_id: str, dest: Path) -> None:
    # Build a thread-local Drive client for safe concurrent downloads.
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    req = drive.files().get_media(fileId=file_id)
    with dest.open("wb") as fh:
        dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()


def assemble_drive_chunks_streaming(
    manifest_chunks: list[tuple[str, int]],
    download_fn,
    video_path: Path,
    chunk_dir: Path,
    *,
    prefetch: int = 2,
) -> str:
    """Download Drive chunks with a bounded prefetch window, append in order, and unlink immediately.

    Keeps peak Cloud Run tmpfs usage near `1x video + prefetch * chunk_size` instead of `2x video`.
    Returns the SHA-256 hex digest of the assembled video.
    """
    chunk_dir.mkdir(parents=True, exist_ok=True)
    window = max(1, prefetch)
    hasher = hashlib.sha256()

    with ThreadPoolExecutor(max_workers=window) as pool, video_path.open("wb") as out_fh:
        in_flight: dict[int, Any] = {}

        def submit(idx: int) -> None:
            cname, _csize = manifest_chunks[idx]
            in_flight[idx] = pool.submit(download_fn, cname, chunk_dir / cname)

        for idx in range(min(window, len(manifest_chunks))):
            submit(idx)

        for idx, (cname, expected_size) in enumerate(manifest_chunks):
            fut = in_flight.pop(idx)
            fut.result()
            cpath = chunk_dir / cname
            got = cpath.stat().st_size
            if got != expected_size:
                cpath.unlink(missing_ok=True)
                raise RuntimeError(f"Chunk {cname} size mismatch: expected {expected_size}, got {got}")

            next_idx = idx + window
            if next_idx < len(manifest_chunks):
                submit(next_idx)

            with cpath.open("rb") as in_fh:
                for block in iter(lambda: in_fh.read(4 * 1024 * 1024), b""):
                    out_fh.write(block)
                    hasher.update(block)
            cpath.unlink(missing_ok=True)

    return hasher.hexdigest()


def stage_from_drive(
    creds: Credentials,
    drive_root_name: str,
    slug: str,
    work_dir: Path,
    wait_seconds: int = 300,
) -> tuple[dict[str, Any], Path, Path | None, Path | None, str]:
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder_mime = "application/vnd.google-apps.folder"

    root = _drive_find_child(drive, None, drive_root_name, mime_type=folder_mime)
    if not root:
        raise FileNotFoundError(f"Drive root folder not found: {drive_root_name}")
    ep_folder = _drive_find_child(drive, root["id"], slug, mime_type=folder_mime)
    if not ep_folder:
        raise FileNotFoundError(f"Drive episode folder not found: {drive_root_name}/{slug}")
    ep_id = ep_folder["id"]

    # Wait until metadata.json and chunks/manifest.txt + all chunks match expected sizes.
    deadline = time.monotonic() + max(0, wait_seconds)
    chunks_folder = None
    manifest_chunks: list[tuple[str, int]] = []
    manifest_sha: str | None = None
    chunk_id_map: dict[str, str] = {}
    ep_children: dict[str, dict[str, Any]] = {}

    while True:
        ep_children = {f["name"]: f for f in _drive_list_children(drive, ep_id)}
        chunks_folder = ep_children.get("chunks")
        if chunks_folder and chunks_folder.get("mimeType") == folder_mime:
            chunk_files = {f["name"]: f for f in _drive_list_children(drive, chunks_folder["id"])}
            if "manifest.txt" in chunk_files:
                manifest_text = _drive_download_bytes(drive, chunk_files["manifest.txt"]["id"]).decode("utf-8")
                manifest_chunks, _total, manifest_sha = parse_manifest(manifest_text)
                if not manifest_sha and "original.sha256" in chunk_files:
                    sha_text = _drive_download_bytes(drive, chunk_files["original.sha256"]["id"]).decode("utf-8")
                    manifest_sha = parse_sha256_file(sha_text)
                missing = []
                for cname, expected_size in manifest_chunks:
                    entry = chunk_files.get(cname)
                    actual_size = int(entry.get("size", -1)) if entry else -1
                    if not entry or actual_size != expected_size:
                        missing.append(f"{cname}({actual_size}/{expected_size})")
                if not missing and "metadata.json" in ep_children:
                    chunk_id_map = {cname: chunk_files[cname]["id"] for cname, _ in manifest_chunks}
                    log(f"Drive staging ready: {len(manifest_chunks)} chunks verified via Drive API")
                    break
                reason = f"waiting on metadata.json or chunks: {missing[:5]}"
            else:
                reason = "waiting on chunks/manifest.txt"
        else:
            reason = "waiting on chunks/ folder"

        if time.monotonic() >= deadline:
            raise TimeoutError(f"Drive staging incomplete for {drive_root_name}/{slug}: {reason}")
        log(f"Drive sync in progress ({reason}); retrying in 15s...")
        time.sleep(15)

    meta = json.loads(_drive_download_bytes(drive, ep_children["metadata.json"]["id"]).decode("utf-8"))
    expected_sha = (meta.get("sha256") or manifest_sha or "").strip().lower()

    # Stream chunks with a 2-chunk prefetch window and delete each chunk right after appending
    # so tmpfs peak stays ~1x video + ~200 MiB (safe inside 8Gi Cloud Run memory even for 4GB+ videos).
    chunk_dir = work_dir / "chunks"
    video_path = work_dir / "video.mp4"
    log(f"Downloading & assembling {len(manifest_chunks)} chunks from Drive (bounded prefetch=2)...")
    t0 = time.monotonic()
    actual_sha = assemble_drive_chunks_streaming(
        manifest_chunks,
        lambda cname, dest: _drive_download_file(creds, chunk_id_map[cname], dest),
        video_path,
        chunk_dir,
        prefetch=2,
    )
    if expected_sha and actual_sha != expected_sha:
        raise RuntimeError(f"Assembled Drive video SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")
    log(
        f"Assembled {video_path.stat().st_size / (1024 * 1024):.1f} MiB in {time.monotonic() - t0:.1f}s, "
        f"SHA-256 verified: {actual_sha[:16]}..."
    )

    cover_path: Path | None = None
    for cname in ("cover-16x9-1920x1080.jpg", "cover-16x9.jpg"):
        if cname in ep_children:
            cover_path = work_dir / "cover-16x9.jpg"
            _drive_download_file(creds, ep_children[cname]["id"], cover_path)
            log(f"Downloaded Drive cover {cname}")
            break

    srt_path: Path | None = None
    if "subtitles.srt" in ep_children:
        srt_path = work_dir / "subtitles.srt"
        _drive_download_file(creds, ep_children["subtitles.srt"]["id"], srt_path)
        log("Downloaded Drive subtitles.srt")

    return meta, video_path, cover_path, srt_path, ep_id


def cleanup_drive_staging(creds: Credentials, ep_folder_id: str, result: dict[str, Any]) -> None:
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    children = _drive_list_children(drive, ep_folder_id)
    trashed = 0
    for child in children:
        if child["name"] == "upload_result.json":
            continue
        drive.files().update(fileId=child["id"], body={"trashed": True}).execute()
        trashed += 1
    # Save a tiny upload_result.json in the episode folder for auditability.
    payload = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json", resumable=False)
    drive.files().create(
        body={"name": "upload_result.json", "parents": [ep_folder_id]},
        media_body=media,
        fields="id",
    ).execute()
    log(f"Trashed {trashed} Drive staging item(s) and wrote upload_result.json")


# ---------------------------------------------------------------------------
# YouTube Data API v3 upload (shared by GCS and Drive modes)
# ---------------------------------------------------------------------------

def upload_to_youtube(
    creds: Credentials,
    meta: dict[str, Any],
    video_path: Path,
    cover_path: Path | None,
    srt_path: Path | None,
) -> dict[str, Any]:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    title = str(meta["title"]).strip()
    description = str(meta["description"]).strip()
    tags = [str(t).strip() for t in meta.get("tags", []) if str(t).strip()]
    privacy_status = str(meta.get("privacy_status") or "public").strip()
    category_id = str(meta.get("category_id") or "22").strip()
    language = str(meta.get("language") or "zh-Hans").strip()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=UPLOAD_CHUNK_BYTES,
        resumable=True,
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    log(f"Starting YouTube resumable upload: title={title!r} privacy={privacy_status}")
    t0 = time.monotonic()
    response = None
    retry = 0
    last_pct = -10
    while response is None:
        try:
            status, response = request.next_chunk()
            retry = 0
            if status:
                pct = int(status.progress() * 100)
                if pct >= last_pct + 10:
                    log(f"YouTube upload progress: {pct}%")
                    last_pct = pct
        except HttpError as exc:
            if exc.resp is not None and exc.resp.status in RETRIABLE_HTTP_STATUS and retry < 6:
                retry += 1
                sleep_s = min(60, 2 ** retry)
                log(f"Retriable YouTube HTTP {exc.resp.status}; sleeping {sleep_s}s (attempt {retry}/6)")
                time.sleep(sleep_s)
                continue
            raise
        except OSError as exc:
            if retry < 6:
                retry += 1
                sleep_s = min(60, 2 ** retry)
                log(f"Network error during upload ({exc}); sleeping {sleep_s}s (attempt {retry}/6)")
                time.sleep(sleep_s)
                continue
            raise

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    log(f"YouTube video uploaded: {url} in {time.monotonic() - t0:.1f}s")

    thumb_ok = False
    thumb_error: str | None = None
    if cover_path and cover_path.is_file():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(cover_path), mimetype="image/jpeg"),
            ).execute()
            thumb_ok = True
            log("16:9 thumbnail set successfully")
        except Exception as exc:  # noqa: BLE001
            thumb_error = str(exc)
            log(f"WARNING: thumbnail upload failed (video stays {privacy_status}): {thumb_error}")

    caption_ok = False
    caption_error: str | None = None
    if srt_path and srt_path.is_file():
        try:
            youtube.captions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "language": language,
                        "name": "中文（简体）",
                        "isDraft": False,
                    }
                },
                media_body=MediaFileUpload(str(srt_path), mimetype="application/octet-stream"),
            ).execute()
            caption_ok = True
            log("Subtitles (captions) uploaded successfully")
        except Exception as exc:  # noqa: BLE001
            caption_error = str(exc)
            log(f"WARNING: captions upload failed (video stays {privacy_status}): {caption_error}")

    return {
        "video_id": video_id,
        "url": url,
        "title": title,
        "privacy_status": response.get("status", {}).get("privacyStatus", privacy_status),
        "thumbnail_ok": thumb_ok,
        "thumbnail_error": thumb_error,
        "caption_ok": caption_ok,
        "caption_error": caption_error,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cloud Run Job YouTube uploader (GCS default, Drive switchable)")
    parser.add_argument("--slug", default=os.environ.get("YT_SLUG", ""))
    parser.add_argument("--source", choices=("gcs", "drive"), default=os.environ.get("YT_SOURCE", "gcs"))
    parser.add_argument("--bucket", default=os.environ.get("YT_GCS_BUCKET", ""))
    parser.add_argument("--drive-root", default=os.environ.get("YT_DRIVE_ROOT", "跑步成片"))
    parser.add_argument("--token-file", default=os.environ.get("YT_TOKEN_FILE", "/secrets/youtube-oauth/token.json"))
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        default=os.environ.get("YT_KEEP_STAGING", "").lower() in ("1", "true", "yes"),
    )
    parser.add_argument("--drive-wait-s", type=int, default=int(os.environ.get("YT_DRIVE_WAIT_S", "300")))
    args = parser.parse_args(argv)

    if not args.slug:
        parser.error("--slug or YT_SLUG is required")

    t_start = time.monotonic()
    work_dir = Path("/tmp/yt-work") / args.slug
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    log(f"Job start: slug={args.slug} source={args.source} bucket={args.bucket or '(none)'}")
    creds = load_credentials(Path(args.token_file))

    drive_ep_id: str | None = None
    if args.source == "gcs":
        meta, video_path, cover_path, srt_path = stage_from_gcs(args.bucket, args.slug, work_dir)
    else:
        meta, video_path, cover_path, srt_path, drive_ep_id = stage_from_drive(
            creds, args.drive_root, args.slug, work_dir, wait_seconds=args.drive_wait_s
        )

    yt_res = upload_to_youtube(creds, meta, video_path, cover_path, srt_path)
    result = {
        "slug": args.slug,
        "source": args.source,
        **yt_res,
        "elapsed_s": round(time.monotonic() - t_start, 1),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.bucket:
        write_gcs_result(args.bucket, args.slug, result)

    if not args.keep_staging:
        if args.source == "gcs":
            cleanup_gcs_staging(args.bucket, args.slug)
        elif drive_ep_id:
            cleanup_drive_staging(creds, drive_ep_id, result)

    # Machine-readable line for log fallback if bucket is omitted.
    print(f"YT_UPLOAD_RESULT_JSON={json.dumps(result, ensure_ascii=False)}", flush=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    log(f"Job finished successfully in {result['elapsed_s']}s: {result['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
