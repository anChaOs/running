---
name: p3-loudness
description: 响度支路：对已拼好的成片跑 assemble 脚本默认响度链（dynaudnorm+loudnorm 约 −16 LUFS，峰值 ≤ −1.5 dBTP），与 p3-subs 并行、互不等待开工。烧字前须就绪。用户说响度、loudnorm、LUFS、音量定稿、音频优化时用。不要在这里拼画面、写字幕或烧字。拼画面走 p3-assemble；字幕走 p3-subs；烧字走 p3-burn。
---

# 响度

成片**画面已拼好**之后的并行支路：修响度到发布目标。与 `p3-subs` **并行**，不要互相卡住对方开工。烧字（`p3-burn`）前本支路须完成。

```text
总序：拼画面 p3-assemble →（字幕 p3-subs ∥ 响度 本 skill）→ 烧字 p3-burn
```

## 职责 / 输入 / 输出

| | |
| --- | --- |
| **职责** | 对媒体目录成片跑响度链并实测 I/TP；听开场与 POV 接缝 |
| **输入** | 已有 `YYYY-MM-DD-run-final.mp4`（通常来自 `p3-assemble --no-loudness-fix`） |
| **输出** | 同路径（或覆盖）响度版成片；可选备份 `YYYY-MM-DD-run-final-pre-loudnorm.mp4`；`assets.md` 记 `loudness: done` + 实测 |
| **实现** | 仍调用 `tools/assemble/assemble_episode.py`（**不加** `--no-loudness-fix`、**不加** `--ass`） |

## 不要做的事

- 不要等字幕定稿才开本支路；也不要拦着 `p3-subs` 开工
- 不要在这里加 `--ass`（烧字是 `p3-burn`）
- 不要整轨 flat gain（旧习惯 ×1.5）——峰值先顶满，轻句仍小
- 不要把本步写成「拼画面的串行后置」；编排上它是与字幕并行的独立阶段
- 不要在这里写字幕稿或改切条

## 前置

`p3-assemble` 已出可对字幕成片（`assemble: done`）。没有成片先 `/p3-assemble`。

## 步骤（调用现有脚本）

建议先备份未修响度副本，再覆盖 `run-final`：

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
cp "$MEDIA/YYYY-MM-DD-run-final.mp4" "$MEDIA/YYYY-MM-DD-run-final-pre-loudnorm.mp4"

nohup .venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir "$MEDIA" \
  > "$MEDIA/loudness.log" 2>&1 &
# 不加 --no-loudness-fix → 默认响度链；不加 --ass
```

脚本在 whoosh 叠完、AAC 编码前跑 post-mix。默认 **dynaudnorm → compressor → loudnorm**，**默认两遍 loudnorm**。滤镜起点（POV 实拍未逐条精调）：

```text
highpass=f=90,afftdn=nf=-25,equalizer=f=3500:t=q:w=1.2:g=2.5,dynaudnorm=f=250:g=15:p=0.9:m=8,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7,aformat=sample_rates=48000:channel_layouts=stereo
```

顺序：concat/acrossfade → 叠 whoosh → 响度链（目标约 **I=-16 LUFS**，**TP=-1.5 dBTP**）→ AAC 192k。

两遍 loudnorm：第一遍测 `measured_*`；第二遍 `linear=true` 再编码。测量失败自动退回单遍；强制单遍加 `--single-pass-loudnorm`。看日志 `Loudnorm pass 1/2` 与末尾 `成片实测: I=… TP=…`。

人工复核：

```bash
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af loudnorm=I=-16:TP=-1.5:LRA=7:print_format=summary -f null -

ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af volumedetect -f null -
```

目标：**LUFS ≈ −16**、**峰值 ≤ −1.5 dB**（勿顶到 0 dB）。用 IINA 听开场、第一段 run、风声最大处、已知掉音处。

通过后：`assets.md` 写 `loudness: done`（附 I/TP/LRA）。`episode.md` 状态仍由字幕侧推进。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 口播刺耳 / 风盖过人声 | 峰值顶到 0 dB，或 flat gain 猛推；确认未误加 `--no-loudness-fix` |
| 整体偏 quieter | 误关了响度链，或单句麦掉音需局部增益（整轨再 ×1.5 不够且易削波） |

## 完成后

> 若字幕尚未定稿：继续等 `/p3-subs`（或提醒用户改字）。若 `subs: done` 已齐：下一步 `/p3-burn`。
>
> `/p3-burn`
