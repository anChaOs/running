# 发布后清临时文件清单

`published` 之后准备清理 `~/Movies/running-content/YYYY-MM-DD-slug/` 时按需加载。

## 保留（KEEP）

| 保留 | 说明 |
| --- | --- |
| 原片 | `open-raw` / `run-*` / `close-raw`；若没有 `*-raw` 变体，则保留剪过的 `open` / `close` 当作原片 |
| 成片 | **仅一份**：`upload/<标题>.mp4`；根目录不要再留同名成片；勿留 `*-no-burn` / 额外 `run-final` |
| 封面 / 外挂 | `upload/` 内三封面（4:3→3:4→16:9）+ `subtitles.srt`；根目录若仍有同名，须为硬链（同 inode），勿再 copy 一份 |
| 媒体字幕产物 | 上传用 `subtitles.srt`。不要在烧字成片旁边留 `*-run-final.srt` |
| 审片播放清单 | `YYYY-MM-DD-review-preview.edl` 留下 |
| 封面自拍原图 | 媒体目录里的自拍源照片（非 `cover-*.jpg`） |
| 数据 | FIT、`weather-hourly.json`、`stats-*.jpg` |
| `logs/` | 制作日志。已同步到 Google Drive `running-retrospect/`；本地留到满 7 天归档，清临时不删 |
| `publish-report.html` | 发布报告，在素材目录。清临时不删 |

仓库只保留 `subtitles.txt`，清理媒体临时文件时不要改它。跑鞋账本一律不动。

## 删除（DELETE）

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
| `cover-candidates/` / `cover-work/` | 封面候选帧与抠图工作目录 |
| `cold-open/` | 冷开场中间件 |
| `yt-drive-chunks/` | Drive 分块本地暂存工作目录 |
| `YYYY-MM-DD-review-preview.srt` | 审片清单旁的外挂。用户说留下才留 |
| 其它预览旁路 | 旧的 `*-review-preview.mp4` 等可再生成的预览片。`YYYY-MM-DD-review-preview.edl` 不在此列 |
| `*.bak`、`.DS_Store` | 备份后缀与系统垃圾 |

## 流程（PROCESS）

1. **先列清单再动手。** 用 `du -sh` / `ls -lh` 列出拟删项与拟留项及体积，报给用户确认。`YYYY-MM-DD-review-preview.edl` 放在 KEEP。用户没明确同意前不要删，也不要标 `cleanup: done`。列完核对 `logs/todo.md`（`published: done`，`cleanup: pending`）。
2. **进废纸篓，禁止 `rm`。** 在 macOS 上把确认要删的路径 **move 进废纸篓**（`mv … ~/.Trash/`，或 `trash` CLI）。同名冲突时先改名再移入。
3. 清完把实际移入废纸篓的路径与腾出的体积报给用户，然后 `todo_list.py mark cleanup done` 并核对 `logs/todo.md`。
4. 这里**不要**整夹归档或删掉整个媒体目录；满 7 天整夹搬走走 `p3-archive`。
