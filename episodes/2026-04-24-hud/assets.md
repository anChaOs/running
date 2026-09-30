# 2026-04-24 第二期素材索引

## 本地素材目录

`~/Movies/running-content/2026-04-24-hud/`

> 说明：本地目录名是 `2026-04-24-hud`（中间有短横线）。本批素材拍摄日期是 2026-04-24，文件名按 `2026-04-24-*` 命名。

## 重命名结果

### 视频素材

- `VID_20260424_055207.mp4` -> `2026-04-24-open.mp4`
- `VID_20260424_060157.mp4` -> `2026-04-24-run-a.mp4`
- `VID_20260424_061715.mp4` -> `2026-04-24-run-b.mp4`
- `VID_20260424_064712.mp4` -> `2026-04-24-run-c.mp4`
- `VID_20260424_072041.mp4` -> `2026-04-24-close.mp4`

### 跑步数据

- `上海市_跑步20260424055340.fit` -> `2026-04-24-run-data.fit`

## 时间顺序依据

- 05:53:35：`open`
- 06:03:51：`run-a`
- 06:21:07：`run-b`
- 06:52:04：`run-c`
- 07:21:46：`close`

## 素材关联

- 开场：`2026-04-24-open.mp4`
- 跑中 A：`2026-04-24-run-a.mp4`
- 跑中 B：`2026-04-24-run-b.mp4`
- 跑中 C：`2026-04-24-run-c.mp4`
- 收尾：`2026-04-24-close.mp4`
- FIT 数据：`2026-04-24-run-data.fit`

## 备注

- 仓库该期目录只保留索引和剪辑备注，不放原始大文件。
- 后续如果补充截图、HUD 导出或成片，也建议继续沿用 `2026-04-24-run-data.*`、`2026-04-24-run-hud-overlay.*`、`2026-04-24-run-final.*` 这套命名。

## 制作状态

- ingest: done
- hud: done（`-sn SC Trainer -sk 2097.14`；抽帧鞋里程 run-a 2083 / run-b 2086 / run-c 2092）
- subs: done（txt 已人手改并回写 ass；另有 srt 给 YouTube 外挂。成片轴 open 0 / run-a 86.383 / run-b 199.642 / run-c 431.292 / close 722.827）
- cover: done（原片 `run-a.mp4` @44s，按锐度筛过；「拍完不等于做完」/「破三实验室 · 第二条」）
- assemble: done（`2026-04-24-run-final.mp4`，未烧字幕；外挂 `subtitles.ass` / `subtitles.srt` 已拷到媒体目录）
- qc: done（成片无烧字幕；HUD 鞋里程 run-a 2083 / run-b 2086 / run-c 2092；气温 `11°C / 10°C` → `12°C / 12°C`；口型已手核）
- cleanup: 已删 HUD preview/alpha、听写 wav、封面候选抽帧。重拼需按 `-sn SC Trainer -sk 2097.14` 再渲 HUD。原片和 `run-final.mp4` 先留着。
