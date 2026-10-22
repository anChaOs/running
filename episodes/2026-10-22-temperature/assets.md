# 2026-10-22 temperature 素材索引

## 本地素材目录

`~/Movies/running-content/2026-10-22-temperature/`

## 重命名结果

### 视频素材

- `VID_20261022_055723.mp4` -> `2026-10-22-open.mp4`（粗剪后；原片 `2026-10-22-open-raw.mp4`）
- `VID_20261022_061459.mp4` -> `2026-10-22-run-a.mp4`
- `VID_20261022_064157.mp4` -> `2026-10-22-run-b.mp4`
- `VID_20261022_065633.mp4` -> `2026-10-22-run-c.mp4`
- `VID_20261022_071909.mp4` -> `2026-10-22-close.mp4`（粗剪后；原片 `2026-10-22-close-raw.mp4`）

### 跑步数据

- COROS Outdoor Run（labelId `481204142910505159`）：13.64 km / 1:13:36 / 均配 5:24 / 均心率 157
- 时间窗：2026-10-22 05:59:49–07:13:24（Asia/Shanghai）
- FIT：`2026-10-22-run-data.fit`（高驰 MCP 下载）

### 截图 / 封面源

- `Screenshot_*coros*.jpg` -> `2026-10-22-stats-01.jpg`（高驰能力/数据截图）
- `1792625182926.jpg`（封面自拍原图，6528×4896；用户确认）

## 时间顺序依据

- 05:57:23: `open`
- 06:14:59: `run-a`
- 06:41:57: `run-b`
- 06:56:33: `run-c`
- 07:19:09: `close`

## 素材关联

- `open`：`2026-10-22-open.mp4`
- `run-a`：`2026-10-22-run-a.mp4`
- `run-b`：`2026-10-22-run-b.mp4`
- `run-c`：`2026-10-22-run-c.mp4`
- `close`：`2026-10-22-close.mp4`
- FIT：`2026-10-22-run-data.fit`
- stats：`2026-10-22-stats-01.jpg`
- 封面自拍：`1792625182926.jpg`

### 封面成图（主推 cool-mist）

- 句：「凉快就能更接近破三？」+「破三实验室」
- 流程：自拍 `1792625182926.jpg` → onnx/u2net 抠图 → 粗白描边 → 冰蓝冷雾创意底 → 三比例手排（人偏右 / 竖版偏下）
- 中间件：`cover-work/person-cutout.png`、`cover-work/person-outlined.png`、`cover-work/bg-cool-mist.jpg`
- 根目录：
  - `cover.jpg` / `cover-1920x1080.jpg` / `cover-16x9-1920x1080.jpg` — **16:9**
  - `cover-4x3-1920x1440.jpg` — **4:3**
  - `cover-1080x1440.jpg` / `cover-3x4-1080x1440.jpg` — **3:4**

## 制作状态

- ingest: done
- hud: done（-sn "C202 7" / -sk 374.56；preview 已句间粗剪）
- shoes: done（C202 7 / -sk 374.56；本场 FIT 13.644）
- cover: waiting-review（主推 cool-mist；16:9/4:3/3:4 已出；句：凉快就能更接近破三？）
- assemble: done（2026-10-22-run-final.mp4；时长 1073.3s≈17:53；响度链默认 ON；close-stats 已叠）
- subs: waiting-review（初稿已自检切条；未 force_align）
- qc: done（抽帧 open/接缝/HUD/close-stats；I≈-15.9 LUFS，max_volume=-1.0 dB）
