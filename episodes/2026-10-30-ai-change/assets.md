# 2026-10-30 ai-change 素材索引

## 本地素材目录

`~/Movies/running-content/2026-10-30-ai-change/`

## 重命名结果

### 视频素材

- `VID_20261030_055018.mp4` -> `2026-10-30-open.mp4`
- `VID_20261030_060040.mp4` -> `2026-10-30-run-a.mp4`
- `VID_20261030_062242.mp4` -> `2026-10-30-run-b.mp4`
- `VID_20261030_065052.mp4` -> `2026-10-30-run-c.mp4`
- `VID_20261030_071559.mp4` -> `2026-10-30-close.mp4`

### 跑步数据

- `2026-10-30-run-data.fit`（用户拷贝自 `上海市_跑步20261030055225.fit`；COROS 14.03 km）

## 时间顺序依据

- 05:50:18: `open`
- 06:00:40: `run-a`
- 06:22:42: `run-b`
- 06:50:52: `run-c`
- 07:15:59: `close`

## 素材关联

- `open`：`2026-10-30-open.mp4`
- `run-a`：`2026-10-30-run-a.mp4`
- `run-b`：`2026-10-30-run-b.mp4`
- `run-c`：`2026-10-30-run-c.mp4`
- `close`：`2026-10-30-close.mp4`
- FIT：`2026-10-30-run-data.fit`
- 封面自拍：`1793316289316.jpg`
- stats：`2026-10-30-stats-01.jpg`

### 封面成图

- 句：「AI，让我有点怕」+「破三实验室」（手排断行：AI，|让我|有点怕）
- 流程：自拍 `1793316289316.jpg` → onnx/u2net 抠图 → 粗白描边 → 暗青霓虹创意底 → 三比例手排
- 中间件：`cover-work/person-cutout.png`、`cover-work/person-outlined.png`、`cover-work/bg.jpg`
- 根目录：
  - `cover.jpg` / `cover-1920x1080.jpg` / `cover-16x9-1920x1080.jpg` — **16:9**
  - `cover-4x3-1920x1440.jpg` — **4:3**
  - `cover-1080x1440.jpg` / `cover-3x4-1080x1440.jpg` — **3:4**

## 制作状态

- ingest: done
- shoes: done (C202 7 / -sk 403.74; FIT 14.03)
- hud: done（-sn C202 7 / -sk 403.74；FIT 14.026 km；before=389.71；preview a/b/c 齐；weather shanghai）
  - 注：句间粗剪 dry-run 约省 52s，但 `--apply` 被 Auto-review 分类器反复报错拦截；成片用未粗剪 preview（keep-lead 本会保留）
- cover: done（16:9/4:3/3:4；句：AI，让我有点怕）
- assemble: done（响度链完成 → `2026-10-30-run-final.mp4` 1284.08s / 2.4G；实测 I=-16.03 LUFS / TP=-0.72 dBTP / LRA=5.20；滤镜目标 I=-16 TP=-1.5；备份 `2026-10-30-run-final-pre-loudnorm.mp4` 仍保留）
- qc: done（`qc/01..05`：open 无 HUD；run HUD 见 C2027 / °C；close 为 stats 叠层）
- subs: waiting-review（draft_subs 初稿 + 切条易错自检 + 专名/同音扫；376 条；`subtitles.txt`/`subtitles.srt`；媒体旁已拷 `subtitles.srt` + `2026-10-30-run-final.srt`；**未** force_align / 未烧 ASS）
- upload: pending
