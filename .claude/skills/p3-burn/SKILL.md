---
name: p3-burn
description: 烧字收尾：字幕定稿且响度就绪后，从 SRT 生成 ASS，用 assemble_episode.py --ass 烧进最终片；处理 no-burn 备份与发布前改名。用户说烧字、硬字幕、--ass、最终片、upload-ready 改名时用。不要在字幕未定稿或响度未完成时烧。拼画面走 p3-assemble；字幕走 p3-subs；响度走 p3-loudness。
---

# 烧字

**字幕定稿（`subs: done`）+ 响度就绪（`loudness: done`）之后**的收尾：把硬字幕烧进最终发布片。不要提前烧，也不要把烧字写进拼画面或字幕校对主流程。

```text
总序：拼画面 p3-assemble →（字幕 p3-subs ∥ 响度 p3-loudness）→ 烧字 本 skill
```

## 职责 / 输入 / 输出

| | |
| --- | --- |
| **职责** | 生成 ASS → `--ass` 烧字 → 抽烧字帧 → 清 `*-no-burn` → 可选 upload-ready 改名 |
| **输入** | 定稿 `episodes/.../subtitles.srt`（及 txt）；已响度的 `YYYY-MM-DD-run-final.mp4` |
| **输出** | 烧字最终片（同名覆盖或随后改成标题名）；`subtitles.ass`；`assets.md`：`burn: done` / `upload: ready` |
| **实现** | `assemble_episode.py --ass ...`（**保留响度链**，不要 `--no-loudness-fix`） |

平台仍可另挂 `subtitles.srt`（B 站创作中心只收 SRT）。不要把字幕轨 mux 进 mp4（平台转码会丢掉）；烧字用滤镜。

## 不要做的事

- 不要在 `waiting-review` / 响度未完成时烧最终片
- 不要加 `--no-loudness-fix`（烧字这次必须带响度链）
- 不要长期保留 `*-no-burn.mp4`：烧字定稿/改名后立刻进废纸篓，不必等抖音
- 不要在这里重做切条或 force_align（回 `p3-subs`）
- 不要在这里重拼画面转场逻辑以外的「再发明」；调用现有 assemble 入口即可

## 前置

- `p3-subs`：`subs: done`（用户确认改好了 / 可以了）
- `p3-loudness`：`loudness: done`（或成片已确认过响度链实测）
- 缺哪条补哪条；两者曾并行，烧字闸门要两边都齐

## 步骤

1. **生成 ASS**（Style 默认如下；Fontname 须系统真选中 Heavy，勿只靠 fontsdir）

   **ASS Style（烧字默认，非 HUD）**
   - Font：`Source Han Sans SC Heavy`（`SourceHanSansSC-Heavy.otf`；仓库 `tools/hud/fonts/` 可复用）
   - 1080p：`Fontsize=72`、`Outline=3`、`MarginV≈100`；单行底中，避开左栏 HUD
   - Mac：otf 装入 `~/Library/Fonts`（或配 FONTCONFIG）；CoreText 常因只靠 fontsdir 落到 PingFang SC Regular

   写出 `episodes/YYYY-MM-DD-slug/subtitles.ass`，并拷到媒体目录。

2. **烧字**（可短暂把无烧字片挪成 `YYYY-MM-DD-run-final-no-burn.mp4`）

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
# 可选：mv "$MEDIA/YYYY-MM-DD-run-final.mp4" "$MEDIA/YYYY-MM-DD-run-final-no-burn.mp4"

nohup .venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir "$MEDIA" \
  --ass episodes/YYYY-MM-DD-slug/subtitles.ass \
  > "$MEDIA/burn.log" 2>&1 &
# 保留响度链：不要 --no-loudness-fix
```

3. **抽烧字帧**核对：底中、Heavy 72、不挡左栏 HUD；再测最终片 I/TP（应仍约 −16 / ≤ −1.5）。

4. **立刻处理 no-burn**：烧字成片定稿（或已按标题改名）后，把 `*-no-burn.mp4` **进废纸篓**（禁止 `rm`），永远不留，不必等抖音。媒体目录同步 `subtitles.ass`；外挂 `subtitles.srt` 仍保留。

5. `assets.md` 写 `burn: done`（附 ASS 样式与实测）。

## 发布前改名（upload-ready）

用户说可以发了、要准备上传时（通常烧字之后）：

1. **只改成片名**：`YYYY-MM-DD-run-final.mp4` 原地改为 `plan.md` / `episode.md` 标题原文 + `.mp4`。
2. **不要改字幕文件名**；上传外挂始终 `subtitles.srt`。
3. 文件名保留标题全部标点（含 `|`、`？`、空格）；不要把 `|` 换成 `-`。
4. 备份（`*-pre-coldopen` 等）改名阶段保留原名；发布后清临时见 `p3-subs`「发布后清临时文件」。
5. `assets.md` 加 `upload: ready`。`episode.md` 仍为 `edited`，双链齐了才 `published`。

简介、抖音文案、发布后清临时文件的 KEEP/DELETE 真源仍在 `p3-subs`。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 最终片没有字 | 漏传 `--ass`；或 ASS Style/MarginV 压 HUD |
| 字重不对（变细） | Fontname 未真选中 Heavy，只靠 fontsdir |
| 烧完音量不对 | 误加了 `--no-loudness-fix` |
| 字幕轴错位 | 冷开场/重拼后未 +offset 或未重对齐（回 `p3-subs`） |

## 完成后

> 用户说「没问题了 / 可以发了」再给上传清单（标题名成片 + `subtitles.srt`）。清临时与双链 `published` 按 `p3-subs`。
