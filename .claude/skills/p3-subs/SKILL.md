---
name: p3-subs
description: 字幕支路：faster-whisper large-v3-turbo 转写（忠于原句）→ 初稿停下等人改字（同时并行跑 HUD 透明层与响度测量）→ force_align → check_subs → 用户确认后出 SRT 并写 plan.md 简介/抖音/标签。用户说字幕、转写、whisper、对口型、改字幕时用。没有审片清单先走 p3-assemble。
---

# 字幕（忠于原句）

识别稿只提供时间和草稿。**校正不是润色**：字必须跟嘴里说的走，切条只断开不改字。本步遵守 `p3-episode` 的全局协议（进度门闩、墙钟日志、不自动开播放器/编辑器）。

**读源码门槛：** 默认只调脚本看退出码；只有改算法、排错或解释切法时才读 `tools/subs/` 源码。

## 不要做的事

- 不要用 `talk.md` / `script.md` 估时间、改口播用词或写简介
- 不要换一种表达、压缩口语/口头禅（「完全」「其实」「大概」等），或自己加括号注释；**用户手改加的括号注释必须原样保留**
- 不要把一段识别起止按字数均分给多条字幕；对不上的交给 `force_align.py` 报出给人听
- 不要用 tiny / small（只用 `large-v3-turbo`）；不要在这里烧字或修响度
- 不要为了转写去拼 `review-preview.mp4`；没有对得上当前时间表的 wav 就停

## 前置与依赖

- 需要 `logs/program.json` 和 `YYYY-MM-DD-review-preview.edl`（缺则先 `/p3-assemble`）。对口型前必须冻结时间表（`program_edl.py freeze`，`force_align.py` 也会自动冻）。若冻后改了刀点导致 `subs_stale`，必须用对得上新表的 wav 重跑对齐。
- 首次依赖：`.venv/bin/pip install -r tools/subs/requirements.txt`（模型自动从 ModelScope 拉到 `~/Movies/running-content/.models/faster-whisper-large-v3-turbo/`）。
- **先在 `episode.md` 填好 `专名：`**（顿号分隔），脚本会自动读作识别提示；不要拿它改用词。

## 阶段一：转写、校正与初稿停门

1. **转写初稿**（`--audio` 传当前时间表的 16k 单声道 wav，如 `asr/YYYY-MM-DD-run-final.wav`；不要覆盖 `asr/*.words.json` 与 `asr/draft-*.srt`）：
   ```bash
   .venv/bin/python tools/subs/draft_subs.py \
     --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav \
     --txt episodes/YYYY-MM-DD-slug/subtitles.txt
   ```
   产物唯一源稿：`episodes/YYYY-MM-DD-slug/subtitles.txt`（单行格式 `0:00:00.00–0:00:02.44  正文`，横屏底栏有 HUD 严禁两行）。跑完核对 `logs/todo.md`（`subs: waiting-review`）。
2. **最小校正**：只修正明显听错（专名、配速/心率数字、繁体残形、同音错字如 寄/计、帧/针、的/得/地、在/再、做/作、象/像）。没听清留原句或标「听不清」，绝不润色。
3. **初稿自检切条（必做）**：读取 [split-checklist.md](references/split-checklist.md)，按 6 条易错规则逐条扫并只改切分不改字。
4. **立刻停门 + 并行准备**：写完 `subtitles.txt` 立刻停（`assets.md` 写 `subs: waiting-review`），**不要对口型、不要写简介、不要自动打开编辑器或播放器**。同时**立刻并行启动**冻结后的 HUD 透明层与响度测量，别等字幕校验：
   ```bash
   .venv/bin/python tools/hud/render_running_hud.py \
     --media-dir ~/Movies/running-content/YYYY-MM-DD-slug --prep-alpha -j 6
   .venv/bin/python tools/assemble/final_export.py \
     --media-dir ~/Movies/running-content/YYYY-MM-DD-slug --measure-only
   ```
   跑完核对 `logs/todo.md`（`hud-render: done`、`loudness-measure: done`，`subs` 仍为 `waiting-review`）。发给用户：
   > 切条已按易错规则扫过。这一轮改错字和换行即可，优先动 `episodes/YYYY-MM-DD-slug/subtitles.txt`，时间先别动。要不要打开这份 txt 和审片预览？改好了直接发：
   >
   > `改好了`

## 阶段二：用户说「改好了」→ 对口型与确认

1. **强制对齐**（只改时间、不改字；`interp`/`unanchored` 必须对着音频核对）：
   ```bash
   .venv/bin/python tools/subs/force_align.py \
     --txt episodes/YYYY-MM-DD-slug/subtitles.txt \
     --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav
   ```
   跑完核对 `logs/todo.md`（`subs: aligned`）。
2. **质检门**：
   ```bash
   .venv/bin/python tools/subs/check_subs.py \
     --subs episodes/YYYY-MM-DD-slug/subtitles.txt \
     --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav
   ```
   机器过门 ≠ 可写 `confirmed`：硬失败行必须列给人听（未经同意不开播放器）；`check_subs.py` 报用户手加括号时保留。
3. **用户明确确认后落账**：改 `assets.md` 为 `subs: done`、`episode.md` 为 `status: edited`，并执行（agent 禁止擅自加 `--confirmed`）：
   ```bash
   .venv/bin/python tools/todo_list.py \
     --media-dir ~/Movies/running-content/YYYY-MM-DD-slug mark subs confirmed --confirmed
   ```
4. **生成外挂 SRT**（分类目录写进 `upload/subtitles.srt`，并按 `preview/*.edl` 同名同步 sidecar `.srt`；旧平铺期写根；勿在烧字成片旁留同名 `.srt`）：
   ```bash
   .venv/bin/python tools/subs/txt_to_subs.py \
     --txt episodes/YYYY-MM-DD-slug/subtitles.txt --media-dir auto
   ```
5. **写 `plan.md` 简介、抖音文案与标签**：读取 [plan-copywriting.md](references/plan-copywriting.md)，严格按校准后的 `subtitles.txt` 写入 `plan.md`。

## 记日志

`draft_subs.py` 自动写 `draft-subs`，`force_align.py` 自动写 `force-align`；未跑脚本的手做步骤用 `tools/log_timeline.py` 补。

## 完成后（字幕已 confirmed）

> 下一步走最终导出：`final_export.py --confirmed`（缺的透明层或响度会自动补齐）。还要 60–90 秒短视频才提 `/p3-jianying`。
