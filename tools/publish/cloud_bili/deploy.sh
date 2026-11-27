#!/usr/bin/env bash
set -euo pipefail

# Idempotent deployment for the Cloud Run Job Bilibili dual-cover uploader.
# Reuses the us-west1 GCS bucket, Artifact Registry repo, and Service Account from cloud_yt.

GCLOUD="${GCLOUD_BIN:-$HOME/google-cloud-sdk/bin/gcloud}"
if ! command -v "$GCLOUD" >/dev/null 2>&1; then
  GCLOUD="gcloud"
fi

PROJECT_ID="${1:-${GCP_PROJECT:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$("$GCLOUD" config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Usage: $0 <GCP_PROJECT_ID> [BUCKET_NAME]" >&2
  exit 1
fi

REGION="${GCP_REGION:-us-west1}"
BUCKET_NAME="${2:-${BILI_GCS_BUCKET:-running-yt-stage-${PROJECT_ID}}}"
REPO_NAME="${BILI_AR_REPO:-running-tools}"
IMAGE_NAME="bili-uploader"
JOB_NAME="${BILI_JOB_NAME:-running-bili-upload}"
SA_NAME="running-yt-uploader"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME="${BILI_SECRET_NAME:-bilibili-cookies}"
LOCAL_COOKIES="${BILI_LOCAL_COOKIES:-$HOME/Movies/running-content/.biliup/cookies.json}"
CONFIG_PATH="$HOME/Movies/running-content/.bili-cloud/config.json"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PUBLISH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo "==> Project: ${PROJECT_ID}  Region: ${REGION}  Bucket: gs://${BUCKET_NAME}"

REPO_ROOT="$(cd "$PUBLISH_DIR/../.." && pwd)"
PY="${BILI_PYTHON:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "==> 0/5 Checking shared bucket and service account from cloud_yt..."
if ! "$GCLOUD" storage buckets describe "gs://${BUCKET_NAME}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "Bucket gs://${BUCKET_NAME} does not exist." >&2
  echo "Run tools/publish/cloud_yt/deploy.sh ${PROJECT_ID} first to create the bucket and service account." >&2
  exit 1
fi
if ! "$GCLOUD" iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "Service account ${SA_EMAIL} does not exist." >&2
  echo "Run tools/publish/cloud_yt/deploy.sh ${PROJECT_ID} first to create the bucket and service account." >&2
  exit 1
fi

echo "==> 1/5 Ensuring Bilibili cookie secret in Secret Manager (${SECRET_NAME})..."
if ! "$GCLOUD" secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  "$GCLOUD" secrets create "$SECRET_NAME" --project "$PROJECT_ID" --replication-policy="automatic"
fi
if [[ -f "$LOCAL_COOKIES" ]]; then
  echo "    Validating ${LOCAL_COOKIES} with bilibili_upload.load_cookies"
  "$PY" - "$PUBLISH_DIR" "$LOCAL_COOKIES" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import bilibili_upload

bilibili_upload.load_cookies(Path(sys.argv[2]))
PY
  "$GCLOUD" secrets versions add "$SECRET_NAME" --project "$PROJECT_ID" --data-file="$LOCAL_COOKIES" >/dev/null
  echo "    Uploaded latest ${LOCAL_COOKIES} -> ${SECRET_NAME}"
else
  echo "    WARNING: ${LOCAL_COOKIES} not found; ensure secret ${SECRET_NAME} already has a version." >&2
fi
"$GCLOUD" secrets add-iam-policy-binding "$SECRET_NAME" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "==> 2/5 Staging build context and building container via Cloud Build..."
BUILD_TMP="$(mktemp -d)"
trap 'rm -rf "${BUILD_TMP:-}"' EXIT
cp "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR/requirements.txt" "$SCRIPT_DIR/job_main.py" "$BUILD_TMP/"
cp "$PUBLISH_DIR/bilibili_upload.py" "$BUILD_TMP/"

"$GCLOUD" builds submit "$BUILD_TMP" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --tag "$IMAGE_URI"

echo "==> 3/5 Deploying Cloud Run Job (${JOB_NAME})..."
"$GCLOUD" run jobs deploy "$JOB_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE_URI" \
  --service-account "$SA_EMAIL" \
  --cpu 2 \
  --memory 8Gi \
  --task-timeout 3600s \
  --max-retries 0 \
  --set-env-vars "BILI_GCS_BUCKET=${BUCKET_NAME},BILI_COOKIE_FILE=/secrets/bili/cookies.json,BILI_LINE=ws,BILI_LIMIT=6,BILI_KEEP_STAGING=1" \
  --set-secrets "/secrets/bili/cookies.json=${SECRET_NAME}:latest"

echo "==> 4/5 Writing local CLI config -> ${CONFIG_PATH}"
mkdir -p "$(dirname "$CONFIG_PATH")"
cat >"$CONFIG_PATH" <<JSON
{
  "project": "${PROJECT_ID}",
  "region": "${REGION}",
  "bucket": "${BUCKET_NAME}",
  "job": "${JOB_NAME}",
  "secret_name": "${SECRET_NAME}",
  "default_line": "ws",
  "default_limit": 6
}
JSON
chmod 600 "$CONFIG_PATH"

echo "==> 5/5 DONE. Cloud Run Job '${JOB_NAME}' deployed in ${REGION} (line: ws)."
