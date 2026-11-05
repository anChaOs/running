# 2026-11-05 ai-pipeline 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-05-ai-pipeline/`

## 重命名结果

### 视频素材

- `VID_20261105_054156.mp4` -> `2026-11-05-open.mp4`（粗剪后；原片 `2026-11-05-open-raw.mp4`）
- `VID_20261105_054750.mp4` -> `2026-11-05-run-a.mp4`
- `VID_20261105_062852.mp4` -> `2026-11-05-run-b.mp4`
- `VID_20261105_064040.mp4` -> `2026-11-05-run-c.mp4`
- `VID_20261105_064143.mp4` -> `2026-11-05-run-d.mp4`
- `VID_20261105_070617.mp4` -> `2026-11-05-run-e.mp4`
- `VID_20261105_071635.mp4` -> `2026-11-05-close.mp4`（粗剪后；原片 `2026-11-05-close-raw.mp4`）

### 跑步数据

- COROS MCP 下载 -> `2026-11-05-run-data.fit`（乳酸阈间歇；records 05:44:00→07:12:53；FIT 18.195 km；COROS 摘要 18.20 km / 1:28:53 / 4:53 / HR166）

### 截图 / 封面

- 分段成绩（先）`Screenshot_…07-23-57…` -> `2026-11-05-stats-01.jpg`（close 叠图每 40s 循环，排前）
- 总览（后）`Screenshot_…07-23-45…` -> `2026-11-05-stats-02.jpg`
- 封面自拍：`1793834657970.jpg`

## 时间顺序依据

- 05:41:56: `open`
- 05:47:50: `run-a`
- 06:28:52: `run-b`
- 06:40:40: `run-c`
- 06:41:43: `run-d`
- 07:06:17: `run-e`
- 07:16:35: `close`

## 素材关联

- `open`：`2026-11-05-open.mp4`
- `run-a`：`2026-11-05-run-a.mp4`
- `run-b`：`2026-11-05-run-b.mp4`
- `run-c`：`2026-11-05-run-c.mp4`
- `run-d`：`2026-11-05-run-d.mp4`
- `run-e`：`2026-11-05-run-e.mp4`
- `close`：`2026-11-05-close.mp4`
- FIT：`2026-11-05-run-data.fit`
- close-stats：`stats-01`（分段）→`stats-02`（总览），每 40s
- 冷开场钩子（用户口述，相对 **close-raw**；粗剪约省 7.6s，assemble 前在 trimmed close 复核）：
  1. ~40s「到底在整个Agent循环扮演什么样的角色呢？」
  2. ~3:10「是不是就是因为他的token特别多呢？」
  3. ~3:47「token是不是越多越厉害呢？」

## 制作状态

- ingest: done
- shoes: done（惊碳Fly；`-sn "惊碳Fly" -sk 1422.20`；跑完后；FIT 18.195）
- hud: done（`-sn "惊碳Fly" -sk 1422.20`；`--jobs 2`；`--preview`；Open-Meteo archive 400→forecast fallback；preview 句间粗剪已 apply，`keep_lead_silence=True`；raw 备份 `*-hud-preview-raw.mp4`）
- cover: done（句「Token越多越厉害？」三行 `Token|越多|越厉害？`；自拍 `1793834657970.jpg`；仅保留三比例：`cover-4x3-1920x1440.jpg` / `cover-3x4-1080x1440.jpg` / `cover-16x9-1920x1080.jpg`；无 cover.jpg 别名）
- assemble: pending
- qc: pending
- loudness: pending
- subs: pending
- burn: pending
- upload: pending
