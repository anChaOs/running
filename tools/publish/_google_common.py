#!/usr/bin/env python3
"""Shared local helpers for Google Cloud / Google Drive publishing CLIs.

Used by local Mac scripts (`youtube_cloud.py`, `sync_retrospect_drive.py`,
`cloud_yt/auth_oauth.py`). Container code (`cloud_yt/job_main.py`) stays
self-contained so Docker builds only depend on `tools/publish/cloud_yt/`.
"""

from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("~/Movies/running-content/.yt-cloud/config.json").expanduser()
DEFAULT_LOCAL_TOKEN = Path("~/Movies/running-content/.yt-cloud/token.json").expanduser()
FOLDER_MIME = "application/vnd.google-apps.folder"


def find_gcloud() -> str:
    for candidate in (
        os.environ.get("GCLOUD_BIN"),
        str(Path("~/google-cloud-sdk/bin/gcloud").expanduser()),
        shutil.which("gcloud"),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return "gcloud"


def escape_drive_q(val: str) -> str:
    return val.replace("\\", "\\\\").replace("'", "\\'")


def load_drive_service(token_path: Path):
    if not token_path.is_file():
        raise FileNotFoundError(
            f"OAuth token not found: {token_path}. Run tools/publish/cloud_yt/auth_oauth.py first."
        )
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    info = json.loads(token_path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info)
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def drive_find_child(
    drive,
    parent_id: str | None,
    name: str,
    *,
    mime_type: str | None = None,
    root_only: bool = False,
) -> dict[str, Any] | None:
    clauses = [f"name = '{escape_drive_q(name)}'", "trashed = false"]
    if parent_id:
        clauses.append(f"'{parent_id}' in parents")
    elif root_only:
        clauses.append("'root' in parents")
    if mime_type:
        clauses.append(f"mimeType = '{mime_type}'")
    resp = drive.files().list(
        q=" and ".join(clauses),
        fields="files(id, name, mimeType, size)",
        pageSize=20,
    ).execute()
    files = resp.get("files", [])
    return files[0] if files else None


def drive_list_children_map(drive, folder_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    page_token = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        for item in resp.get("files", []):
            out[item["name"]] = item
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def drive_download_bytes(drive, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()
