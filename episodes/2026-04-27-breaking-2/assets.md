# 2026-04-27 第五期素材索引

## 本地素材目录

`~/Movies/running-content/2026-04-27-breaking-2/`

> 说明：本仓库该期目录只保留素材索引；原始视频和 FIT 数据保留在本地素材目录。

## 重命名结果

### 视频素材

- `VID_20260427_054729.mp4` -> `2026-04-27-open.mp4`
- `VID_20260427_055217.mp4` -> `2026-04-27-run-a.mp4`
- `VID_20260427_063135.mp4` -> `2026-04-27-run-b.mp4`
- `VID_20260427_065310.mp4` -> `2026-04-27-run-c.mp4`
- `VID_20260427_071954.mp4` -> `2026-04-27-close.mp4`

### 跑步数据

- `乳酸阈20260427054907.fit` -> `2026-04-27-run-data.fit`

## 时间顺序依据

- 05:47:29：`open`
- 05:52:17：`run-a`
- 06:31:35：`run-b`
- 06:53:10：`run-c`
- 07:19:54：`close`

## 素材关联

- 开场：`2026-04-27-open.mp4`
- 跑中 A：`2026-04-27-run-a.mp4`
- 跑中 B：`2026-04-27-run-b.mp4`
- 跑中 C：`2026-04-27-run-c.mp4`
- 收尾：`2026-04-27-close.mp4`
- FIT 数据：`2026-04-27-run-data.fit`

## 备注

- 主题目录 `2026-04-27-breaking-2` 已保留这期素材的主题语义，后续脚本、封面句或成片命名可以直接复用。
- 当前素材数量对应 `open + 3 段跑中 + close`，所以未扩展到 `run-d`。
- 如果后续补充跑步数据截图、HUD 导出或成片，建议继续沿用：
  - `2026-04-27-run-data.*`
  - `2026-04-27-run-hud-overlay.*`
  - `2026-04-27-run-final.*`

## 制作状态

- ingest: done
- hud: done（`-sn "SC Trainer" -sk 2143.72`；开跑前 2127.19，FIT 16.533；抽帧 run-a 2128 / run-b 2135 / run-c 2140→2141；天气 `°C`，上海城市场点）
- cover: waiting-review（原片 run-a 80s 黄车+路沿；备选 8s 栅栏）
- subs: done（171 条；人手改字后对口型回写；外挂 `subtitles.srt` / `2026-04-27-run-final.srt`；未烧进成片）
- assemble: done（`2026-04-27-run-final.mp4` HEVC 1080p60 565.53s ~27Mbps 1.8G，无字幕轨）
- qc: done（open 无 HUD；open→run HUD 入、SC Trainer 2128、15°C；run-c 2140 / 16°C / 17°C；run→close HUD 出 2141；close 无 HUD）
- cleanup: done（7.6G → 3.6G；已删 HUD preview/alpha、听写 wav、qc 抽帧；原片 / 成片 / FIT / 封面 / SRT / weather / asr 稿留下）
