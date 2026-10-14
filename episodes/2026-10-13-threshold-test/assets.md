# 2026-10-13 threshold-test 素材索引

## 本地素材目录

`~/Movies/running-content/2026-10-13-threshold-test/`

## 重命名结果

### 视频素材

- `VID_20261013_055303.mp4` -> `2026-10-13-open.mp4`
- `VID_20261013_055602.mp4` -> `2026-10-13-run-a.mp4`
- `VID_20261013_061416.mp4` -> `2026-10-13-run-b.mp4`
- `VID_20261013_062622.mp4` -> `2026-10-13-run-c.mp4`
- `VID_20261013_062833.mp4` -> `2026-10-13-run-d.mp4`
- `VID_20261013_063128.mp4` -> `2026-10-13-run-e.mp4`
- `VID_20261013_071404.mp4` -> `2026-10-13-close.mp4`

### 跑步数据

- `2026-10-13-run-data.fit` -> `2026-10-13-run-data.fit`


### 口播叠加素材（已就绪）

- `lt-pace-2025-10-to-2026-04.jpg` — 高驰乳酸阈配速半年曲线（2025-10-12 → 2026-04-18；半年均 4'07"；1 月峰值约 4:00）
- `lt-pace-2026-04-to-2026-10.jpg` — 高驰乳酸阈配速半年曲线（2026-04-07 → 2026-10-12；半年均 4'10"；7 月掉到约 4:15–4:18，现在约 4:21）
- `lt-pace-before-test.jpg` — 测前阈值参考

叠图约定：run-a 说到 4:00 峰值叠第一张；说到 7 月掉点叠第二张；说到现在 4:21 叠测前截图；close 用 stats 左侧轮播（含测前/测后对比）。成片已落地，见制作状态。

### 高驰截图（stats）

- `Screenshot_…07-30-57….jpg` -> `2026-10-13-stats-01.jpg`
- `Screenshot_…07-31-11….jpg` -> `2026-10-13-stats-02.jpg`
- `Screenshot_…07-31-33….jpg` -> `2026-10-13-stats-03.jpg`

拼成片时叠到 close 左侧。

### 封面原图

- `1791847311156.jpg`（手持自拍；拍摄单要 2 张，目前 1 张；本期按 1 张推进）
- 抠图：`cover-candidates/cover-cutout.png`（rembg/u2net 真人像素；`cover-cutout-stroke.png` 粗白描边）
- 定稿封面（选用 **A** 实验室数据风；句「乳酸阈值掉到 4:21？」）：
  - `cover.jpg` / `cover-1920x1080.jpg` / `cover-16x9-1920x1080.jpg` — **16:9**
  - `cover-4x3-1920x1440.jpg` — **4:3**
  - `cover-1080x1440.jpg` / `cover-3x4-1080x1440.jpg` — **3:4**（手排，非裁切）
  - 候选仍留在 `cover-candidates/`（含 B/C 备选与 cutout）

## 时间顺序依据

- 05:53:03: `open`
- 05:56:02: `run-a`
- 06:14:16: `run-b`
- 06:26:22: `run-c`
- 06:28:33: `run-d`
- 06:31:28: `run-e`
- 07:14:04: `close`

## 素材关联

- `open`：`2026-10-13-open.mp4`
- `run-a`：`2026-10-13-run-a.mp4`
- `run-b`：`2026-10-13-run-b.mp4`
- `run-c`：`2026-10-13-run-c.mp4`
- `run-d`：`2026-10-13-run-d.mp4`
- `run-e`：`2026-10-13-run-e.mp4`
- `close`：`2026-10-13-close.mp4`
- FIT：`2026-10-13-run-data.fit`

## 制作状态

- ingest: done
- hud: done（`-sn "Plaid 1.5" -sk 492.70`；开跑前 483.91，FIT 8.787；天气 shanghai；run-a/d/e preview 已句间粗剪，run-b/c 无超长停顿未剪；用户口述阈值+慢跑后 497.87）
- subs: done
- cover: done（选用 A；16:9 cover.jpg/cover-1920x1080/cover-16x9；4:3 cover-4x3-1920x1440；3:4 cover-1080x1440；句：乳酸阈值掉到 4:21？）
- assemble: done（`2026-10-13-run-final.mp4`，9:19.7；open→run-a…e→close-stats；风转场；峰值 −1.1 dB，已用 limiter；无 limiter 备份 `2026-10-13-run-final-pre-limiter.mp4`）
  - LT 叠图（右侧竖屏，不挡 HUD 胶囊）：
    - `lt-pace-2025-10-to-2026-04.jpg` ≈ 成片 185s（run-a 峰值/4:01 段）
    - `lt-pace-2026-04-to-2026-10.jpg` ≈ 成片 270s（run-a 7 月掉点段）
    - `lt-pace-before-test.jpg` ≈ 成片 285s（run-a 说到现在 4:21）
  - close：`*-close-stats.mp4` 已叠 stats-01/02/03 左侧轮播
- qc: done（`qc/01-open-start.jpg` … `qc/10-close-end.jpg`；鞋 Plaid 1.5、末段约 492 km；气温 °C；open/close 无 HUD）
- upload: done（成片已改名为《高驰体能测试 | 乳酸阈配速多少？.mp4》；外挂 subtitles.srt）
- published:
  - YouTube：https://youtu.be/gSJVibcJlYI
  - Bilibili：BV1sdWF6ME8a（https://www.bilibili.com/video/BV1sdWF6ME8a）
- post-publish cleanup: 待用户确认后进废纸篓（清单见发布后对话）
