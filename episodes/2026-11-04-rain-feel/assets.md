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
- 07:18:38: `close`（raw ~95.58s → trim ~90.25s；句间 5 处，均值 0.84s，keep≈0.64s）

## 素材关联

- `run-a`：`2026-11-04-run-a.mp4`
- `close`：`2026-11-04-close.mp4`（`*-close-raw.mp4` 保留）
- FIT：`2026-11-04-run-data.fit`
- stats：`2026-11-04-stats-01.jpg`（总览）→ `2026-11-04-stats-02.jpg`（每公里）
- cover selfie：`1793748234852.jpg`

## assemble 提示（close 叠图）

close 一开始贴总览；念到「我会把我的心率贴在…」时（ASR cue @ close **30.15s**）切到每公里。
文件名已与内容对齐：`stats-01.jpg`=总览，`stats-02.jpg`=每公里。holds=`30.15,60.096`。

## 鞋

- HUD：`-sn "SC Trainer" -sk 2514.00`（用户口述跑完后；FIT 本场 16.408 km；开跑前 2497.59）

## 制作状态

- ingest: done（`--no-open`；close pause-trim done）
- shoes: done（-sn SC Trainer -sk 2514.00）
- hud: done（-sn SC Trainer -sk 2514.00；alpha+preview；preview pause-trim ~229.03s→~195.93s；raw 保留）
- cover: done（主推：今天体感不错？；16:9/4:3/3:4 + cover.jpg；2026-11-04 08:06 换句重排；按 p3-cover 不进 run-final，片头仍是 run HUD）
- close-stats: done（fix 08:06：总览 0–30.15 → 每公里 30.15–90.25；cue 切点不变 @30.15；已交换文件名对齐内容）
- assemble: done（reassemble 08:08；`2026-11-04-run-final.mp4` 286.0s≈4:46；无 open；hud-preview + close-stats；响度链默认 ON）
- qc: done（fix 帧：close/final 早段总览、cue 前后切每公里；鞋 SC Trainer；气温 16°）
- loudness: done（重拼带；成片 I=-16.08 LUFS TP=-1.21 dBTP LRA=4.60）
- subs: draft（subtitles.txt/srt 已出；人手改字前停；切条已轻拆长句；未 force_align）
- burn: pending
- upload: pending
