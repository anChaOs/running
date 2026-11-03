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

说到「我会把我的心率贴在xxxx」时切截图：先 `stats-01` 总览，再切 `stats-02` 每公里。

## 鞋

- HUD：`-sn "SC Trainer" -sk 2514.00`（用户口述跑完后；FIT 本场 16.408 km；开跑前 2497.59）

## 制作状态

- ingest: done（`--no-open`；close pause-trim done）
- shoes: done（-sn SC Trainer -sk 2514.00）
- hud: running（tmux p3-hud-2026-11-04；logs/hud-render.log）
- cover: done（主推：雨里跑，随便聊聊；16:9/4:3/3:4 + cover.jpg）
- assemble: pending
- qc: pending
- loudness: pending
- subs: pending
- burn: pending
- upload: pending
