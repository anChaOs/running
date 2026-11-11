# 2026-11-11 double11-buys 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-11-double11-buys/`

## 重命名结果

### 视频素材

- `VID_20261111_054701_007.mp4` -> `2026-11-11-open.mp4`
- `VID_20261111_055445_008.mp4` -> `2026-11-11-run-a.mp4`
- `VID_20261111_062520_009.mp4` -> `2026-11-11-run-b.mp4`
- `VID_20261111_071955_011.mp4` -> `2026-11-11-close.mp4`

### 跑步数据

- `2026-11-11-run-data.fit` -> `2026-11-11-run-data.fit`

## 时间顺序依据

- 05:47:01: `open`
- 05:54:45: `run-a`
- 06:25:20: `run-b`
- 07:19:55: `close`

## 素材关联

- `open`：`2026-11-11-open.mp4`
- `run-a`：`2026-11-11-run-a.mp4`
- `run-b`：`2026-11-11-run-b.mp4`
- `close`：`2026-11-11-close.mp4`
- FIT：`2026-11-11-run-data.fit`

## 制作状态

- ingest: done（007=open / 008=run-a / 009=run-b / 011=close；010 误删未拍；open 67.33→65.47s、close 58.26→56.87s，keep_lead_silence=True；鞋图未改名）
- shoes: done（1080v14；`-sn "1080v14" -sk 52.39`；跑完后；FIT 15.348 km；开跑前 37.04；与 11-10 账本 31.61 相差 5.43 km，按用户口述 52.39 记账）
- hud: done（`-sn "1080v14" -sk 52.39`；`--jobs 2`；`--preview`；`--weather-city shanghai`；Open-Meteo archive 曾 400，weather-hourly.json 仍有 11-11 05–08 时点≈6–7°C / 体感≈5°C；按 PR #81 时间单调小地图于 11-11 09:02–09:59 重渲，alpha/preview 时长 a 209.10 / b 414.41，与原片一致；0:37:48 未再全沙闪，剩余路线仍灰）
- cover: done（用户确认改排后的三比例；封面句「我已退役的跑鞋」；复用 11-02 退役鞋数据与抠图；cover-16x9-1920x1080.jpg / cover-4x3-1920x1440.jpg / cover-3x4-1080x1440.jpg）
- preview: done（审片预览见下条 assemble；`2026-11-11-review-preview.mp4` 与带鞋审片均 745.4s / 12:25）
- assemble: done（按新 HUD 于 11-11 10:01–10:08 重拼审片预览 `2026-11-11-review-preview.mp4`，745.4s / 12:25，h264 1080p30，未烧字幕/响度/封面叠图，未导出成片；带鞋审片 `2026-11-11-review-preview-with-shoes.mp4` 同长 745.4s，叠 mid 4:3（9:36.52–9:59.80，宽 920）+ close 3:4（close+0.4 至结尾，宽 520），fade 0.35 / opacity 0.85）
- qc: done（抽帧 qc/01-open-start、02-open-run-seam、03-hud-mid-a、04-hud-mid-b、05-run-close-seam、06-close-stats、07-close-end；open/close 无 HUD；中段鞋名 1080v14、气温约 6–7°/体感 4–5°，与 COROS 截图 10°C 不同因走上海 Open-Meteo；跑段累计里程与 37.04+本场距离一致；接缝叠化正常；close 全程左侧 stats，未截断；HUD 重渲后补 qc/hud-map-3734、qc/hud-map-3748（0:37:34 / 0:37:48，剩余路线仍灰）；带鞋预览抽 qc/retired-overlay-mid、qc/retired-overlay-close）
- subs: done（用户确认含 0:06:44.96–0:06:45.50 的 0.54s 漏盖空档；换行已按用户清单拆分）
- final: done（11-11 10:25–10:32 Asia/Shanghai 用独立 worktree PR #82 tools @ 1aebc9e 一次导出；因本集分支尚未合入 overlays.json 最终导出支持，未把 #82 合进本分支或 main；成片 `2026-11-11-run-final.mp4` 745.400s / 12:25.40，1080p30 hevc/hvc1 + AAC 192k，2.5G，moov 在前；含 mid 4:3 `cover-4x3-1920x1440.jpg` 576.52–599.80 与 close 3:4 `cover-3x4-1080x1440.jpg` 688.922833–745.3895，fade 0.35 / opacity 0.85；已烧字幕并做响度；抽帧 qc/final-retired-overlay-mid、qc/final-retired-overlay-close、qc/final-subs-sample）
- upload: ready（`upload/`：标题名成片硬链自 `2026-11-11-run-final.mp4`，加 16:9/4:3/3:4 封面与 subtitles.srt；根目录成片保留，避免改正在播放的文件）
