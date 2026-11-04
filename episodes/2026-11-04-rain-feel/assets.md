# 2026-11-04 rain-feel 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-04-rain-feel/`

## 重命名结果

### 视频素材

- `VID_20261104_063829.mp4` -> `2026-11-04-run-a.mp4`（无 open；直接从 run 开始）
- `VID_20261104_071838.mp4` -> `2026-11-04-close.mp4`（粗剪后；原片 `2026-11-04-close-raw.mp4`）

### 跑步数据

- `2026-11-04-run-data.fit`（COROS MCP URL + curl；labelId 481505597806641157）

### 截图 / 封面

- `Screenshot_2026-11-04-07-22-57-279_*.jpg` -> `2026-11-04-stats-01.jpg`（总览，close 第一张叠图）
- `Screenshot_2026-11-04-07-23-05-519_*.jpg` -> `2026-11-04-stats-02.jpg`（每公里，close 第二张叠图）
- `1793748234852.jpg`：封面自拍（cover 用）

## 时间顺序依据

- 06:38:29: `run-a`（~229s）
- 07:18:38: `close`（raw ~95.58s → 事故后重 trim keep_lead → **92.519s**；旧误 trim 90.25s 裁掉片头「完了」；见 media `logs/failures.md` ACCIDENT）

## 素材关联

- `run-a`：`2026-11-04-run-a.mp4`
- `close`：`2026-11-04-close.mp4`（`*-close-raw.mp4` 保留）
- FIT：`2026-11-04-run-data.fit`
- stats：`2026-11-04-stats-01.jpg`（总览）→ `2026-11-04-stats-02.jpg`（每公里）
- cover selfie：`1793748234852.jpg`

## assemble 提示（close 叠图）

close 一开始贴总览；念到「我会把我的心率贴在…」时（ASR cue @ close **32.86s**，restore lead 后）切到每公里。
文件名已与内容对齐：`stats-01.jpg`=总览，`stats-02.jpg`=每公里。holds=`30.15,60.096`。

## 鞋

- HUD：`-sn "SC Trainer" -sk 2514.00`（用户口述跑完后；FIT 本场 16.408 km；开跑前 2497.59）

## 制作状态

- ingest: done（`--no-open`；close pause-trim done）
- shoes: done（-sn SC Trainer -sk 2514.00）
- hud: done（-sn SC Trainer -sk 2514.00；alpha+preview；preview pause-trim ~229.03s→~195.93s；raw 保留）
- cover: done（主推：今天体感不错？；16:9/4:3/3:4 + cover.jpg；2026-11-04 08:06 换句重排；按 p3-cover 不进 run-final，片头仍是 run HUD）
- close-stats: done（restore 08:28：总览 0–32.86 → 每公里 32.86–92.519；cue @32.86；stats-01=总览 stats-02=每公里）
- assemble: done（restore 08:31；`2026-11-04-run-final.mp4` **288.300s≈4:48**；无 open；hud-preview 195.933 + close-stats 92.519；响度 ON）
- qc: done（restore 帧：close 片头「完了」+总览、cue@32.86 切每公里；final qc/restore-final-*）
- loudness: done（restore 成片 I=-16.07 LUFS TP=-0.55 dBTP LRA=4.60；TP soft ⚠）
- subs: done（用户确认仅改「完了」→「跑完了」；时间 0:03:16.33–0:03:17.80；txt_to_subs 同步；未重跑 force_align）
- burn: done（Source Han Sans SC Heavy 72 / Outline=3 / MarginV=100；fontselect→~/Library/Fonts/SourceHanSansSC-Heavy.otf；-c:a copy；out 今天体感不错？.mp4 547M / 288.300s）
- upload: ready（成片名已改；外挂 subtitles.srt；封面 cover-*.jpg；等双链）

## 事故（2026-11-04）
close 句间粗剪默认 `keep_lead_silence=False` + VAD 漏检短句「完了」→ 片头被裁 ~2.27s。已 keep_lead 重 trim 并默认改为保留片头。详情：媒体目录 `logs/failures.md` / `logs/timeline.txt`。

## 字幕定稿备注（2026-11-04 08:45+）

- 用户确认 close 片头口播是 **「跑完了」**，不是「完了」。事故日志里仍写作「完了」的是当时 ASR/补字幕误写；成片轴 cue 已改为「跑完了」。
