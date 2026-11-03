---
name: p3-loudness
description: 响度补跑：对已有 run-final 只改音轨（-c:v copy + 默认响度链，约 −16 LUFS / ≤ −1.5 dBTP）。优先在 p3-assemble 拼时带响度；本 skill 仅拼时关了响度才用。可与 p3-subs 并行。用户说响度、loudnorm、LUFS、音量定稿时用。
---

# 响度

成片画面已拼好之后，把音量修到发布目标：**I=−16 LUFS**，**TP=−1.5 dBTP**；不要整轨 flat gain。

入口：`tools/assemble/loudness_only.py`（**`-c:v copy`**，不重拼 open/HUD/close）。拼时已带响度（`loudness: done`）则**跳过**。

## 不要做的事

- 拼时已带响度就不要再跑本步
- 不要为了响度再跑 `assemble_episode.py`（会全量重拼，冷开场 bumper 会被抹掉）
- 不要在这里加 `--ass`
- 不要整轨 flat gain
- 不要在这里写字幕稿或改切条

## 前置

`assemble: done`，且还没有 `loudness: done`。没有成片先 `/p3-assemble`（推荐直接拼时带响度）。

## 步骤

建议先备份未修响度副本，再覆盖 `run-final`：

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
cp "$MEDIA/YYYY-MM-DD-run-final.mp4" "$MEDIA/YYYY-MM-DD-run-final-pre-loudnorm.mp4"

nohup .venv/bin/python tools/assemble/loudness_only.py \
  --media-dir "$MEDIA" \
  > "$MEDIA/loudness.log" 2>&1 &
```

与拼片同款响度链（默认两遍 loudnorm）。强制单遍加 `--single-pass-loudnorm`。看日志 `Loudnorm pass 1/2` 与末尾 `成片实测: I=… TP=…`。

人工复核：

```bash
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af loudnorm=I=-16:TP=-1.5:LRA=7:print_format=summary -f null -
```

目标：**LUFS ≈ −16**、**峰值 ≤ −1.5 dB**。用 IINA 听开场、第一段 run、风声最大处。

通过后：`assets.md` 写 `loudness: done`（附 I/TP/LRA）。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 口播刺耳 / 风盖过人声 | 峰值顶到 0 dB，或 flat gain 猛推 |
| 整体偏 quieter | 误用了旧全量 assemble 且加了 `--no-loudness-fix` |
| 冷开场消失 | prepend 后又跑了全量 assemble（响度请用本脚本） |

## 完成后

> 若 `subs: done` 已齐：`/p3-burn`；否则继续等 `/p3-subs`。
>
> `/p3-burn`
