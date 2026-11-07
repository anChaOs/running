# 2026-11-07 xtep-10k 素材索引

## 本地素材目录

`~/Movies/running-content/2026-11-07-xtep-10k/`

## 重命名结果

### 视频素材

- `VID_20261107_142219.mp4` + `VID_20261107_153453.mp4` -> `2026-11-07-open.mp4`（先 ffmpeg concat demuxer `-c copy` 拼成一段，再句间粗剪；拼接未剪原片 `2026-11-07-open-raw.mp4`；分镜源 `2026-11-07-open-part1-raw.mp4` / `2026-11-07-open-part2-raw.mp4`）
- `VID_20261107_161135.mp4` -> `2026-11-07-run-a.mp4`
- `VID_20261107_162128.mp4` -> `2026-11-07-run-b.mp4`
- `VID_20261107_163329.mp4` -> `2026-11-07-run-c.mp4`
- `VID_20261107_164430.mp4` -> `2026-11-07-run-d.mp4`
- `VID_20261107_165012.mp4` -> `2026-11-07-run-e.mp4`（4K 3840×2160）
- `VID_20261107_165112.mp4` -> `2026-11-07-close.mp4`（粗剪后；原片 `2026-11-07-close-raw.mp4`）

### 高驰截图（assemble 叠到 close 左侧）

- `Screenshot_2026-11-07-17-17-56-882_com.yf.smart.coros.dist.jpg` -> `2026-11-07-stats-01.jpg`
- `Screenshot_2026-11-07-19-00-38-476_com.yf.smart.coros.dist.jpg` -> `2026-11-07-stats-02.jpg`

### 跑步数据

- COROS MCP `labelId=481584378242170883`（Outdoor Run / sportType 100）-> `2026-11-07-run-data.fit`（16:10:39→16:50:41 Asia/Shanghai）

### 其他图片（未做 cover）

- `1794049313024.jpg`：横屏自拍（赛事墙背景）——**封面源图**（用户指定；cover 尚未做）
- `1794049615268.jpg`：奖牌平铺——close 插图/叠片素材，**不当封面**

## 时间顺序依据

- open：两段 VID 14:22:19 + 15:34:53；拼接件 mtime 对齐 part2 结束 `15:35:47`（`open-raw`）；粗剪工作文件 mtime 为剪完时刻；工作时长 ≈99.20s（raw 113.39s）
- 16:11:35: `run-a`（mtime 16:11:54）
- 16:21:28: `run-b`（mtime 16:21:56）
- 16:33:29: `run-c`（mtime 16:34:01）
- 16:44:30: `run-d`（mtime 16:45:05）
- 16:50:12: `run-e`（mtime 16:50:31）
- 16:51:12: `close`（raw mtime 16:51:35；工作时长 ≈21.28s，raw 22.06s）

## 素材关联

- 开场：`2026-11-07-open.mp4`
- 跑中 A–E：`2026-11-07-run-a.mp4` … `run-e.mp4`
- 收尾：`2026-11-07-close.mp4`
- FIT：`2026-11-07-run-data.fit`
- 截图：`2026-11-07-stats-01.jpg` / `02`
- 封面源：`1794049313024.jpg`
- 奖牌：`1794049615268.jpg`

## 制作状态

- ingest: done（open 两段先 `-c copy` 拼再句间粗剪；close 单段粗剪；vad + keep_lead_silence；open 约省 14.23s、close 约省 0.80s；`*-raw` / open-part*-raw 保留；**未动 run-***）
- shoes: pending
- hud: pending
- cover: pending（源图已定自拍 `1794049313024.jpg`）
- assemble: pending
- qc: pending
- subs: pending
- upload: pending
