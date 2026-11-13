---
name: p3-hud
description: 先把跑鞋、天气和透明层规格记进 logs/program.json，不渲未剪原片。时间表冻结后可以用 --prep-alpha 按留下的入出点直接画透明层，和字幕校对并行。需要已命名 mp4、FIT、跑鞋 -sn/-sk。用户说 HUD、叠加数据、overlay 时用。封面走 p3-cover，可并行。不要给 open/close 加 HUD，不要剪原片 run-*。天气用上海城市场点，不要发 FIT GPS。确认导出若缺透明层会自己补，仍然只编码一次。
---

# HUD

记录这一步只写 HUD 要什么：鞋名、跑完后的累计公里、天气城市、透明层规格。写进 `logs/program.json` 的 `hud`，并把 `logs/todo.md` 的 `hud-record` 标成 done。**不要在这里对未剪原片渲 ProRes，也不要在同一次任务里压审片预览。** 透明层等时间表冻结后再画：输入仍是原片，用 `--hud-start` / `--hud-end` 只画留下的区间，直接写成 `hud-renders/<profile>/` 里的 alpha。不要先把画面切到 `hud-renders/keeps/`。默认 `qtrle`。确认导出每条原片只打开一次：`-ss` 落在这组切片最早的入点，句间刀从同一次输入里裁出来，不按切片各开一个解码器，再叠时间从 0 起的 alpha。

封面走 `p3-cover`，和这一步互不依赖，可并行。细节见 `tools/hud/README.md`。不要为换封面句重渲 HUD。

## 前置

- `~/Movies/running-content/YYYY-MM-DD-slug/` 里已有 `*-run-*.mp4` 和 `*-run-data.fit`
- `-sn` / `-sk` 已由 `p3-shoes` 确认（`-sk` = 本场跑完后累计 km）。HUD 会用整场 FIT 总距离反推开跑前，再按当前帧 FIT `distance` 往前滚；不是每段视频各自顶到 `-sk`。
- 文件 `mtime` 能当视频结束时间（ingest 阶段应已校正）

## 不要做的事

- 不要给 `open` / `close` 加 HUD
- 不要把 FIT 的经纬度发给 Open-Meteo；用 `--weather-city shanghai` 或现成 `--weather-json`
- 温度写 `°C`，不要写 `℃`
- 不要加 `--preview`。那会在渲透明层的同时把未剪原片再压一遍，官方流程不这么做
- 不要改 `--video-end-time-mode`，保持 `file-modified`。原片第 0 秒对 FIT 的偏移写在 `source_sync`，之后改成片时间表也不许改它
- 不要把留下的区间先编码成 `hud-renders/keeps/` 再拿去画 HUD。那条旧命令还在，只作遗留，正式路径不调用
- **不要用 HUD preview 当封面底图**

## HUD

先探测时间：

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-a.mp4
```

先确认原片对齐已经写进 `logs/program.json`。然后只记录，不渲染：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --record-only \
  --weather-city shanghai \
  -sn "<HUD 名>" \
  -sk <跑完后累计 km>
```

明确不要天气时把 `--weather-city shanghai` 换成 `--no-weather`。默认透明层是 `qtrle`。剪映要 ProRes 时另加 `--overlay-profile prores4444`，那是导出或短视频的事，不是这一步。

`-sn` / `-sk` 用 `p3-shoes` 刚确认的这一场，不要抄上一期。

明确不要天气时把 `--weather-city` 换成 `--no-weather`。已有 `weather-hourly.json` 时用 `--weather-json <该文件>`。

记录步的产物是 `logs/program.json` 里的 `hud.recorded=true`，外加已有的 FIT。不要在这里产出 `*-hud-preview.mp4`。

句间刀用 `tools/ingest/trim_talk_pauses.py --record`，只把保留区间写进同一张表，不编码。画面和 HUD 以后都按这张表切。skill 不复述停顿算法。

## 冻结之后画透明层

`logs/program.json` 已经 `frozen`，并且 `logs/todo.md` 的 `preview` 是 done 之后，可以和字幕校对同时跑。字幕还没确认也不挡这一步。刀点保持冻结；校对只改错字和换行。

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --prep-alpha \
  -j 6
```

8 核机器用 `-j 6`，留 1–2 核给系统和写 mov 的 ffmpeg。默认仍是 2，核少就拿掉 `-j`。命令行上的数字会进渲染工人数。

同一条原片起一个 wrap：FIT 和模板加载一次，再按留下的窗口逐段写成 `hud-renders/<profile>/` 里各自的 alpha mov。一条原片占了大部分窗口时，最多拆成 `-j` 个进程，每个进程仍然一次加载、连续画多段。短窗补起点，透明层时间从 0 起。确认导出把同一条原片只打开一次，`-ss` 放在这一次 `-i` 前面；裁完的画面从 0 起，透明层直接叠上去。已经对得上的文件直接复用。不写 `hud-renders/keeps/`，也不解码重编原片画面。

脚本把 `hud-render` 标成 done，墙钟记在 `hud-render`。切开的区间由这一次加载后的窗口步进器来画，输入仍是原片。整段留下的原片不限窗口。清单写在 `logs/hud-alpha.json`。对不上当前表时，`final_export.py --confirmed -j 6` 会自己重画，工人数同样认 `--jobs`。确认导出仍然只编码一次。

响度测量不是这一步。要提前测用 `final_export.py --measure-only`。

## 记日志

`--record-only` 不写 `hud-render`（没有渲染）。`--prep-alpha` 才记 `hud-render`。确认导出里补画的透明层，墙钟算在 `final-export`。

## 完成

`assets.md`：`hud: done`（记下 `-sn` / `-sk`，并写明只记录、导出时再渲，规格 qtrle）。`episode.md` 改为 `hud`。`logs/todo.md` 的 `hud-record` 必须是 done。

## 完成后

HUD 写好后立刻推荐拼接；封面若还没做，提醒并行走 `/p3-cover`。

> 下一步把冷开场和贴图写入时间表，然后 `/p3-assemble`。可以直接发：
>
> `/p3-assemble`

短视频若要现在的透明层，再单独渲，并按剪映需要加 `--overlay-profile prores4444`。不要顺手加 `--preview`。全长成片等时间表冻结后 `--prep-alpha`；没跑的话确认导出会补。
