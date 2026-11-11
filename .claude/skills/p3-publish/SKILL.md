---
name: p3-publish
description: 发布收尾：用户给齐 B 站 + YouTube 链接后写 episode 发布栏、status=published、该期 episode PR squash 合 main；接着把制作复盘日志 CopyToBox 到 bot 长期留存；再列清临时 KEEP/DELETE（体积）→ 人确认 → 进废纸篓。抖音短链不挡 published，随后写入。用户说发布完毕、发完了、已发布、写链接、合 episode PR、清临时时用。满 7 天整夹归档见 p3-archive。
---

# 发布

烧字 / upload-ready 之后：**写双链 → `published` → squash 合本期 episode PR → 复盘日志上 box → 清临时**。

## 不要做的事

- 不要在缺 B 站或 YouTube 任一链接时写 `published` 或合 PR
- 不要用抖音是否已发来挡 `published`（抖音短链随后补）
- 不要在用户确认前删任何临时文件
- 清临时禁止 `rm` / `rm -rf`；只进废纸篓
- 不要整夹删媒体目录；满 7 天搬盘走 `p3-archive`
- `published` 之后必须把复盘日志拷上 box
- 复盘目录不要放视频、FIT、封面、原片

## 前置

通常已走完 `final_export.py`，并完成最终片人工核对。用户说「没问题了 / 可以发了」时可先给上传清单；真正写链接与清临时要等双链到手。

## 上传清单（用户说可以发了时给）

从 `plan.md` 抄标题、封面句、简介。最终导出文件改名与外挂文件名按 `upload/` 现有打包规则处理；不要重新编码成片。

核对：
- `upload/` 已有：标题烧字 `.mp4`、三封面（4:3→3:4→16:9）、`subtitles.srt`（`pack_upload.py` 打好）
- 自动上传走 `/p3-bilibili`、`/p3-youtube`
- `status` 在 **B 站 + YouTube 双链齐**之前仍为 `edited`

**抖音（第三平台，不挡 `published`）**：成片用 `upload/` 里那份；正文从 `plan.md`「抖音」栏抄，话题在发布页点选（≤5）。短链随后写 `episode.md`「抖音：」。

还要短视频才提 `/p3-jianying`。

## 双链齐 → published → 合 PR

触发：用户说「发布完毕 / 发完了 / 已发布」之类，并且同时给了 **B 站 BV（或完整 B 站链接）** 和 **YouTube 链接**。顺序：

1. 写两边链接进 `episode.md`「发布」栏，`status=published`
2. **立刻合并该期 episode PR 进 `main`**（squash；可删远程分支）；不要等用户再点合
3. **复盘日志上 box**（下一节，必做；不要等清临时确认）。拷完立刻 `/p3-publish-report`
4. 再按下文列清临时清单（体积）→ 用户确认 → 进废纸篓（禁止 `rm`）

抖音短链不挡本步；有了再补写「抖音：」。

合 PR：Cursor GitHub 插件若 403，改用本机 `gh pr merge --squash`（用户已登录）。**只自动合 episode 内容 PR**；skill / 工具类 PR 仍等用户合。

## 复盘日志上 box（published 之后必做）

双链和 `published` 写上之后马上做。episode PR 能合就先合完再拷；合不了也要拷，不要干等。清临时要等用户点头，这一步不要等。只留文本和小文件，方便以后在 box 上翻这期怎么做的。

Mac 上的文件用 **CopyToBox** 送到 box。已经在 box 上的 YouTube 上传记录，在 box 本地拷，不要再从 Mac 传一遍。

两处内容保持一致。先写长期目录，再镜像到浏览路径（本期目录 + 根上的 `INDEX.md`）。浏览路径若已是长期目录的链接，写一处即可。

- 长期：`/cursor/stores/store-96d3cec6-b662-4113-b5c5-90eebd57a3c8/running-retrospect/<YYYY-MM-DD-slug>/`
- 浏览：`/workspace/running-retrospect/<YYYY-MM-DD-slug>/`

| 来源 | 放到 | 说明 |
| --- | --- | --- |
| 媒体 `logs/timeline.txt`、`logs/failures.md` | `<slug>/logs/` | 文件在就必拷 |
| `logs/` 里其它小文件 | `<slug>/logs/` | 有用就带；跳过 `.pid` |
| 本期 `episode.md`、`plan.md`；`assets.md` 不大也带 | `<slug>/episode-repo/` | 拷的是刚写上 `published` 的那份 |
| box `/workspace/youtube-upload/` 的 `upload_result.json`，以及同目录 `upload_progress.json`、`upload_run*.log` | `<slug>/youtube-upload/` | 用结果里的 `url` / `title` 对一下本期；没有或不是本期就跳过 |

没有 `logs/`：在 INDEX 记 missing，继续后面的清临时。`timeline.txt` / `failures.md` 或 `episode.md` / `plan.md` 明明在、却没传上：重试，并写进 `INDEX.md` 末尾 Copy failures；没成功不要当这步做完。

两处 `INDEX.md` 按现有几行补本期：slug、标题、`published`、双链、logs 拷了什么或 missing、youtube-upload 有无、episode-repo 有哪些文件。顺手改顶部同步日期。

清临时不要动 `logs/`。本地日志留着，满 7 天随整夹走 `p3-archive`。

## 发布后清临时文件

媒体目录：`~/Movies/running-content/YYYY-MM-DD-slug/`。

### 保留（KEEP）

| 保留 | 说明 |
| --- | --- |
| 原片 | `open-raw` / `run-*` / `close-raw`；若没有 `*-raw` 变体，则保留剪过的 `open` / `close` 当作原片 |
| 成片 | **仅一份**：`upload/<标题>.mp4`；根目录不要再留同名成片；勿留 `*-no-burn` / 额外 `run-final` |
| 封面 / 外挂 | `upload/` 内三封面（4:3→3:4→16:9）+ `subtitles.srt`；根目录若仍有同名，须为硬链（同 inode），勿再 copy 一份 |
| 媒体字幕产物 | 制作期 `YYYY-MM-DD-run-final.srt`、烧字 `subtitles.ass` |
| 封面自拍原图 | 媒体目录里的自拍源照片（非 `cover-*.jpg`） |
| 数据 | FIT、`weather-hourly.json`、`stats-*.jpg` |
| `logs/` | 制作日志。复盘已拷到 box；本地留到满 7 天归档，清临时不删 |

仓库只保留 `subtitles.txt`，清理媒体临时文件时不要改它。跑鞋账本一律不动。

### 删除（DELETE）

缺了就跳过，不要报错停住：

| 删 | 说明 |
| --- | --- |
| `*-no-burn.mp4` | 无字幕备份；**永远不留**。烧字成片定稿/改名后立刻进废纸篓，不必等抖音 |
| 多余 `YYYY-MM-DD-run-final.mp4` | 已有标题烧字成片时的旧名/无字幕备份 |
| `*-run-final-pre-*.mp4` | 拼片备份（冷开场前、修剪前等） |
| `close-stats` 等渲染中间件 | 叠了数据的 close 中间件、其它可再生成的渲染产物 |
| 剪过的 `open` / `close` | **仅当**已有对应 `open-raw` / `close-raw` 时删；没有 `-raw` 则上面 KEEP 已要求保留 |
| `hud-renders/` | HUD preview / 透明层；可再跑 `p3-hud` |
| `asr/` | 转写中间产物 |
| `qc/` | 抽帧核对图 |
| `cover-candidates/` | 封面候选帧 |
| `cold-open/` | 冷开场中间件 |
| `*.bak`、`.DS_Store` | 备份后缀与系统垃圾 |

### 流程（PROCESS）

1. **先列清单再动手。** 用 `du -sh` / `ls -lh` 列出拟删项与拟留项及体积，报给用户确认。用户没明确同意前不要删。
2. **进废纸篓，禁止 `rm`。** 在 macOS 上把确认要删的路径 **move 进废纸篓**（`mv … ~/.Trash/`，或已安装的 `trash` CLI）。同名冲突时先改名再移入。
3. 清完把实际移入废纸篓的路径与腾出的体积报给用户。
4. 这里**不要**整夹归档或删掉整个媒体目录；满 7 天整夹搬走走 `p3-archive`。

## 记日志

`pack_upload.py` 会写 `pack-upload`。写上 `published` 时用 `.venv/bin/python tools/log_timeline.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug start published`，再 `end`。脚本或 helper 已写的行不要重复；失败用 `fail`。

## 完成后

> 双链已写、`published`、episode PR 已 squash 进 main。复盘已在 box：`running-retrospect/<YYYY-MM-DD-slug>/`（logs / episode-repo / youtube-upload 有或无，如实说；传失败不要说成已同步）。清临时清单如下，确认后进废纸篓。
>
> （列出 KEEP / DELETE + 体积）
