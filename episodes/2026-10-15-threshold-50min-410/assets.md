# 2026-10-15 threshold-50min-410 素材索引

## 本地素材目录

`~/Movies/running-content/2026-10-15-threshold-50min-410/`

## 重命名结果

### 视频素材

- `VID_20261015_054614.mp4` -> `2026-10-15-open.mp4`（粗剪后；原片 `2026-10-15-open-raw.mp4`）
- `VID_20261015_061504.mp4` -> `2026-10-15-run-a.mp4`
- `VID_20261015_065300.mp4` -> `2026-10-15-run-b.mp4`
- `VID_20261015_070113.mp4` -> `2026-10-15-run-c.mp4`
- `VID_20261015_072439.mp4` + `VID_20261015_072527.mp4` -> `2026-10-15-close.mp4`（先 ffmpeg concat demuxer `-c copy` 拼成一段，再句间粗剪；拼接未剪原片 `2026-10-15-close-raw.mp4`；分镜源 `2026-10-15-close-part1-raw.mp4` / `2026-10-15-close-part2-raw.mp4`）

### 高驰截图（assemble 全进成片）

叙事顺序（非文件名时间序）：

- `Screenshot_…07-31-17…` -> `2026-10-15-stats-01.jpg`（带地图的完成页）
- `Screenshot_…07-31-30…` -> `2026-10-15-stats-02.jpg`（各公里分段）
- `Screenshot_…07-31-02…` -> `2026-10-15-stats-03.jpg`（能力图；LT 已更新到 4:10）

### 跑步数据

- COROS MCP `labelId=481041874751095188` -> `2026-10-15-run-data.fit`

### 封面原图

- `1792020720563.jpg`（6528×4896 自拍；rembg 抠图源）
- 成图（主推 **charcoal-volt**：炭黑底 + 荧光黄光斑；封面字「手表给的乳酸阈值／能跑出来吗？」+「破三实验室」；咬牙咧嘴表情；粗白描边；无备选）
  - `cover.jpg` / `cover-1920x1080.jpg` / `cover-16x9-1920x1080.jpg`（16:9）
  - `cover-4x3-1920x1440.jpg`（4:3）
  - `cover-1080x1440.jpg` / `cover-3x4-1080x1440.jpg`（3:4）
  - 中间件：`cover-work/person-cutout.png`、`cover-work/person-outlined.png`

## 时间顺序依据

- 05:46:14: `open`（mtime 结束约 05:48:26）
- 06:15:04: `run-a`（mtime 06:16:48）
- 06:53:00: `run-b`（mtime 06:53:27）
- 07:01:13: `run-c`（mtime 07:02:01）
- close：两段 VID 07:24:39 + 07:25:27；拼接件 mtime 对齐 part2 结束 `07:27:57`（`close-raw`）；粗剪工作文件 mtime 为剪完时刻

## 素材关联

- 开场：`2026-10-15-open.mp4`
- 跑中 A：`2026-10-15-run-a.mp4`
- 跑中 B：`2026-10-15-run-b.mp4`
- 跑中 C：`2026-10-15-run-c.mp4`
- 收尾：`2026-10-15-close.mp4`
- FIT：`2026-10-15-run-data.fit`
- 截图：`2026-10-15-stats-01.jpg` / `02` / `03`

## close 叠片动画（assemble 必用）

目录：`~/Movies/running-content/2026-10-15-threshold-50min-410/overlays/`（左半屏；透明用 `.mov`，预览用 `-darkbg.mp4`）

| 文件 | 对应 close 口播 |
|---|---|
| `lt-01-produce` | 快供能靠糖 → 糖酵解 → 丙酮酸 → 乳酸（非「这时才开始有」） |
| `lt-02-reuse` | 产生乳酸的肌肉 → 丙酮酸 → 线粒体氧化；血液 → 心脏/慢肌 |
| `lt-03-threshold` | 生成≈清除稳态 vs 生成>清除堆积≈过乳酸阈；手表原 4:16 |

详见 overlays/`README-overlays.md`。

**assemble 提醒**：close 叠三张 LT 动画 + 三张 stats（含能力图 4:10），不要只留 overlays 目录不用。

## 本场要点（给 HUD / 口播核对）

- 全程约 18.16 km / 1:28:16
- 主段约 50′ 均配 **4:08**（心率约 182）
- 手表乳酸阈更新到 **4:10**（全马预测约 3:10:28）

## HUD

- `-sn` Plaid 1.5 / `-sk` 516.03（FIT 18.164 km → 开跑前 497.87）
- 产出：`hud-renders/2026-10-15-run-{a,b,c}-hud-alpha.mov` + `*-hud-preview.mp4`（已句间粗剪；未剪备份 `*-hud-preview-raw.mp4`）
- preview 时长（粗剪后）：run-a ≈ 91.8s / run-b ≈ 22.6s / run-c ≈ 44.6s
- 天气：`--weather-city shanghai`（城市场点，未发 FIT GPS）

## close 叠片时间轴（成片已用）

原 `2026-10-15-close.mp4` 不动。工作文件：`2026-10-15-close-stats.mp4`（assemble 优先选用）。

| 时段（close 内） | 内容 |
|---|---|
| 0–34.3s | stats-01 地图完成页 → stats-02 分段 → stats-03 能力图（各约 11.4s，半透明左侧） |
| 34.3–46.3s | `overlays/lt-01-produce.mov`（12s，左半屏） |
| 76.3–86.3s | `overlays/lt-02-reuse.mov`（10s） |
| 105.3–118.3s | `overlays/lt-03-threshold.mov`（13s） |
| 151s–end | 无叠片（结尾疑问） |

ASR 对齐稿：`qc/close-asr.txt`；cue 摘要：`qc/close-overlay-cues.txt`。

## 成片

- `2026-10-15-run-final.mp4`（≈469.5s / 887M；loudness 链 ON）
- 响度（loudnorm summary）：I ≈ **−15.9 LUFS**，TP ≈ **−0.7 dBTP**，LRA ≈ 5.2（目标 I=-16 / TP≤-1.5；峰值略热，未二次整轨抬增益）
- QC 抽帧：`qc/final-*.jpg` + close 叠片核对帧 `qc/close-*.jpg`

## 制作状态

- ingest: done
- hud: done（-sn Plaid 1.5 / -sk 516.03）
- subs: waiting-review（force_align+check_subs 已跑，机器过门；硬失败 3 条漏盖 + interp #70 待人听确认后才写 done）
- cover: done（主推 charcoal-volt；16:9/4:3/3:4 已落媒体目录）
- assemble: done（close-stats = 三 stats + 三 LT；loudness 链默认开）
- qc: done（拼后抽帧 + LUFS）
