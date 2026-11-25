---
name: p3-hud
description: 先把跑鞋、天气和透明层规格记进 logs/program.json（--record-only），不渲未剪原片；时间表冻结后用 --prep-alpha 直接画留下区间的透明层（8 核 -j 6），与字幕校对并行。用户说 HUD、叠加数据、overlay 时用。封面走 p3-cover，可并行。
---

# HUD

本步遵守 `p3-episode` 全局协议（进度门闩与墙钟日志）。**记录阶段只写配置，不渲未剪原片**；透明层等时间表冻结后再用 `--prep-alpha` 按留下的入出点直接画，默认 `qtrle`（剪映需 ProRes 时另加 `--overlay-profile prores4444`）。封面走 `/p3-cover` 可并行；细节见 `tools/hud/README.md`。

## 前置

- 素材目录已按分类或平铺放好 `*-run-*.mp4`（`raw/`）和 `*-run-data.fit`（`data/`），`mtime` 已校正且 `source_sync` 已写入 `logs/program.json`
- `-sn` / `-sk` 已由 `/p3-shoes` 确认（`-sk` = 本场跑完后累计 km，HUD 会反推开跑前再随 FIT 滚动）

## 不要做的事

- 不要给 `open` / `close` 加 HUD；不要把 FIT 经纬度发给 Open-Meteo（用 `--weather-city shanghai` 或 `--weather-json`）
- 温度写 `°C`，不要写 `℃`
- 不要加 `--preview`（会重压未剪原片）；不要改 `--video-end-time-mode`（保持 `file-modified`）
- 不要把区间先切到 `hud-renders/keeps/` 再画 HUD；不要用 HUD preview 当封面底图；不要为换封面重渲 HUD

## 阶段一：记录 HUD 规格（`hud-record`）

先探测时间（不改 `todo.md`）：

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/YYYY-MM-DD-slug/raw/YYYY-MM-DD-run-a.mp4
```

再只记录、不渲染（明确不要天气改 `--no-weather`；已有缓存用 `--weather-json`）：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --record-only \
  --weather-city shanghai \
  -sn "<HUD 名>" \
  -sk <跑完后累计 km>
```

跑完核对 `logs/todo.md`（`hud-record: done`；重记规格时 `hud-render` 会被打回 `pending`）。`--record-only` 不记 `hud-render` 墙钟。

## 阶段二：交出字幕初稿后画透明层（`hud-render`）

`logs/program.json` 已 `frozen`、`preview: done` 且**优先独享 CPU 跑完 `draft_subs.py` 交出 `subtitles.txt`（`subs: waiting-review`）时**，**立刻并行启动**（与用户校对字幕并行，不要抢在转写初稿前占满 CPU；8 核用 `-j 6`，核少拿掉 `-j` 默认 2）：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --prep-alpha \
  -j 6
```

脚本直接写出 `hud-renders/<profile>/*-hud-alpha.mov` 与清单 `logs/hud-alpha.json`（已对上的直接复用），自动记 `hud-render` 墙钟并标 `logs/todo.md` 的 `hud-render: done`。若未提前跑或表已变，`final_export.py --confirmed` 会自动补画。

## 完成与下一步

记录步完成时写 `assets.md`（`hud: done`，记 `-sn`/`-sk`、规格 `qtrle`）并改 `episode.md` 为 `hud`。若封面还没做提醒并行 `/p3-cover`。

> 下一步把冷开场和贴图写入时间表，然后 `/p3-assemble`：
>
> `/p3-assemble`
