---
name: p3-qc
description: 只再核对一次成片。默认成片流程里抽帧核对已在 p3-assemble 里拼完立刻做。用户说再核对、抽帧、QC、审片、接缝不对时用。画面声音通过且已有校准字幕才把 episode status 改为 edited。
---

# 成片核对（补做 / 重做）

默认流程：核对跟拼接一起在 `p3-assemble` 里做。本 skill 只在要再抽一轮、或成片已在、当时没核对时用。

## 前置

制作期成片：`YYYY-MM-DD-run-final.mp4`（默认无烧字幕）。若已 upload-ready 改名，成片是标题原文 + `.mp4`；外挂仍是 `subtitles.srt`（不要找与成片同名的 `.srt`）。时间轴见 `p3-assemble`。外挂源稿在 `episodes/YYYY-MM-DD-slug/subtitles.srt`。

## 不要做的事

- 不要为了再核对去重拼成片，除非接缝或 HUD 本身有问题
- 字幕错只改 txt/SRT，不用重拼
- 不要从成片画面里找字幕帧（默认没烧字）

## 抽帧

至少这几处，写到媒体目录 `qc/`：

1. open 开头（应无 HUD）
2. open→run 接缝（HUD 刚出现）
3. 跑中 HUD 一帧（鞋名、气温 `°C`、配速）
4. run→close 接缝（HUD 应在叠化里消失）
5. close 结尾（无 HUD）

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
# 制作期用 run-final；改名后换成标题名 .mp4
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

## 字幕（外挂，叠上看）

```bash
# 制作期：
iina --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
# 改名后（外挂固定 subtitles.srt，不要找与标题同名的 .srt）：
# iina --mpv-geometry=320x180-8+8 --mpv-sub-file=.../subtitles.srt \
#   ~/Movies/running-content/YYYY-MM-DD-slug/<标题>.mp4
```

制作期成片旁边的 `YYYY-MM-DD-run-final.srt` 会自动挂上；改名后显式挂 `subtitles.srt`。不要推荐 ffplay。抽查：open 第一句、第一段 run 开头、各 run 接缝、close 第一句。看字是否跟嘴、两条会不会重叠、是不是单行。出点跟说完：气口后的短人声不要当成下一句的整句，正词开口时条子不能已经没了。入点略早可以，早收不行。

SRT 贴底栏，可能压 HUD。公开前用私密/不公开稿在网页播放器开 CC 看一眼。

## 清单

- 外挂时间以 `tools/subs/check_subs.py` 为准：机器过门（早收 ≤3% 可核对条、漏盖累计 ≤1% 成片、挂静音 ≤3% 可核对条，且严重早收 >0.5s 为 0）；机器过门后硬失败行仍须人听，**不能**仅凭比例过门就把字幕标成 done。本节抽听只看它报的噪声时段和接缝

- open / close 没有 HUD
- 成片画面里没有烧进去的字幕
- 外挂跟嘴、单行、不要太长；没有 `\N` 两行；用词跟口播，没有被改写成另一种说法
- 没有两条字幕叠在一起
- 没有把一个词组切成两条（上一条停在「的」「一个」，下一条接着补完）；单独一两个字的条子要是完整的词
- 跑鞋名和 `-sk` 与 `training/logs/shoes.md` 一致
- 天气是「数字°C / 数字°C」，不是方框 `℃`
- 没有明显降码、花屏、音画不同步

画面声音通过后：`assets.md` 制作状态 `qc: done`。已有校准字幕才把 `episode.md` 改为 `edited`。

失败则指出该重跑哪个 skill：鞋错 → `p3-hud`；字幕错 → 改 txt/SRT，**不用重拼**；接缝错 → 查 open/close 是否被当成 run。

## 完成后

还没有字幕：`/p3-subs`。已有校准字幕：不要再推荐制作 skill，发布按 `p3-subs`。
