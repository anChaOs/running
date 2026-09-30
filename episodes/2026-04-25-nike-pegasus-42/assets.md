# 2026-04-25 第三期素材索引

## 本地素材目录

`~/Movies/running-content/2026-04-25-nike-pegasus-42/`

> 说明：本仓库该期目录只保留素材索引；原始视频和 FIT 数据保留在本地素材目录。

## 重命名结果

### 视频素材

- `VID_20260425_155728.mp4` -> `2026-04-25-open.mp4`
- `VID_20260425_161215.mp4` -> `2026-04-25-run-a.mp4`
- `VID_20260425_161852.mp4` -> `2026-04-25-run-b.mp4`
- `VID_20260425_163728.mp4` -> `2026-04-25-run-c.mp4`
- `VID_20260425_172237.mp4` -> `2026-04-25-run-d.mp4`
- `VID_20260425_173132.mp4` -> `2026-04-25-close.mp4`

### 跑步数据

- `上海市_跑步20260425161205.fit` -> `2026-04-25-run-data.fit`

## 时间顺序依据

- 15:57:28：`open`
- 16:12:15：`run-a`
- 16:18:52：`run-b`
- 16:37:28：`run-c`
- 17:22:37：`run-d`
- 17:31:32：`close`

## 素材关联

- 开场：`2026-04-25-open.mp4`
- 跑中 A：`2026-04-25-run-a.mp4`
- 跑中 B：`2026-04-25-run-b.mp4`
- 跑中 C：`2026-04-25-run-c.mp4`
- 跑中 D：`2026-04-25-run-d.mp4`
- 收尾：`2026-04-25-close.mp4`
- FIT 数据：`2026-04-25-run-data.fit`

## 备注

- 主题目录名已包含鞋款信息 `nike-pegasus-42`，后续剪辑和脚本可以直接复用这个主题语义。
- 这一期比前两期多一段跑中素材，因此用了 `run-d`。
- 如果后续补充跑步数据截图、HUD 导出或成片，建议继续沿用：
  - `2026-04-25-run-data.*`
  - `2026-04-25-run-hud-overlay.*`
  - `2026-04-25-run-final.*`

## 制作状态

- ingest: done
- hud: done（`-sn "Pegasus 42" -sk 13.13`；鞋里程从 0 滚到 13，抽帧 run-a 0 / run-b 1 / run-c 5 / run-d 13）
- subs: done（`episodes/2026-04-25-nike-pegasus-42/subtitles.{txt,srt}`；媒体目录外挂 SRT，未烧进成片）
- cover: done（001 店租赁展台原图 `cover-source.jpg`；红黑底、底栏白字）
- assemble: done（`2026-04-25-run-final.mp4`，589.0s，无字幕流；close 用 `2026-04-25-close-overlay.mp4`，左侧叠挑战榜 88% 不透明，原 `*-close.mp4` 未改）
- qc: done
