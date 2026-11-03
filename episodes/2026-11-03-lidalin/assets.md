# 2026-11-03 lidalin 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-03-lidalin/`

## 重命名结果

### 视频素材

- `VID_20261103_052651.mp4` -> `2026-11-03-open.mp4`
- `VID_20261103_053907.mp4` -> `2026-11-03-run-a.mp4`
- `VID_20261103_054132.mp4` -> `2026-11-03-run-b.mp4`
- `VID_20261103_061441.mp4` -> `2026-11-03-run-c.mp4`
- `VID_20261103_064044.mp4` -> `2026-11-03-run-d.mp4`
- `VID_20261103_071938.mp4` -> `2026-11-03-close.mp4`

### 跑步数据

- `2026-11-03-run-data.fit` -> `2026-11-03-run-data.fit`

## 时间顺序依据

- 05:26:51: `open`
- 05:39:07: `run-a`
- 05:41:32: `run-b`
- 06:14:41: `run-c`
- 06:40:44: `run-d`
- 07:19:38: `close`

## 素材关联

- `open`：`2026-11-03-open.mp4`
- `run-a`：`2026-11-03-run-a.mp4`
- `run-b`：`2026-11-03-run-b.mp4`
- `run-c`：`2026-11-03-run-c.mp4`
- `run-d`：`2026-11-03-run-d.mp4`
- `close`：`2026-11-03-close.mp4`
- FIT：`2026-11-03-run-data.fit`

## 制作状态

- ingest: done（open/close 句间粗剪已 apply：band + 比默认更紧 OUTLIER_RATIO=1.25 / EXTRA=0.35 / GAP_SAFETY=0.18 / MIN_KEEP=0.32；open 约省 1.12s、close 约省 1.33s；`*-raw` 保留；未动 run-*）
- shoes: done（SC Trainer / -sk 2497.59；本场 FIT 20.667）
- hud: done（-sn SC Trainer -sk 2497.59；weather shanghai；preview a/b/d 已激进粗剪，c 句间已很密未再剪；run-* 原片未动）
- cover: done（自拍抠图+霓虹底；cover-1920x1080 / 4x3 / 1080x1440；句「李大林，强的可怕」）
- cold-open: done（`hooks-bumper.mp4` ≈12.032683s 硬切 prepend 到 run-final；备份 `2026-11-03-run-final-pre-coldopen.mp4`；offset=12.032683；源见 `cold-open/HOOKS.md`；正文原句保留）
- assemble: done（`--no-loudness-fix` 可对字幕版；成片含冷开场 `2026-11-03-run-final.mp4` ≈1192.15s；pre-coldopen ≈1180.10s）
- qc: done（抽帧 open/接缝/HUD/close；冷开场头帧已抽；响度链待 waiting-review 后补）
- subs: waiting-review（354 条；含冷开场钩子；外挂已同步媒体目录；未 force_align）
- upload: pending
