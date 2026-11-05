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
- 冷开场钩子（已 prepend；源=`2026-11-05-close.mp4` trimmed，非 close-stats/HUD；硬切；ASR 复核）：
  1. close `43.52`–`48.25`「到底在整个Agent循环扮演什么样的角色呢？」（ASR≈「到底在整个agent的循环当中…什么样的决策/角色」；raw≈40s）
  2. close `188.52`–`192.40`「是不是就是因为它的token特别多呢」（raw≈3:10）
  3. close `220.84`–`223.45`「token是不是越多越厉害呢？」（raw≈3:47；句首按用户 quote 从 token 起，略去前缀「再一个是」）
  - bumper：`cold-open/hooks-bumper-60-loudnorm.mp4` offset **11.376s**
  - 备份：`2026-11-05-run-final-pre-coldopen.mp4`
  - 成片：`2026-11-05-run-final.mp4` ≈**1225.92s**（pre-coldopen 1214.681s）

## 制作状态

- ingest: done
- shoes: done（惊碳Fly；`-sn "惊碳Fly" -sk 1422.20`；跑完后；FIT 18.195）
- hud: done（`-sn "惊碳Fly" -sk 1422.20`；`--jobs 2`；`--preview`；Open-Meteo archive 400→forecast fallback；preview 句间粗剪已 apply，`keep_lead_silence=True`；raw 备份 `*-hud-preview-raw.mp4`）
- cover: done（句「Token越多越厉害？」三行 `Token|越多|越厉害？`；自拍 `1793834657970.jpg`；仅保留三比例：`cover-4x3-1920x1440.jpg` / `cover-3x4-1080x1440.jpg` / `cover-16x9-1920x1080.jpg`；无 cover.jpg 别名）
- assemble: done（open + 5 HUD preview + close-stats；风转场；拼时响度；成片含冷开场 `2026-11-05-run-final.mp4` ≈1225.92s；备份 `…-pre-coldopen.mp4`）
- cold-open: done（硬切；close trimmed 三句；offset 11.376s；详见上）
- qc: done（`qc/00-coldopen`…`05-close-end.jpg`；open/close 无 HUD；跑中 HUD 鞋名惊碳Fly、气温 °C；close 左 stats-01→02 每 40s）
- loudness: done（拼时两遍；成片实测 I=-16.03 LUFS / TP=-1.02 dBTP / LRA=4.10；bumper 单独 loudnorm I≈-15.9）
- subs: done（用户确认「可以了」；按空格重切；force_align + check_subs 过门；354 条；外挂已同步媒体目录）
- burn: done（ASS Source Han Sans SC Heavy 72 / Outline 3 / MarginV=100；fontselect→SourceHanSansSC-Heavy；burn_ass.py；-c:a copy；成片 ≈1225.92s / 2.3G；无烧字备份已进废纸篓）
- upload: ready（`upload/`：标题成片 MOVE + 三封面硬链 + subtitles.srt 硬链）
