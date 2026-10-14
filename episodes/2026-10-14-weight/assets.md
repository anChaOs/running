# 2026-10-14 weight 素材索引

## 本地素材目录

`~/Movies/running-content/2026-10-14-weight/`

## 重命名结果

### 视频素材

- `VID_20261014_055304.mp4` -> `2026-10-14-open.mp4`（句间粗剪后；原片 `2026-10-14-open-raw.mp4`）
- `VID_20261014_060007.mp4` -> `2026-10-14-run-a.mp4`
- `VID_20261014_063446.mp4` -> `2026-10-14-run-b.mp4`
- `VID_20261014_072006.mp4` -> `2026-10-14-close.mp4`（句间粗剪后；原片 `2026-10-14-close-raw.mp4`）

### 跑步数据

- `2026-10-14-run-data.fit` ← 高驰 MCP（户外跑 LabelId 481018626896330754 / 14.66 km / 05:54–07:16）

### 截图与封面原图

- COROS 截图已改名：`2026-10-14-stats-01.jpg`
- 自拍原图：`1791934103558.jpg`（封面主推用）
- 封面定稿：**E-mint-paper**（薄荷绿纸感；句「瘦下来就能破三？」；人物放大约 90% 高；双手/捏肚子完整；粗白描边）
  - 根目录：`cover.jpg` / `cover-1920x1080.jpg`（16:9）、`cover-4x3-1920x1440.jpg`（4:3）、`cover-1080x1440.jpg`（3:4）
  - 候选留档：`cover-candidates/E-mint-paper-*.jpg`（已同步为放大版）

## 时间顺序依据

- 05:53:04: `open`
- 06:00:07: `run-a`
- 06:34:46: `run-b`
- 07:20:06: `close`

## 素材关联

- `open`：`2026-10-14-open.mp4`
- `run-a`：`2026-10-14-run-a.mp4`
- `run-b`：`2026-10-14-run-b.mp4`
- `close`：`2026-10-14-close.mp4`
- FIT：`2026-10-14-run-data.fit`
- stats：`2026-10-14-stats-01.jpg`

## mtime（HUD 用 run-*）

- open-raw：2026-10-14 05:54:30 +0800（ok）
- run-a：2026-10-14 06:02:55 +0800（ok）
- run-b：2026-10-14 06:39:53 +0800（ok）
- close-raw：2026-10-14 07:26:04 +0800（ok）
- open/close 工作文件粗剪后 mtime 为剪辑时间，不影响 HUD

## 制作状态

- ingest: done
- shoes: done（C202 7，跑后 360.91 km）
- hud: done（`-sn "C202 7" -sk 360.91`；开跑前 346.25，FIT 14.662；天气 shanghai；preview 已句间粗剪：run-a 166.63s→163.03s、run-b 306.63s→291.70s；未剪为 `*-hud-preview-raw.mp4`）
- subs: done（force_align 283 条：整条 272 / 短窗 6 / interp 5 / unanchored 0；check_subs 机器过门；硬失败漏盖 1 条 13:21.30–13:21.82「把之前」旁 0.52s；用户确认口型后发布）
- upload: done（成片「体重 | 减肥能帮我破三吗？.mp4」；外挂 subtitles.srt）
- published:
  - YouTube：https://youtu.be/Ms-rZwFUyaQ
  - Bilibili：BV1Kypy6hEui（https://www.bilibili.com/video/BV1Kypy6hEui）
- cover: done（选用 E-mint-paper 放大版；16:9/4:3/3:4 已覆盖根目录 cover*.jpg；双手/捏肚子完整）
- assemble: done（`2026-10-14-run-final.mp4` **892.4s**；close-stats 曾截成 131s 已重渲满长 354s 后重拼；loudnorm 链同 assemble-1014（dynaudnorm+loudnorm I=-16/TP=-1.5），峰值 max_volume −1.3 dB。备份：`close-stats-TRUNCATED-131s.mp4` / `run-final-TRUNCATED-close.mp4` / `run-final-pre-loudnorm.mp4`。**字幕须按新成片重转写**；`subtitles.txt` 用户改稿未动）
- qc: done（抽帧 qc/01–05：open/close 无 HUD；跑中 C202 7 / °C；接缝正常）
