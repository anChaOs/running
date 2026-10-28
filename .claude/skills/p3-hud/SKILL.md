---
name: p3-hud
description: 给 run-* 渲染透明 HUD 和原片同档 preview，preview 出完做句间粗剪。需要已命名 mp4、FIT、跑鞋 -sn/-sk。用户说 HUD、叠加数据、hud-preview、overlay 时用。封面走 p3-cover，可并行。不要给 open/close 加 HUD，不要剪原片 run-*。天气用上海城市场点，不要发 FIT GPS。
---

# HUD

HUD 吃 `run-*` + FIT。封面走 `p3-cover`（自拍抠图合成），和 HUD 互不依赖，可**并行**做，不要等 HUD 渲完再做封面。

细节见 `tools/hud/README.md`。不要为换封面句重渲 HUD。

## 前置

- `~/Movies/running-content/YYYY-MM-DD-slug/` 里已有 `*-run-*.mp4` 和 `*-run-data.fit`
- `-sn` / `-sk` 已由 `p3-shoes` 确认（`-sk` = 本场跑完后累计 km）。HUD 会用整场 FIT 总距离反推开跑前，再按当前帧 FIT `distance` 往前滚；不是每段视频各自顶到 `-sk`。
- 文件 `mtime` 能当视频结束时间（ingest 阶段应已校正）

## 不要做的事

- 不要给 `open` / `close` 加 HUD
- 不要把 FIT 的经纬度发给 Open-Meteo；用 `--weather-city shanghai` 或现成 `--weather-json`
- 温度写 `°C`，不要写 `℃`
- 不要降码；`--preview` 必须跟原片同档
- 不要改 `--video-end-time-mode`，保持 `file-modified`
- 短样不要裁出来再渲；正式片段直接用原片
- **不要用 HUD preview 当封面底图**，数据条会进封面

## HUD

先探测时间：

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-a.mp4
```

dry-run：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --overlay-only \
  --preview \
  --weather-city shanghai \
  --dry-run \
  -sn "<HUD 名>" \
  -sk <跑完后累计 km>
```

正式：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --overlay-only \
  --preview \
  --weather-city shanghai \
  -sn "<HUD 名>" \
  -sk <跑完后累计 km>
```

`-sn` / `-sk` 用 `p3-shoes` 刚确认的这一场，不要抄上一期。

明确不要天气时把 `--weather-city` 换成 `--no-weather`。已有 `weather-hourly.json` 时用 `--weather-json <该文件>`。

产出：

```text
hud-renders/YYYY-MM-DD-run-a-hud-alpha.mov
hud-renders/YYYY-MM-DD-run-a-hud-preview.mp4
weather-hourly.json
```

preview 出完后，对 **preview** 做句间粗剪（原片 `run-*` 不剪，HUD 时间轴才不会漂）：

```bash
.venv/bin/python tools/ingest/trim_talk_pauses.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --targets preview
```

默认 dry-run。确认后 `--apply`。工作文件仍是 `*-hud-preview.mp4`，未剪的 preview 改名为 `*-hud-preview-raw.mp4`。确认时看两件事：最后一句有没有被片尾保护段前面的空洞吃掉；强度课硬段不说话，那是课不是句间停顿，不要整段剪掉。

口播检测默认 **Silero VAD**（人声 vs 风/车，不是声纹）。模型：

```text
~/Movies/running-content/.models/ggml-silero-v5.1.2.bin
```

没有就从 `https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin` 拉到这个路径（约 864K）。ModelScope 没有这个模型；直连不通就把域名换成 `hf-mirror.com`。CLI 是 brew 的 `whisper-vad-speech-segments`，打印的时间是百分之一秒。只剪 `max(2×均值, 均值+1.2s)` 以上的停顿，收到均值 + 安全余量，左右留肩，片尾 3 秒不剪。对比旧能量门限加 `--speech-detect band`。

拼成片用粗剪后的 **preview**。`--preview` 会先渲透明层再叠回原片同档，alpha 是渲染中间件，不是成片交付。不走剪映可以不理 `*-hud-alpha.mov`。单片段检查加 `--clips YYYY-MM-DD-run-a.mp4`。

## 完成

`assets.md`：`hud: done`（记下 `-sn` / `-sk`）。`episode.md` 改为 `hud`。

## 完成后

HUD 写好后立刻推荐拼接；封面若还没做，提醒并行走 `/p3-cover`。

> 下一步用 `/p3-assemble`，可以直接发：
>
> `/p3-assemble`

短视频才需要 alpha 进剪映：`/p3-jianying`。
