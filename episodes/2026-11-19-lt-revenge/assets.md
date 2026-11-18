# 2026-11-19 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-19-lt-revenge/`

## 重命名结果

### 视频素材

- `VID_20261119_055048_017.mp4` -> `2026-11-19-open.mp4`
- `VID_20261119_055803_018.mp4` -> `2026-11-19-run-a.mp4`
- `VID_20261119_063535_019.mp4` -> `2026-11-19-run-b.mp4`
- `VID_20261119_070458_020.mp4` -> `2026-11-19-run-c.mp4`
- `VID_20261119_070744_021.mp4` -> `2026-11-19-run-d.mp4`
- `VID_20261119_072154_022.mp4` -> `2026-11-19-close.mp4`

### 跑步数据

- COROS MCP `labelId=481853536064274535` -> `2026-11-19-run-data.fit`

### 高驰截图

- `Screenshot_...-07-27-15-874_...` -> `2026-11-19-stats-01.jpg`（今天完整总览）
- `Screenshot_...-07-27-32-207_...` -> `2026-11-19-stats-02.jpg`（今天各组圈速）
- `Screenshot_...-07-27-51-132_...` -> `2026-11-19-stats-03.jpg`（上周四完整总览）
- `Screenshot_...-07-28-01-841_...` -> `2026-11-19-stats-04.jpg`（上周四各组圈速）
- `Screenshot_...-07-33-29-457_...` -> `2026-11-19-stats-05.jpg`（上周四地图+温度）
- `Screenshot_...-07-33-36-625_...` -> `2026-11-19-stats-06.jpg`（今天地图+温度）

## 时间顺序依据

- HH:MM:SS：`open` → `run-a` → `run-b` → `run-c` → `run-d` → `close`

## 素材关联

- 开场：`2026-11-19-open.mp4`
- 跑中 A–D：`2026-11-19-run-a.mp4` … `2026-11-19-run-d.mp4`
- 收尾：`2026-11-19-close.mp4`
- FIT：`2026-11-19-run-data.fit`
- 封面自拍：`1795044496788.jpg`

## 制作状态

- ingest: done
- shoes: done（Plaid 1.5，跑完后 -sk 550.68；本场 FIT 18.151 km）
- hud: done（`--record-only` + `--prep-alpha -j 6`；-sn Plaid 1.5 -sk 550.68；规格 qtrle）
- cover: done（句「6x2km乳酸阈间歇 | 复仇之战」；字号硬性下限下排版断行 `6x2km|乳酸阈|复仇之战`，省略「间歇」；自拍 rembg + 设计底 `cover-work/bg.jpg`；三比例：`cover-4x3-1920x1440.jpg` / `cover-3x4-1080x1440.jpg` / `cover-16x9-1920x1080.jpg`）
- preview: done（`2026-11-19-review-preview.edl`；layout 含 close 左右对比数据图三对同步轮播）
- qc: pending
- subs: waiting-review（`episodes/2026-11-19-lt-revenge/subtitles.txt`；等用户改错字和换行）
- loudness: done（`--measure-only` 已测）
- burn: deprecated
- final: pending
- upload: pending

## close 左右对比贴图

program.json overlays（role=stats），close 成片窗均分三步同步：

1. 左 `stats-01` / 右 `stats-03`（完整总览）
2. 左 `stats-02` / 右 `stats-04`（各组圈速）
3. 左 `stats-06` / 右 `stats-05`（地图+温度；今天是 06）

左 x=`40`，右 x=`W-w-40`。未改共享工具。
