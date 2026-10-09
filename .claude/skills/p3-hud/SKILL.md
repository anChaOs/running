---
name: p3-hud
description: 给 run-* 渲染透明 HUD 和原片同档 preview，preview 出完做句间粗剪，同时从原片 run-* 做封面。需要已命名 mp4、FIT、跑鞋 -sn/-sk。用户说 HUD、叠加数据、hud-preview、overlay、封面一起做时用。不要给 open/close 加 HUD，不要剪原片 run-*。天气用上海城市场点，不要发 FIT GPS。封面不要用 HUD preview。
---

# HUD + 封面

同一阶段、互不影响，**并行**：HUD 吃 `run-*` + FIT；封面吃原片 `run-*`（任意一段，用户点哪段就用哪段）。不要等 HUD 渲完再抽封面。

细节见 `tools/hud/README.md`。换封面句、重做封面走 `p3-cover`，不要为换几个字重渲 HUD。

## 前置

- `~/Movies/running-content/YYYY-MM-DD-slug/` 里已有 `*-run-*.mp4` 和 `*-run-data.fit`
- `-sn` / `-sk` 已由 `p3-shoes` 确认（`-sk` = 本场跑完后累计 km）。HUD 会用整场 FIT 总距离反推开跑前，再按当前帧 FIT `distance` 往前滚；不是每段视频各自顶到 `-sk`。
- 文件 `mtime` 能当视频结束时间（ingest 阶段应已校正）
- 封面句：默认 `episode.md` / `talk.md` 标题，系列名「破三实验室」。用户改过就用用户的。

## 不要做的事

- 不要给 `open` / `close` 加 HUD
- 不要把 FIT 的经纬度发给 Open-Meteo；用 `--weather-city shanghai` 或现成 `--weather-json`
- 温度写 `°C`，不要写 `℃`
- 不要降码；`--preview` 必须跟原片同档
- 不要改 `--video-end-time-mode`，保持 `file-modified`
- 短样不要裁出来再渲；正式片段直接用原片
- **不要用 HUD preview 当封面底图**，数据条会进封面
- 不要在封面堆第二句鸡汤；不要为了空路用糊帧

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

没有就从 `https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin` 拉到这个路径（约 864K）。CLI 是 brew 的 `whisper-vad-speech-segments`，打印的时间是百分之一秒。只剪 `max(2×均值, 均值+1.2s)` 以上的停顿，收到均值 + 安全余量，左右留肩，片尾 3 秒不剪。对比旧能量门限加 `--speech-detect band`。

拼成片用粗剪后的 **preview**。`--preview` 会先渲透明层再叠回原片同档，alpha 是渲染中间件，不是成片交付。不走剪映可以不理 `*-hud-alpha.mov`。单片段检查加 `--clips YYYY-MM-DD-run-a.mp4`。

## 封面（并行）

片源：任一原片 `YYYY-MM-DD-run-*.mp4`（不只 `run-a`，也不要 HUD preview）。抽帧：**清晰是硬条件。** 近处树叶、树皮、路沿要能看出纹理。同时避开行人特写、过曝、低头看表。先抽 2–3 个清楚的候选给用户看；用户点哪段就用哪段。

```bash
.venv/bin/python tools/assemble/make_cover.py \
  --src ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-XXX.mp4 \
  --title "封面句" \
  --sub "破三实验室" \
  --ss 40 \
  --out-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

产出：

```text
cover-1920x1080.jpg
cover-1080x1440.jpg
cover-frame.jpg
```

## 完成

`assets.md`：`hud: done`（记下 `-sn` / `-sk`），`cover: done` 或 `cover: waiting-review`（等人选帧）。`episode.md` 改为 `hud`。

## 完成后

两件都写好后立刻推荐字幕。不要再推荐 `/p3-cover`，除非封面被否、要重抽。

> 下一步用 `/p3-subs`，可以直接发：
>
> `/p3-subs`

只要 HUD、先不听写：

> `/p3-assemble`

短视频才需要 alpha 进剪映：`/p3-jianying`。
