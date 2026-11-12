---
name: p3-youtube
description: 把本期 upload/ 成片经 Google Drive「跑步成片」暂存到 bot 云电脑，再用 YouTube Data API 公开上传（16:9 封面）。用户说 YouTube 上传、自动发 YouTube、传 YT 时用。独立于 p3-publish：本 skill 只上传拿链接；写双链 / published / 合 PR / 复盘日志上 box / 清临时仍走 p3-publish。默认禁止从用户 Mac 调 YouTube API / Studio 上传。
---

# YouTube 自动上传（Drive → box → Data API）

本 skill **只上传**，不写 `published`、不合 PR、不拷复盘日志、不清临时。成片必须能在 **用户 Mac 关机** 时仍传得上去：上传动作只发生在 **bot 云电脑（box）**。

## 硬规则（不要破）

1. **默认禁止**从用户 Mac（或任何注册用户电脑）跑 YouTube Data API / Studio 上传。除非 **安超当场明确允许**「这次可以用我电脑传 YouTube」。
2. **唯一默认路径：** Mac（或已有成片处）→ 暂存到 Google Drive 文件夹 **「跑步成片」** → bot 用 Drive 下载到 **box** → 在 box 上 YouTube Data API **resumable** 上传，`privacyStatus=public`。
3. 上传成功后：**清空本期**在「跑步成片」里的暂存成片/封面（进废纸篓即可）；文件夹本身可留空给下期。
4. **暂存完成**只认 Drive API 的稳定 item id。Finder / 本机 `ls`（含 `local-*`）不算拷完。细则见「暂存完成门」。


## 不要做的事

- 不要默认 `unlisted` / `private`（必须 **public**，除非用户当场改口）
- 不要把 Finder / 本机 `ls`（含 `local-*`）当成「拷完」；API 还空时不要把同一条成片再 `cp` 进「跑步成片」
- 不要在缺 `token.json` / 缺成片 / 缺 16:9 封面时硬传
- 不要因外挂字幕失败而回滚已公开的成片（字幕缺 scope 时可后补）

## 前置

1. 本期已 `upload: ready`：`~/Movies/running-content/YYYY-MM-DD-slug/upload/` 内有  
   - `<标题>.mp4`  
   - `cover-16x9-1920x1080.jpg`（缩略图用这张；**不是** 4×3）  
   - 可选 `subtitles.srt`
2. `plan.md` 已有标题 + YouTube / 通用简介文案
3. box 上已有可用 OAuth：`/workspace/youtube-upload/token.json`（含 **refresh_token**；上传前可强制 refresh）  
   - 常见 scope：`youtube.upload` + `youtube`；挂 captions 还要 **`youtube.force-ssl`**（缺了视频仍可 public，字幕接口会 403）
4. Google Drive 文件夹「跑步成片」可写（用户账号 / Drive 连接器）

## 上传顺序

成片（标题名烧字 `.mp4`）→ 设 16:9 封面（`thumbnails.set`）→ **`privacyStatus=public`**（不要默认 unlisted/private）。硬字幕已烧进成片；`subtitles.srt` 外挂**可选**（方便关字幕/无障碍；缺 scope 失败不挡公开）。

## 传输路径（默认）

```text
Mac upload/  →  Google Drive「跑步成片」/YYYY-MM-DD-slug/  （暂存 mp4 + 16:9 封面 + 可选 srt）
             →  box：Drive DownloadFile / 连接器下载到 /workspace/yt-stage/YYYY-MM-DD-slug/
             →  box：YouTube Data API resumable upload（public）
             →  成功后：Drive 本期暂存进废纸篓；写 episode.md YouTube 链
```

大文件整段经 Drive 下载到 box，不要从用户电脑把成片直拷进 box。

### 暂存完成门（硬门）

**Finder 或本机 `ls`「跑步成片」不算拷完。** 桌面版 Drive 里看得到，只说明本机在传。

1. **拷完**只认 Drive API `list` / `search` 返回本期 mp4，并带**稳定云端 item id**；体积对得上更好。
2. 本机 DriveFS 路径可见（Finder / `ls`，包括 `local-*` 占位）**不算完成**。
3. API 还是空的，**不要**把同一条成片再 `cp` 进「跑步成片」。上次第一条还在传，就撞出 `…2.mp4` / `…3.mp4`。
4. 默认路径始终是 Drive → `DownloadFile` → YouTube API。
5. 一期只暂存一份：`跑步成片/YYYY-MM-DD-slug/` 里已经有这条成片，就不要再拷。等 API id；要重来，先有意清掉再拷。
6. `stage_drive_chunks.py` 写完 `drive-stage` 之后，把 `logs/todo.md` 的 `drive` 标成 done。YouTube Data API 公开上传成功、拿到链接之后，再标 `youtube` done。Drive 没完成不能标 YouTube。禁止从 Mac 把成片 CopyToBox 分片。

## box 上传脚本模式

工作目录惯例：`/workspace/youtube-upload/`。

- `token.json` — OAuth（refresh 后写回；可镜像到 agent-data 备份路径）
- 当期暂存：`/workspace/yt-stage/YYYY-MM-DD-slug/`（`<标题>.mp4`、`cover-16x9-1920x1080.jpg`、可选 `subtitles.srt`）
- 脚本：`/workspace/youtube-upload/upload_episode.py`（或同目录等价脚本）  
  - 用当期路径/标题/简介/标签 **参数或临时改占位**，不要把上期文案留死在仓库 skill 里  
  - `MediaFileUpload(..., resumable=True, chunksize=8*1024*1024)`  
  - `videos.insert` → `thumbnails.set`（16:9）→ 可选 `captions.insert`  
  - 进度写 `upload_progress.json`，结果写 `upload_result.json`（含 `url` / `privacyStatus`）

元数据默认：

| 项 | 默认 |
| --- | --- |
| 标题 | `plan.md`「发这个」 |
| 简介 | `plan.md` YouTube / 通用简介 |
| 标签 | 从当期 `plan.md`「## 标签」里 **YouTube 标签** 那栏抄（由 `/p3-subs` 按字幕写好）；**不要**在本 skill 写死一套默认标签 |
| `categoryId` | `22`（People & Blogs）常见可用 |
| `privacyStatus` | **`public`** |
| 语言 | `zh-Hans`（defaultLanguage / defaultAudioLanguage） |

上传前确认视频文件存在且体积合理；跑完读 `upload_result.json`，确认 `privacyStatus=public` 与 `https://youtu.be/<id>`。

### 字幕

- 有 `subtitles.srt` 就试 `captions.insert`（语言 `zh-Hans`）
- 若 403 `insufficientPermissions` / 缺 **`youtube.force-ssl`**：记一笔，**视频照样 public**；告知用户可在 Studio 手挂或下次扩 scope 重授权
- 不要为字幕失败重新上传整片

## 记日志

`tools/publish/stage_drive_chunks.py` 在源文件位于 `upload/` 时会写 `drive-stage`；不在 `upload/` 时用 helper 补记。box 上的 YouTube 上传没有仓库脚本：开始 `start youtube-upload`，成功 `end`，失败 `fail`（`.venv/bin/python tools/log_timeline.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug`）。已有的行不要重复。

## 成功后

1. 把 `https://youtu.be/…` 写入该期 `episode.md`「发布」栏「YouTube：」（B 站仍空则 **不要** 改 `published`）
2. **立刻**把 Drive「跑步成片」里本期暂存的 mp4/封面/srt **进废纸篓**（文件夹可留空）
3. 清理 box 上 `/workspace/yt-stage/YYYY-MM-DD-slug/` 大文件（可留结果 json 备查）
4. 推当期 episode 分支；**只有 B+YT 双链都齐** 才轮到 `/p3-publish`（写齐、改 `published`、squash episode PR、复盘日志上 box、清临时）——那是 publish 的事，本 skill 不做

告诉用户：

> YouTube 已公开：`https://youtu.be/…`（缩略图/字幕若失败如实说）。  
> B 站仍空着时 `status` 保持 `edited`。双链齐了再 `/p3-publish`。  
> Drive「跑步成片」本期暂存已清。

## 翻车记录

- bot 云电脑浏览器打开 YouTube Studio 常 TLS 超时；**不要**靠 Studio 网页上传。Data API / googleapis 上传端点从 box 可达。
- 从 Mac 直调 API 曾能用，但违背「Mac 关机也能发」；用户已要求：**未经当场允许不得用其电脑传 YouTube**。
- 2026-11-06：Finder / `ls` 当成拷完，API 还空就再 `cp`，撞出 `…2.mp4` / `…3.mp4`。暂存完成只认 Drive API 的稳定 item id。
- captions 缺 `youtube.force-ssl` 时整片仍可 public；不要把字幕当成上传门闩。
