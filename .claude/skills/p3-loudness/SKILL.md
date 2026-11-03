---
name: p3-loudness
description: 响度支路：对成片跑 assemble 脚本默认响度链（约 −16 LUFS，峰值 ≤ −1.5 dBTP）。当前实现=全量重拼，成本高；优先在 p3-assemble 拼时带响度，本 skill 仅补跑。可与 p3-subs 并行。烧字前须就绪。用户说响度、loudnorm、LUFS、音量定稿时用。拼画面走 p3-assemble；字幕走 p3-subs；烧字走 p3-burn。总序见 p3-episode。
---

# 响度

成片画面已拼好之后，把音量修到发布目标。

**总序真源：** `p3-episode`。编码成本与推荐路径见 `p3-assemble`「编码成本」。

## 成本警告（必读）

**当前实现仍调用 `assemble_episode.py`（不加 `--no-loudness-fix`）= 从 open/HUD/close 全量重拼重编整片，不是「只改音轨」。**

- 若 `p3-assemble` **拼时已带响度**（`loudness: done`）：**跳过本 skill**。
- 若拼时用了 `--no-loudness-fix`：本步会再编一整遍；人审字幕不够长时，墙钟上几乎省不下时间。
- 若已做过**冷开场 prepend**：本步会覆盖 `run-final`、**抹掉 bumper**——先不要跑；等「只响度」脚本，或把 bumper 重新接上。

滤镜目标（真源在本 skill）：约 **I=−16 LUFS**，**TP=−1.5 dBTP**；不要整轨 flat gain。

## 职责 / 输入 / 输出

| | |
| --- | --- |
| **职责** | 补跑响度链并实测 I/TP；听开场与 POV 接缝 |
| **输入** | 已有 `YYYY-MM-DD-run-final.mp4`，且 `loudness` 尚未 done |
| **输出** | 同路径响度版成片；可选备份 `*-run-final-pre-loudnorm.mp4`；`assets.md`：`loudness: done` + 实测 |
| **实现（现状）** | `tools/assemble/assemble_episode.py`（**不加** `--no-loudness-fix`、**不加** `--ass`）→ 全量重拼 |

## 不要做的事

- 拼时已带响度就不要再跑本步
- 冷开场 prepend 之后不要跑本步覆盖成片
- 不要在这里加 `--ass`（烧字是 `p3-burn`）
- 不要整轨 flat gain（旧习惯 ×1.5）
- 不要在这里写字幕稿或改切条
- 不要拦着 `p3-subs` 开工（编排上可并行；只是本步很贵）

## 前置

`p3-assemble` 已出成片（`assemble: done`），且还没有 `loudness: done`。没有成片先 `/p3-assemble`（推荐直接拼时带响度）。

## 步骤（调用现有脚本）

建议先备份未修响度副本，再覆盖 `run-final`：

```bash
MEDIA=~/Movies/running-content/YYYY-MM-DD-slug
cp "$MEDIA/YYYY-MM-DD-run-final.mp4" "$MEDIA/YYYY-MM-DD-run-final-pre-loudnorm.mp4"

nohup .venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir "$MEDIA" \
  > "$MEDIA/loudness.log" 2>&1 &
# 不加 --no-loudness-fix → 默认响度链；不加 --ass
# 注意：这是全量重拼，不是 audio-only
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

通过后：`assets.md` 写 `loudness: done`（附 I/TP/LRA）。`episode.md` 状态仍由字幕侧推进。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 口播刺耳 / 风盖过人声 | 峰值顶到 0 dB，或 flat gain 猛推；确认未误加 `--no-loudness-fix` |
| 整体偏 quieter | 误关了响度链，或单句麦掉音需局部增益 |
| 冷开场消失 | prepend 后又跑了全量 assemble（本步） |

## 完成后

> 若字幕尚未定稿：继续等 `/p3-subs`。若 `subs: done` 已齐：下一步 `/p3-burn`。
>
> `/p3-burn`
