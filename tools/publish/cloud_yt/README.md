# Cloud Run Jobs YouTube 上传器（默认 GCS，可手动切换 Google Drive）

用同一个 GCP Cloud Run Job（`us-west1` 免费层）把本期成片公开上传到 YouTube，设 16:9 封面并挂中文字幕。触发后 Mac 可以立刻合盖、断网。

## 文件说明

- `job_main.py`：Cloud Run Job 容器主程序，通过 `YT_SOURCE=gcs|drive`（默认 `gcs`）切换暂存源。
- `Dockerfile` / `requirements.txt`：轻量 Python 3.11 镜像，由 Cloud Build 在云端构建。
- `auth_oauth.py`：本机一次性 OAuth 桌面授权脚本，把含 `refresh_token` 的凭证写入 GCP Secret Manager（不进 git）。
- `deploy.sh`：一键幂等部署（启用 API、建 `us-west1` GCS Bucket + `staging/` 1 天自动删除规则、最小权限 Service Account、Cloud Build 构镜像、部署 Cloud Run Job，并写入本地配置 `~/Movies/running-content/.yt-cloud/config.json`）。
- `../youtube_cloud.py`：本机日常触发与取结果 CLI。

## 一次性初始化

```bash
# 1. 登录 gcloud
~/google-cloud-sdk/bin/gcloud auth login

# 2. 跑一次 OAuth 授权，写入 Secret Manager（需先在 GCP Console 建 Desktop OAuth Client 并切 Production）
.venv/bin/python tools/publish/cloud_yt/auth_oauth.py \
  --client-secret ~/Downloads/client_secret_xxx.json \
  --project <GCP_PROJECT_ID>

# 3. 一键部署 Bucket（us-west1 + 1 天自动删）+ Cloud Run Job
tools/publish/cloud_yt/deploy.sh <GCP_PROJECT_ID>
```

## 日常使用

```bash
# 默认方式：GCS 并发直传 + 异步触发 Cloud Run Job（触发后立刻可合盖）
.venv/bin/python tools/publish/youtube_cloud.py upload \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug

# 手动切换为 Google Drive 分块通道
.venv/bin/python tools/publish/youtube_cloud.py upload \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --source drive

# 稍后取回 YouTube 链接并自动标 todo done
.venv/bin/python tools/publish/youtube_cloud.py result \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```
