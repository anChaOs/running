---
name: p3-loudness
description: 响度补跑：对成片跑 assemble 默认响度链（约 −16 LUFS，峰值 ≤ −1.5 dBTP）。优先在 p3-assemble 拼时带响度；本 skill 仅拼时关了响度才用。可与 p3-subs 并行。用户说响度、loudnorm、LUFS、音量定稿时用。
---

# 响度

成片画面已拼好之后，把音量修到发布目标：**I=−16 LUFS**，**TP=−1.5 dBTP**；不要整轨 flat gain。

**现状：** 仍调 `assemble_episode.py`（不加 `--no-loudness-fix`）= **全量重拼**，不是只改音轨。拼时已带响度（`loudness: done`）则**跳过**。冷开场 prepend 后不要跑（会抹 bumper）。编码成本见 `p3-assemble`。

## 不要做的事

- 拼时已带响度就不要再跑本步
- 冷开场 prepend 之后不要跑本步覆盖成片
- 不要在这里加 `--ass`
- 不要整轨 flat gain（旧习惯 ×1.5）
- 不要在这里写字幕稿或改切条

## 前置

`assemble: done`，且还没有 `loudness: done`。没有成片先 `/p3-assemble`（推荐直接拼时带响度）。

## 步骤

建议先备份未修响度副本，再覆盖 `run-final`：

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
cp "$MEDIA/YYYY-MM-DD-run-final.mp4" "$MEDIA/YYYY-MM-DD-run-final-pre-loudnorm.mp4"

nohup .venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir "$MEDIA" \
  > "$MEDIA/loudness.log" 2>&1 &
# 不加 --no-loudness-fix；不加 --ass
```

脚本在 whoosh 叠完、AAC 编码前跑 post-mix。默认 **dynaudnorm → compressor → loudnorm**，**默认两遍 loudnorm**。滤镜起点（POV 实拍未逐条精调）：

```text
highpass=f=90,afftdn=nf=-25,equalizer=f=3500:t=q:w=1.2:g=2.5,dynaudnorm=f=250:g=15:p=0.9:m=8,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7,aformat=sample_rates=48000:channel_layouts=stereo
```

两遍 loudnorm：第一遍测 `measured_*`；第二遍 `linear=true` 再编码。测量失败自动退回单遍；强制单遍加 `--single-pass-loudnorm`。看日志 `Loudnorm pass 1/2` 与末尾 `成片实测: I=… TP=…`。

人工复核：

```bash
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af loudnorm=I=-16:TP=-1.5:LRA=7:print_format=summary -f null -

ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af volumedetect -f null -
```

目标：**LUFS ≈ −16**、**峰值 ≤ −1.5 dB**（勿顶到 0 dB）。用 IINA 听开场、第一段 run、风声最大处、已知掉音处。

通过后：`assets.md` 写 `loudness: done`（附 I/TP/LRA）。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 口播刺耳 / 风盖过人声 | 峰值顶到 0 dB，或 flat gain 猛推；确认未误加 `--no-loudness-fix` |
| 整体偏 quieter | 误关了响度链，或单句麦掉音需局部增益 |
| 冷开场消失 | prepend 后又跑了全量 assemble |

## 完成后

> 若 `subs: done` 已齐：`/p3-burn`；否则继续等 `/p3-subs`。
>
> `/p3-burn`
