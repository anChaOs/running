# 2026-09-20 watch-load-three 素材索引

## 本地素材目录

`~/Movies/running-content/2026-09-20-watch-load-three/`

## 重命名结果

### 视频素材

- `VID_20260920_062806.mp4` -> `2026-09-20-open.mp4`（0:57，跑前）
- `VID_20260920_064252.mp4` -> `2026-09-20-run-a.mp4`（3:51）
- `VID_20260920_065636.mp4` -> `2026-09-20-run-b.mp4`（4:02）
- `VID_20260920_071152.mp4` -> `2026-09-20-close.mp4`（2:04，跑后）

mtime 均对齐 VID 开始 + 时长，未改写。

### 跑步数据

- COROS `labelId 480461850153091778` -> `2026-09-20-run-data.fit`
- 06:29:14–07:08:22，6.04 km，平均 6:29，均心率 136，用时 39:09

### 高驰截图

- `Screenshot_2026-09-20-07-18-09-851_com.yf.smart.coros.dist.jpg` -> `2026-09-20-stats-01.jpg`

## 时间顺序依据

- 06:28:06：`open`
- 06:42:52：`run-a`
- 06:56:36：`run-b`
- 07:11:52：`close`

## 素材关联

- 开场：`2026-09-20-open.mp4`
- 跑中 A：`2026-09-20-run-a.mp4`
- 跑中 B：`2026-09-20-run-b.mp4`
- 收尾：`2026-09-20-close.mp4`
- FIT：`2026-09-20-run-data.fit`
- 截图：`2026-09-20-stats-01.jpg`

## 制作状态

- ingest: done
- pause-trim: done（open 57.1s→56.5s，close 124.2s→123.5s；句间均值+0.45s，短音节保留，片尾 3 秒不剪；原片 `*-raw.mp4`）
- hud: done（`-sn "C202 7" -sk 278.72`；开跑前 272.68，FIT 6.043；天气 shanghai；preview 已用 Silero VAD 粗剪：run-a 231.33s→226.47s、run-b 241.83s→227.13s，未剪 preview 为 `*-hud-preview-raw.mp4`）
- cover: done（run-a 40s 铁栏；句「负荷比？体力恢复？HRV？听哪个」）
- subs: done
- assemble: done
- qc: done
