---
name: p3-youtube
description: 把本期 upload/ 成片经 GCS（默认）或 Google Drive（手动切换）触发 GCP Cloud Run Job 在云端公开上传 YouTube（16:9 封面 + 外挂字幕）。用户说 YouTube 上传、自动发 YouTube、传 YT 时用。独立于 p3-publish：本 skill 只上传拿链接；写双链 / published / 合 PR / 清临时仍走 p3-publish。触发后用户 Mac 可立刻合盖断网。
---

# YouTube 自动上传（GCS / Drive → Cloud Run Job → Data API）

本 skill **只上传**，不写 `published`、不合 PR、不清临时。真正调用 YouTube Data API 的动作只发生在 **GCP Cloud Run Job（`us-west1`）**，触发后用户 Mac 可立刻合盖或断网。

## 硬规则（不要破）

1. **默认禁止**从用户 Mac 直调 YouTube Data API / Studio 上传视频，除非用户当场明确允许。
2. **默认通道：`--source gcs`**（Mac `gcloud storage cp` 直传 `gs://<bucket>/staging/<slug>/` → 异步触发 Cloud Run Job → 上传公开 → 设 16:9 封面 → 挂字幕 → 写结果到 `gs://<bucket>/results/<slug>.json` → 立刻删除 `staging/<slug>/`）。
3. **手动切换通道：`--source drive`**（复用 `stage_drive_chunks.py` 切块拷进 Google Drive `跑步成片/<slug>/` + `metadata.json` → Drive API 确认稳定 id 与字节数齐全 → 异步触发同一个 Cloud Run Job → 上传成功后将 Drive 暂存移入废纸篓）。
4. 上传默认 `privacyStatus=public`，除非用户当场改口。
5. **Drive 暂存完成**只认 Drive API 的稳定 item id 和完整体积；Finder / 本机 `ls`（含 `local-*`）不算拷完。不要在 API 还空时把同一条成片再 `cp` 进去。

## 不要做的事

- 不要默认 `unlisted` / `private`（必须 **public**，除非用户当场改口）
- 不要在缺 `pack-upload: done`、缺成片或缺 16:9 封面时硬传
- 不要把 OAuth `client_secret*.json` 或 `token.json` 提交进 git（只存 GCP Secret Manager 和仓库外 `~/Movies/running-content/.yt-cloud/`）
- 不要因外挂字幕失败而回滚已公开的成片（缺 `youtube.force-ssl` 报 403 时照样 public，可后补）

## 前置

1. 本期 `logs/todo.md` 已有 `pack-upload: done`，`~/Movies/running-content/YYYY-MM-DD-slug/upload/` 内有：
   - `<标题>.mp4`
   - `cover-16x9-1920x1080.jpg`（缩略图只用 16:9，不是 4×3）
   - 可选 `subtitles.srt`
2. `episodes/YYYY-MM-DD-slug/plan.md` 已有 `## 标题`、`### YouTube` 简介（不含 `http://`/`https://`）和 `## 标签` 里的 `YouTube 标签`。
3. 云端设施已初始化（一次）：见 `tools/publish/cloud_yt/README.md`（`auth_oauth.py` + `deploy.sh`，配置落在 `~/Movies/running-content/.yt-cloud/config.json`）。

## 日常触发（默认 GCS；可手动切 Drive）

### 默认：GCS + Cloud Run Job（推荐，最快且无 Drive 桌面版同步黑盒）

```bash
.venv/bin/python tools/publish/youtube_cloud.py upload \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

### 手动切换：Google Drive + Cloud Run Job

```bash
.venv/bin/python tools/publish/youtube_cloud.py upload \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --source drive
```

说明：
- 默认 `--async`：云端暂存完并触发 Cloud Run Job 后立刻返回，此时 **Mac 可直接合盖断网**。如需现场等完拿到链接，加 `--wait`。
- 触发脚本会自动写 `logs/timeline.txt`（`drive-stage` 和 `start youtube-upload`），并在暂存完成后把 `logs/todo.md` 的 `drive` 标为 `done`。跑完立刻读 `logs/todo.md` 核对。

## 取回结果并落账

稍后（通常 1–3 分钟，或合盖回来后）运行：

```bash
.venv/bin/python tools/publish/youtube_cloud.py result \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

脚本会从 `gs://<bucket>/results/YYYY-MM-DD-slug.json` 拉回结果 JSON、写副本到 `logs/youtube-upload-result.json`、补记 `end youtube-upload` 并把 `logs/todo.md` 的 `youtube` 标为 `done`。跑完立刻读 `logs/todo.md` 确认 `youtube` 为带时间的 `done`。清单不对就停。

## 成功后

1. 把 `https://youtu.be/…` 写入该期 `episode.md`「发布」栏「YouTube：」（B 站仍空则 **不要** 改 `published`）。
2. 推当期 episode 分支；**只有 B 站 + YouTube 双链都齐** 才轮到 `/p3-publish`（写齐、改 `published`、squash episode PR、出 `publish-report.html`、清临时）。
3. 告诉用户：

> YouTube 已公开：`https://youtu.be/…`（缩略图/字幕若失败如实说；云端暂存已自动清理）。
> B 站仍空着时 `status` 保持 `edited`。双链齐了再 `/p3-publish`。

## 翻车记录

- OAuth 同意屏幕若停在 Testing，Google 会在 **7 天后强制吊销 `refresh_token`**；必须切到 Production（个人自用无需提交审核）。
- Cloud Run Job 必须设置 `--max-retries 0`，避免网络抖动导致重复上传两条公开视频。
- GCS 桶建在 `us-west1`（Always Free 区域）并配 `staging/` 1 天自动删除 Lifecycle 规则，防止意外遗留产生存储费。
- captions 缺 `youtube.force-ssl` 时整片仍可 public；不要把字幕当成上传门闩。
