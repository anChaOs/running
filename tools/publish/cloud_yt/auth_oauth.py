#!/usr/bin/env python3
"""One-time local OAuth helper for Cloud Run YouTube + Google Drive uploader.

Generates a refresh-token-backed token.json with scopes:
  - youtube.upload
  - youtube
  - youtube.force-ssl (for captions)
  - drive (for --source drive mode and cleanup)

Uploads the token directly into GCP Secret Manager (never into git).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _google_common import DEFAULT_LOCAL_TOKEN, find_gcloud  # noqa: E402

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/drive",
]


def push_secret(project: str, secret_name: str, token_json: str) -> None:
    gcloud = find_gcloud()
    check = subprocess.run(
        [gcloud, "secrets", "describe", secret_name, "--project", project],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode != 0:
        subprocess.run(
            [
                gcloud, "secrets", "create", secret_name,
                "--project", project,
                "--replication-policy=automatic",
            ],
            check=True,
        )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(token_json)
        tmp_path = Path(tmp.name)
    try:
        os.chmod(tmp_path, 0o600)
        subprocess.run(
            [
                gcloud, "secrets", "versions", "add", secret_name,
                "--project", project,
                f"--data-file={tmp_path}",
            ],
            check=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authorize YouTube + Drive OAuth and upload token to Secret Manager")
    parser.add_argument("--client-secret", required=True, help="Path to OAuth Desktop client_secret*.json from GCP Console")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--secret-name", default="youtube-oauth-token", help="Secret Manager secret name")
    parser.add_argument(
        "--save-local",
        default=str(DEFAULT_LOCAL_TOKEN),
        help="Also save token locally (chmod 600, outside repo) for Drive API verification; pass '' to skip",
    )
    args = parser.parse_args(argv)

    client_secret = Path(args.client_secret).expanduser()
    if not client_secret.is_file():
        raise SystemExit(f"client secret not found: {client_secret}")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    if not creds.refresh_token:
        raise SystemExit("Did not receive refresh_token. Revoke previous grant in Google Account and re-run.")

    token_json = creds.to_json()
    push_secret(args.project, args.secret_name, token_json)
    print(f"Uploaded OAuth token to Secret Manager: projects/{args.project}/secrets/{args.secret_name}")

    if args.save_local:
        dest = Path(args.save_local).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(token_json + "\n", encoding="utf-8")
        os.chmod(dest, 0o600)
        print(f"Saved local copy (mode 600, outside repo): {dest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
