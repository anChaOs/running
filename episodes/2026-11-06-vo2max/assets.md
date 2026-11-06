# 2026-11-06 vo2max 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-06-vo2max/`

## 重命名结果

### 视频素材

- `VID_20261106_052403.mp4` -> `2026-11-06-open.mp4`
- `VID_20261106_053306.mp4` -> `2026-11-06-run-a.mp4`
- `VID_20261106_053436.mp4` -> `2026-11-06-run-b.mp4`
- `VID_20261106_055420.mp4` -> `2026-11-06-run-c.mp4`
- `VID_20261106_063341.mp4` -> `2026-11-06-run-d.mp4`
- `VID_20261106_073006.mp4` -> `2026-11-06-close.mp4`

### 跑步数据

- `2026-11-06-run-data.fit` -> `2026-11-06-run-data.fit`

## 时间顺序依据

- 05:24:03: `open`
- 05:33:06: `run-a`
- 05:34:36: `run-b`
- 05:54:20: `run-c`
- 06:33:41: `run-d`
- 07:30:06: `close`

## 素材关联

- `open`：`2026-11-06-open.mp4`
- `run-a`：`2026-11-06-run-a.mp4`
- `run-b`：`2026-11-06-run-b.mp4`
- `run-c`：`2026-11-06-run-c.mp4`
- `run-d`：`2026-11-06-run-d.mp4`
- `close`：`2026-11-06-close.mp4`
- FIT：`2026-11-06-run-data.fit`

## 制作状态

- ingest: done
- shoes: done（SC Trainer；`-sn "SC Trainer" -sk 2536.20`；跑完后；FIT 22.191 km）
- hud: done（`-sn "SC Trainer" -sk 2536.20`；`--jobs 2`；`--preview`；`--weather-city shanghai`；preview 句间粗剪已 apply，`keep_lead_silence=True`；raw 备份 `*-hud-preview-raw.mp4`）
- cover: done（句「最大摄氧量｜百分之几是什么意思？」排版断行 `最大摄氧|百分之几|什么意思`；自拍 `1793922140517.jpg`；AI 创意底 `cover-work/bg.jpg`；仅三比例：`cover-4x3-1920x1440.jpg` / `cover-3x4-1080x1440.jpg` / `cover-16x9-1920x1080.jpg`）
- assemble: done（open + 4 HUD preview + close-stats；风转场；拼时响度两遍；**成片已排除 run-a（cut not reassemble）**：backup `2026-11-06-run-final-with-run-a.mp4`；T0=55.141 T1=84.241 Δ=29.100s；新成片 `2026-11-06-run-final.mp4` ≈1246.91s / 2.29G；stream-copy concat）
- qc: done（`qc/01-open-start`…`05-close-end` + `04b-close-after-xfade`；open/close 无 HUD；跑中 HUD 鞋名 SC Trainer、配速、AIR/FEEL °C；close 左 stats-01）
- loudness: done（拼时两遍；成片实测 I=-16.03 LUFS / TP=-0.92 dBTP / LRA=4.40）
- subs: waiting-review（draft 轴已随成片切掉 run-a：删 [55.141,84.241) 内 6 条，其后 −29.100s；现 311 条；等人抽听改字；未 burn）
- upload: pending
