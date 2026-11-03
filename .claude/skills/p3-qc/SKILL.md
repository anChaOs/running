---
name: p3-qc
description: 只再核对一次成片。默认成片流程里抽帧核对已在 p3-assemble 里拼完立刻做。用户说再核对、抽帧、QC、审片、接缝不对时用。只写 `qc: done`；episode status 的 `edited` 由 p3-subs 在用户确认字幕后写。
---

# 成片核对（补做 / 重做）

默认核对跟拼接在 `p3-assemble` 里做完。本 skill 只在要再抽一轮、或成片已在但当时没核对时用。

## 前置

制作期成片：`YYYY-MM-DD-run-final.mp4`。改名与外挂文件名见 `p3-burn`；时间轴见 `p3-assemble`。外挂源稿在 `episodes/.../subtitles.srt`。

## 不要做的事

- 不要为了再核对去重拼成片，除非接缝或 HUD 本身有问题
- 字幕错只改 txt/SRT，不用重拼
- 不要从成片画面里找字幕帧（默认没烧字）

## 抽帧

**画面抽帧点与清单真源：`p3-assemble`「核对」。** 本 skill 按那份再抽一轮；制作期用 `run-final`，改名后用标题名 `.mp4`（改名规则见 `p3-burn`）。

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

## 字幕（外挂，叠上看）

下面的 IINA 命令发给用户，**用户同意才执行**，agent 不要自己打开播放器。不要推荐 ffplay。

```bash
# 制作期（旁边的 YYYY-MM-DD-run-final.srt 会自动挂上）：
iina --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
# 改名后显式挂 subtitles.srt，不要找与标题同名的 .srt：
# iina --mpv-geometry=320x180-8+8 --mpv-sub-file=.../subtitles.srt \
#   ~/Movies/running-content/YYYY-MM-DD-slug/<标题>.mp4
```

抽听：open 第一句、第一段 run 开头、各 run 接缝、close 第一句。出点跟说完：气口后的短人声不要当成下一句的整句；正词开口时条子不能已经没了。入点略早可以，早收不行。

SRT 贴底栏，可能压 HUD。公开前用私密/不公开稿在网页播放器开 CC 看一眼。

## 清单

- **画面 / HUD / 接缝 / 鞋名 / 气温：** 按 `p3-assemble` 核对清单
- 外挂时间以 `tools/subs/check_subs.py` 为准：早收 ≤3% 可核对条、漏盖累计 ≤1% 成片、挂静音 ≤3% 可核对条，且严重早收（>0.5s）为 0。机器过门后硬失败行仍须人听。本节抽听只看它报的噪声时段和接缝
- 成片画面里没有烧进去的字幕（烧字后的核对见 `p3-burn`）
- 外挂跟嘴、单行；没有 `\N` 两行；用词跟口播
- 没有两条字幕叠在一起；词组不要切碎

画面声音通过后：`assets.md` 写 `qc: done`。`episode.md` 的 `edited` 只由 `p3-subs` 在用户确认字幕后写，这里不改。

失败：鞋错 → `p3-hud`；字幕错 → 改 txt/SRT，**不用重拼**；接缝错 → 查 open/close 是否被当成 run。

## 完成后

还没有字幕：`/p3-subs`（可与 `/p3-loudness` 并行）。字幕+响度都齐未烧字：`/p3-burn`。已烧字：发布与清临时走 `/p3-publish`。
