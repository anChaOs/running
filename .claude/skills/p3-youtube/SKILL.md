---
name: p3-youtube
description: 把本期 upload/ 成片经 Google Drive「跑步成片」暂存到 bot 云电脑，再用 YouTube Data API 公开上传（16:9 封面）。用户说 YouTube 上传、自动发 YouTube、传 YT 时用。独立于 p3-publish：本 skill 只上传拿链接；写双链 / published / 合 PR / 清临时仍走 p3-publish。默认禁止从用户 Mac 调 YouTube API / Studio 上传。
---

# YouTube 自动上传（Drive → box → Data API）

本 skill **只上传**，不写 `published`、不合 PR、不清临时。成片必须能在 **用户 Mac 关机** 时仍传得上去：上传动作只发生在 **bot 云电脑（box）**。

## 硬规则（不要破）

1. **默认禁止**从用户 Mac（或任何注册用户电脑）跑 YouTube Data API / Studio 上传。除非 **安超当场明确允许**「这次可以用我电脑传 YouTube」。
2. **唯一默认路径：** Mac（或已有成片处）→ 暂存到 Google Drive 文件夹 **「跑步成片」** → bot 用 Drive 下载到 **box** → 在 box 上 YouTube Data API **resumable** 上传，`privacyStatus=public`。
3. 上传成功后：**清空本期**在「跑步成片」里的暂存成片/封面（进废纸篓即可）；文件夹本身可留空给下期。


## 不要做的事

- 不要默认 `unlisted` / `private`（必须 **public**，除非用户当场改口）
- 不要把 ~2G 成片默认拆成多片 `CopyToBox` 从 Mac 拷进 box（慢、占用户机；仅当 Drive 暂存丢失且用户允许时的应急，见下）
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

大文件走 Drive，**不要**默认 Mac→box 直拷。`CopyToBox` 单文件常有约 **100MiB** 上限；整段成片应整文件经 Drive。

### 应急 fallback（仅当 Drive 里没有本期 mp4）

若「跑步成片」暂存失败/被清掉、又必须继续：可经用户同意后，把成片 **分片** `CopyToBox` 到 box 再拼接。注意：

- 这仍占用用户 Mac 做传输；速度可能只有约 0.4–0.5 MB/s，2G 级要很久
- **仍不是**在 Mac 上调 YouTube API；API 上传必须留在 box
- 拼完校验体积/时长后再传；用完删 box 临时分片

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

## 成功后

1. 把 `https://youtu.be/…` 写入该期 `episode.md`「发布」栏「YouTube：」（B 站仍空则 **不要** 改 `published`）
2. **立刻**把 Drive「跑步成片」里本期暂存的 mp4/封面/srt **进废纸篓**（文件夹可留空）
3. 清理 box 上 `/workspace/yt-stage/YYYY-MM-DD-slug/` 大文件（可留结果 json 备查）
4. 推当期 episode 分支；**只有 B+YT 双链都齐** 才轮到 `/p3-publish`（写齐、改 `published`、squash episode PR、清临时）——那是 publish 的事，本 skill 不做

告诉用户：

> YouTube 已公开：`https://youtu.be/…`（缩略图/字幕若失败如实说）。  
> B 站仍空着时 `status` 保持 `edited`。双链齐了再 `/p3-publish`。  
> Drive「跑步成片」本期暂存已清。

## 翻车记录

- bot 云电脑浏览器打开 YouTube Studio 常 TLS 超时；**不要**靠 Studio 网页上传。Data API / googleapis 上传端点从 box 可达。
- 从 Mac 直调 API 曾能用，但违背「Mac 关机也能发」；用户已要求：**未经当场允许不得用其电脑传 YouTube**。
- Drive 暂存丢失时用过 Mac 分片 `CopyToBox`（约 90MB/片）再拼接——仅应急，默认仍走 Drive `DownloadFile`。
- captions 缺 `youtube.force-ssl` 时整片仍可 public；不要把字幕当成上传门闩。
