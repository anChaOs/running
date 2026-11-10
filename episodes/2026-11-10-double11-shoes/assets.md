# 2026-11-10 double11-shoes 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-10-double11-shoes/`

## 重命名结果

### 视频素材

- `VID_20261110_053352_001.mp4` -> `2026-11-10-open.mp4`（粗剪后；原片 `2026-11-10-open-raw.mp4`）
- `VID_20261110_053924_002.mp4` -> `2026-11-10-run-a.mp4`
- `VID_20261110_054337_003.mp4` -> `2026-11-10-run-b.mp4`
- `VID_20261110_061638_004.mp4` -> `2026-11-10-run-c.mp4`
- `VID_20261110_070316_005.mp4` -> `2026-11-10-run-d.mp4`
- `VID_20261110_072351_006.mp4` -> `2026-11-10-close.mp4`（粗剪后；原片 `2026-11-10-close-raw.mp4`）

### 高驰截图（assemble 叠到 close 左侧）

- `Screenshot_2026-11-10-07-30-25-199_com.yf.smart.coros.dist.jpg` -> `2026-11-10-stats-01.jpg`

### 跑步数据

- `2026-11-10-run-data.fit`（COROS；records 05:35:32 → 07:20:10 Asia/Shanghai；与视频重叠 570s）

### 其他图片

- `1794267046645.jpg`：自拍大图——**封面源图**（未改名）

## 时间顺序依据

- 05:33:52: `open`（raw mtime 05:35:32；工作时长 ≈93.57s，raw 98.77s）
- 05:39:24: `run-a`（mtime 05:42:19）
- 05:43:37: `run-b`（mtime 05:45:55）
- 06:16:38: `run-c`（mtime 06:19:26）
- 07:03:16: `run-d`（mtime 07:04:53）
- 07:23:51: `close`（raw mtime 07:26:28；工作时长 ≈148.03s，raw 155.39s）

## 素材关联

- `open`：`2026-11-10-open.mp4`
- `run-a`：`2026-11-10-run-a.mp4`
- `run-b`：`2026-11-10-run-b.mp4`
- `run-c`：`2026-11-10-run-c.mp4`
- `run-d`：`2026-11-10-run-d.mp4`
- `close`：`2026-11-10-close.mp4`
- FIT：`2026-11-10-run-data.fit`
- 截图：`2026-11-10-stats-01.jpg`
- 封面源：`1794267046645.jpg`

## 制作状态

- ingest: done（角色 open=001 / run-a..d=002..005 / close=006；open+close 句间粗剪 vad + keep_lead_silence；open 约省 5.19s、close 约省 7.39s；`*-raw` 保留；**未动 run-***）
- shoes: done（1080v14；`-sn "1080v14" -sk 31.61`；跑完后；FIT 20.727 km；开跑前 10.88）
- hud: done（`-sn "1080v14" -sk 31.61`；`--jobs 2`；`--preview`；`--weather-city shanghai`；Open-Meteo archive 曾 400 但 weather-hourly.json 仍有 11-10 05–08 时点≈7°C；preview 句间粗剪已 apply，`keep_lead_silence=True`；a≈省11.7s / b≈13.1s / c≈25.6s / d≈14.2s；raw 备份 `*-hud-preview-raw.mp4`；工作 preview 时长 a 161.47 / b 122.67 / c 140.30 / d 81.40）
- assemble: done（open + run-a..d hud-preview + close-stats；xfade 0.2；run 风转场+whoosh；响度两遍 loudnorm；无 --ass；无冷开场/打字机；overlays 无；成片 `2026-11-10-run-final.mp4` 666.19s≈11:06；墙钟≈5m08s（08:11:12→08:16:20 Asia/Shanghai）；loudness 实测 I=-16.03 LUFS TP=-1.25 dBTP LRA=4.70 OK）
- loudness: done（拼时带响度，跳过单独 p3-loudness）
- qc: done（抽帧 qc/01-open-start、02-open-run-seam、03-hud-mid、04-run-close-seam、05-close-end；open/close 无 HUD；中段鞋名 1080v14、气温约 7°/体感 4°；接缝叠化正常；close 末 COROS stats 在左侧）
- cover: done（定稿句「Go Ultra 拍摄跑步画质会更好吗？」；字号硬性下限下排版断行减字 `Go Ultra|拍摄画质|更好吗？`；复用自拍 `1794267046645.jpg` rembg 抠图 `cover-work/person-cutout.png` + AI 底 `cover-work/bg.jpg`；三比例：`cover-4x3-1920x1440.jpg` / `cover-3x4-1080x1440.jpg` / `cover-16x9-1920x1080.jpg`）
- subs: waiting-review（draft_subs large-v3-turbo；专名表已用；切条自检；未 force_align / 未 burn；口播未定稿按成片音频）
- upload: pending
