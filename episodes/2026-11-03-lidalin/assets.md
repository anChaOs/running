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
- cold-open: done（**完整三句**，不卡 12s；`hooks-bumper.mp4`≈33.27s → 60fps+loudnorm offset=**33.286s** prepend；备份短钩 `cold-open/backup-short-hooks/` + `2026-11-03-run-final-short-hooks-bak.mp4`；源见 `cold-open/HOOKS.md`；正文原句保留）
- assemble: done（先 `--no-loudness-fix` 出可对字幕版，再 loudnorm；成片含完整冷开场 `2026-11-03-run-final.mp4` ≈1213.49s；旁路 `…-loudnorm-no-hooks.mp4` 1180.181s / `…-pre-loudnorm.mp4` / `…-pre-coldopen.mp4` / `…-short-hooks-bak.mp4`）
- qc: done（抽帧 open/接缝/HUD/close；整片含钩子 loudnorm 复测见下；hooks-bumper 单独 loudnorm 后再 concat）
- subs: done（363 条定稿；force_align + 用户确认「可以了」；ASS Source Han Sans SC Heavy 72 / Outline 3 / MarginV=100；已烧入成片；无烧字备份 2026-11-03-run-final-no-burn.mp4）
- upload: ready（成片=标题名「李大林，强的可怕.mp4」；外挂=subtitles.srt；ASS=subtitles.ass）
- burn+rename: done（libass 烧 Source Han Sans SC Heavy→`李大林，强的可怕.mp4` ≈2.2G / 1213.49s；备份 `2026-11-03-run-final-no-burn.mp4`；音频 copy 保响度）

## 响度 / 冷开场

- cold-open bumper：`cold-open/hooks-bumper-60-loudnorm.mp4` **offset=33.286s**（三句完整：close 47.03–51.51；run-c 2.08–11.85；run-c 211.98–230.93；单独 loudnorm 后 I≈-16.0 / TP≈-1.2）
- final（含钩子）：`2026-11-03-run-final.mp4` 时长 ≈1213.488s；整片实测 **I=-16.0 LUFS / TP=-1.1 dBTP / LRA=5.0**（`loudnorm-final-with-hooks.txt`）
- 无钩子响度正片：`2026-11-03-run-final-loudnorm-no-hooks.mp4` 1180.181s；I=-16.02 / TP=-1.11 / LRA=5.30
- 备份：`…-pre-loudnorm.mp4`、`…-pre-coldopen.mp4`、`…-short-hooks-bak.mp4`、`cold-open/backup-short-hooks/`
