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
- `VID_20261107_165012.mp4` -> `2026-11-07-run-e-4k.mp4`（4K 原片）+ 工作 `2026-11-07-run-e.mp4`（1080，mtime 同 16:50:31，供 HUD）
- `VID_20261107_165112.mp4` -> `2026-11-07-close.mp4`（粗剪后；原片 `2026-11-07-close-raw.mp4`）

### 高驰截图（assemble 叠到 close 左侧）

- `Screenshot_2026-11-07-17-17-56-882_com.yf.smart.coros.dist.jpg` -> `2026-11-07-stats-01.jpg`
- `Screenshot_2026-11-07-19-00-38-476_com.yf.smart.coros.dist.jpg` -> `2026-11-07-stats-02.jpg`

### 跑步数据

- COROS MCP `labelId=481584378242170883`（Outdoor Run / sportType 100）-> `2026-11-07-run-data.fit`（16:10:39→16:50:41 Asia/Shanghai）

### 其他图片

- `1794049313024.jpg`：横屏自拍（赛事墙背景）——**封面源图**（已翻转去镜像 + rembg；cover done）
- `1794049615268.jpg`：奖牌平铺源图；合成 `medal-with-rank.jpg`（上半「第二名」）经 `overlays.json` 叠进 close 右侧（width=560，fade 0.35）；**不当封面**

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

## 鞋

- HUD：`-sn "Pure 2.0" -sk 176.68`（用户口述跑完后；FIT 本场 9.369 km；开跑前 167.31）

## 制作状态

- ingest: done（open 两段先 `-c copy` 拼再句间粗剪；close 单段粗剪；vad + keep_lead_silence；open 约省 14.23s、close 约省 0.80s；`*-raw` / open-part*-raw 保留；**未动 run-***）
- shoes: done（Pure 2.0 全天候；`-sn "Pure 2.0" -sk 176.68`；跑完后；FIT 9.369 km）
- hud: done（`-sn "Pure 2.0" -sk 176.68`；`--jobs 2`；`--preview`；`--weather-city shanghai`；preview 句间粗剪已 apply，`keep_lead_silence=True`；a/b/c/d 有剪、e 无剪；raw 备份 `*-hud-preview-raw.mp4`；**run-e 原片 4K→工作文件先缩到 1080 再渲 HUD**（4K 备份 `2026-11-07-run-e-4k.mp4`，mtime 保留 16:50:31；错误的 4K-layout preview 备份 `hud-renders/…-hud-preview-4k.mp4`；已按 1920×1080 重渲 e））
- cover: done（句「湖边10km比赛 | 第二名？」排版断行 `湖边|10km|第二名？`（字号硬性下限下省略「比赛」）；自拍 `1794049313024.jpg` 先水平翻转去镜像再 rembg；设计底 `cover-work/bg.jpg`；三比例：`cover-4x3-1920x1440.jpg` / `cover-3x4-1080x1440.jpg` / `cover-16x9-1920x1080.jpg`；奖牌图不当封面）
- assemble: done（片头 hook≈2.72s 硬切进 open-body；open+5 HUD preview+close-stats；风转场；奖牌 `medal-with-rank.jpg` overlays.json width=560；拼时响度；成片 `2026-11-07-run-final.mp4` ≈**237.40s**；**run-e HUD 已按 1080 正确布局重渲后重拼**）
- qc: done（`qc/00-hook-text`…`06-close-end.jpg`；hook 文案在 OUTLETS 下；open/close 无 HUD；跑中 HUD 鞋名 Pure 2.0、气温 °C；close 左 stats + 右奖牌）
- loudness: done（拼时两遍 loudnorm；成片实测 I=-16.07 LUFS / TP=-0.96 dBTP / LRA=5.40；脚本提示 TP 略超 -1.0）
- open-hook: done（自拍静帧 `cover-work/selfie-flipped.jpg` + ASS 逐字「猜猜我第几名？」+ 合成打字机音；`open-hook/open-hook.mp4`≈2.72s；硬切拼进 `2026-11-07-open.mp4`；口播开场备份 `2026-11-07-open-body.mp4`）
- subs: done
- burn: done（ASS Source Han Sans SC Heavy 72 / Outline 3 / MarginV=100；fontselect→SourceHanSansSC-Heavy；burn_ass.py；-c:a copy；成片 ≈237.40s / 454M；无烧字备份已进废纸篓）
- upload: ready
