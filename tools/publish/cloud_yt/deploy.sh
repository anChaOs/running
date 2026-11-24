#!/usr/bin/env bash
set -euo pipefail

# Idempotent deployment for the Cloud Run Job YouTube uploader (GCS default + Google Drive fallback).
# All resources default to us-west1 (GCP Always Free region for GCS & Cloud Run Jobs).

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
BUCKET_NAME="${2:-${YT_GCS_BUCKET:-running-yt-stage-${PROJECT_ID}}}"
REPO_NAME="${YT_AR_REPO:-running-tools}"
IMAGE_NAME="yt-uploader"
JOB_NAME="${YT_JOB_NAME:-running-yt-upload}"
SA_NAME="running-yt-uploader"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME="${YT_SECRET_NAME:-youtube-oauth-token}"
DRIVE_ROOT="${YT_DRIVE_ROOT:-跑步成片}"
CONFIG_PATH="$HOME/Movies/running-content/.yt-cloud/config.json"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo "==> Project: ${PROJECT_ID}  Region: ${REGION}  Bucket: gs://${BUCKET_NAME}"

echo "==> 1/6 Enabling required GCP APIs..."
"$GCLOUD" services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  youtube.googleapis.com \
  drive.googleapis.com \
  --project "$PROJECT_ID"

echo "==> 2/6 Ensuring us-west1 GCS bucket & 1-day staging lifecycle rule..."
if ! "$GCLOUD" storage buckets describe "gs://${BUCKET_NAME}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  "$GCLOUD" storage buckets create "gs://${BUCKET_NAME}" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --default-storage-class STANDARD \
    --uniform-bucket-level-access
fi

LIFECYCLE_FILE="$(mktemp)"
trap 'rm -f "${LIFECYCLE_FILE:-}"' EXIT
cat >"$LIFECYCLE_FILE" <<'JSON'
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 1,
        "matchesPrefix": ["staging/"]
      }
    }
  ]
}
JSON
"$GCLOUD" storage buckets update "gs://${BUCKET_NAME}" --lifecycle-file="$LIFECYCLE_FILE"
rm -f "$LIFECYCLE_FILE"
LIFECYCLE_FILE=""

echo "==> 3/6 Ensuring dedicated least-privilege Service Account..."
if ! "$GCLOUD" iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  "$GCLOUD" iam service-accounts create "$SA_NAME" \
    --project "$PROJECT_ID" \
    --display-name "Running Vlog YouTube Cloud Run Uploader"
  sleep 5
fi

"$GCLOUD" storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin" >/dev/null

if "$GCLOUD" secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  "$GCLOUD" secrets add-iam-policy-binding "$SECRET_NAME" \
    --project "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
else
  echo "WARNING: Secret '${SECRET_NAME}' not found yet. Run auth_oauth.py first, then re-run deploy.sh." >&2
  exit 2
fi

echo "==> 4/6 Ensuring Artifact Registry repository & building container via Cloud Build..."
if ! "$GCLOUD" artifacts repositories describe "$REPO_NAME" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  "$GCLOUD" artifacts repositories create "$REPO_NAME" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --repository-format=docker \
    --description="Running vlog Cloud Run uploader images"
fi

"$GCLOUD" builds submit "$SCRIPT_DIR" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --tag "$IMAGE_URI"

echo "==> 5/6 Deploying Cloud Run Job (${JOB_NAME})..."
"$GCLOUD" run jobs deploy "$JOB_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE_URI" \
  --service-account "$SA_EMAIL" \
  --cpu 2 \
  --memory 8Gi \
  --task-timeout 3600s \
  --max-retries 0 \
  --set-env-vars "YT_SOURCE=gcs,YT_GCS_BUCKET=${BUCKET_NAME},YT_DRIVE_ROOT=${DRIVE_ROOT},YT_TOKEN_FILE=/secrets/youtube-oauth/token.json" \
  --set-secrets "/secrets/youtube-oauth/token.json=${SECRET_NAME}:latest"

echo "==> 6/6 Writing local CLI config -> ${CONFIG_PATH}"
mkdir -p "$(dirname "$CONFIG_PATH")"
cat >"$CONFIG_PATH" <<JSON
{
  "project": "${PROJECT_ID}",
  "region": "${REGION}",
  "bucket": "${BUCKET_NAME}",
  "job": "${JOB_NAME}",
  "drive_root": "${DRIVE_ROOT}",
  "secret_name": "${SECRET_NAME}",
  "default_source": "gcs"
}
JSON
chmod 600 "$CONFIG_PATH"

echo "DONE. Cloud Run Job '${JOB_NAME}' deployed in ${REGION} (default source: gcs, switchable to drive)."
