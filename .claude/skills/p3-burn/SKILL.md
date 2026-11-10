---
name: p3-burn
description: 烧字收尾：字幕定稿且响度就绪后，从 SRT 生成 ASS，用 burn_ass.py 烧进最终片（不重拼）；处理 no-burn 备份与发布前改名。用户说烧字、硬字幕、--ass、最终片、upload-ready 改名时用。
---

# 烧字

**`subs: done` + `loudness: done` 之后**：生成 ASS → `burn_ass.py` 烧字 → 抽烧字帧 → 清 `*-no-burn` → 可选 upload-ready 改名。平台仍可另挂 `subtitles.srt`；不要把字幕轨 mux 进 mp4。

入口：`tools/assemble/burn_ass.py`（单文件进、单文件出；**`-c:a copy`**，视频重压一次）。不要为了烧字再跑 `assemble_episode.py --ass`（会全量重拼并抹冷开场）。

## 不要做的事

- 不要在 `waiting-review` / 响度未完成时烧最终片
- 不要为了烧字全量 assemble
- 不要长期保留 `*-no-burn.mp4`：烧字定稿/改名后立刻进废纸篓，不必等抖音
- 不要在这里重做切条或 force_align（回 `p3-subs`）

## 前置

- `subs: done`
- `loudness: done`（拼时带响度或已跑 `/p3-loudness`）

## 步骤

1. **生成 ASS**（Style 默认如下；Fontname 须系统真选中 Heavy，勿只靠 fontsdir）

   **ASS Style（烧字默认，非 HUD）**
   - Font：`Source Han Sans SC Heavy`（`SourceHanSansSC-Heavy.otf`；仓库 `tools/hud/fonts/` 可复用）
   - 1080p：`Fontsize=72`、`Outline=3`、`MarginV≈100`；单行底中，避开左栏 HUD
   - Mac：otf 装入 `~/Library/Fonts`（或配 FONTCONFIG）；CoreText 常因只靠 fontsdir 落到 PingFang SC Regular

   写出 `episodes/YYYY-MM-DD-slug/subtitles.ass`（本地导出，`.gitignore`，不要提交），并拷到媒体目录。git 里的字幕源仍是 `subtitles.txt`。

2. **烧字**（可短暂把无烧字片挪成 `YYYY-MM-DD-run-final-no-burn.mp4`）

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
# 可选：mv "$MEDIA/YYYY-MM-DD-run-final.mp4" "$MEDIA/YYYY-MM-DD-run-final-no-burn.mp4"

nohup .venv/bin/python tools/assemble/burn_ass.py \
  --media-dir "$MEDIA" \
  --ass episodes/YYYY-MM-DD-slug/subtitles.ass \
  > "$MEDIA/burn.log" 2>&1 &
```

3. **抽烧字帧**核对：底中、Heavy 72、不挡左栏 HUD；再听一遍（音轨应未改）。

4. **立刻处理 no-burn**：烧字成片定稿（或已按标题改名）后，把 `*-no-burn.mp4` **进废纸篓**（禁止 `rm`）。媒体目录同步 `subtitles.ass`；外挂 `subtitles.srt` 仍留在媒体目录。这两份都不进 git。

5. `assets.md` 写 `burn: done`（附 ASS 样式）。

## 发布前改名（upload-ready）

用户说可以发了、要准备上传时（通常烧字之后）：

1. **只改成片名**：`YYYY-MM-DD-run-final.mp4` 原地改为 `plan.md` / `episode.md` 标题原文 + `.mp4`。
2. **不要改字幕文件名**；上传外挂始终 `subtitles.srt`。
3. 文件名保留标题全部标点（含 `|`、`？`、空格）；不要把 `|` 换成 `-`。
4. **打包 `upload/`**：改名后立刻跑 pack（标题成片 **move** 进 `upload/`，禁止 copy；封面与 `subtitles.srt` 硬链，失败才 copy 小文件）：

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
.venv/bin/python tools/publish/pack_upload.py --media-dir "$MEDIA"
# 缺文件或认不出标题 mp4 时非 0；可加 --title-mp4 "标题.mp4"
```

5. 备份（`*-pre-coldopen` 等）改名阶段保留原名；发布后清临时见 `p3-publish`。
6. `assets.md` 加 `upload: ready`（`upload/` 已齐）。`episode.md` 仍为 `edited`，双链齐了才 `published`。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 最终片没有字 | 漏传 `--ass`；或 ASS Style/MarginV 压 HUD |
| 字重不对（变细） | Fontname 未真选中 Heavy，只靠 fontsdir |
| 字幕轴错位 | 冷开场后未 +offset 或未重对齐（回 `p3-subs`） |
| 冷开场消失 | prepend 后又跑了全量 assemble（烧字请用本脚本） |

## 完成后

> 用户说「没问题了 / 可以发了」走 `/p3-publish`。
