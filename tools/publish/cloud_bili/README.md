# Cloud Run Jobs B 站双封面上传器（共用 GCS staging）

与 `cloud_yt/` 共用同一套 `us-west1` GCS Bucket（`gs://running-yt-stage-<project>/staging/<slug>/video.mp4`）。Mac 只需上传一次视频到 GCS，即可同时触发 YouTube 和 B 站云端投稿并立刻合盖断网。

## 为什么用 `ws` 线路

2026-11-27 在 `us-west1` 实测：
- 出口 IP 调 `member.bilibili.com` 未触发 `-412` 异地风控；
- `ws`（`zone=cs`，分配 `upcdntxa`）10 MiB PUT 实测 `3.64 MiB/s`（`qn` 分配 `upcdnalia` 为 `2.15 MiB/s`），`bda2` 仅 `0.13 MiB/s`、`tx` 超时、`bldsa` 证书过期。

## 一次性部署

```bash
chmod +x tools/publish/cloud_bili/deploy.sh
tools/publish/cloud_bili/deploy.sh <GCP_PROJECT_ID>
```

## 日常使用

```bash
# 1. 触发云端投稿（若 YouTube 已把 video.mp4 传进 GCS staging，自动跳过视频重传）
.venv/bin/python tools/publish/bilibili_cloud.py upload \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug

# 2. 稍后取回 BV 号与链接并标 bilibili: done
.venv/bin/python tools/publish/bilibili_cloud.py result \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug

# 3. 本机 cookies.json renew/重新扫码后同步到 Secret Manager
.venv/bin/python tools/publish/bilibili_cloud.py sync-cookies
```
