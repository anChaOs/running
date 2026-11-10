---
name: p3-hud
description: 给 run-* 渲染透明 HUD 和审片 preview。需要已命名 mp4、FIT、跑鞋 -sn/-sk。用户说 HUD、叠加数据、hud-preview、overlay 时用。封面走 p3-cover，可并行。不要给 open/close 加 HUD，不要剪原片 run-*。天气用上海城市场点，不要发 FIT GPS。
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
- HUD alpha 是最终导出的中间层；`--preview` 只供审片，可以使用统一的轻量 preview 规格，不作为最终输入
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

`*-hud-preview.mp4` 只用于审片；最终导出直接使用原始 run 片段和对应 alpha，不读取 preview。

预览只用于人工检查和字幕校对。不要对 `hud-preview` 做会改变时长的粗剪：最终导出会重新读取原始 `run-*` 与 HUD alpha，单独裁预览会造成字幕轴漂移。若需要裁句间停顿，必须先把同一 EDL 应用于原片和 alpha；本次不走该路径。

口播检测与停顿门槛在 `tools/ingest/trim_talk_pauses.py`（默认 Silero VAD）。对比旧能量门限加 `--speech-detect band`。skill 不复述剪停顿算法；**跑流程只调脚本看输出，不要为执行去 Read 源码**（改算法 / 排错除外）。

多段 `run-*` 默认 `--jobs 2` 并行渲（可改；`-j 1` 串行）；失败看 `hud-renders/*-hud-render.log` 定位哪条 clip。审片预览使用 `*-hud-preview.mp4`；最终导出使用原片和 `*-hud-alpha.mov`。`--preview` 先渲透明层再生成轻量审片文件，alpha 是最终导出的中间层。不走剪映可以不理 alpha。单片段检查加 `--clips YYYY-MM-DD-run-a.mp4`。

## 完成

`assets.md`：`hud: done`（记下 `-sn` / `-sk`）。`episode.md` 改为 `hud`。

## 完成后

HUD 写好后立刻推荐拼接；封面若还没做，提醒并行走 `/p3-cover`。

> 下一步用 `/p3-assemble`，可以直接发：
>
> `/p3-assemble`

短视频才需要 alpha 进剪映：`/p3-jianying`。
