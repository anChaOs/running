---
name: p3-assemble
description: 拼画面：把 open + HUD preview + close 拼成全长成片，拼完立刻抽帧核对。两端 0.2s 叠化、run 默认一阵风刮过+风声。推荐拼时带响度（不加 --no-loudness-fix）；急着先转写才加 --no-loudness-fix。本步不加 --ass。用户说拼接、转场、assemble、拼画面、成片导出时用。不要在这里渲 HUD、写字幕或烧字。只再核对一次走 p3-qc。
---

# 拼画面

把已有 HUD preview 拼成一条全长成片，**拼完立刻抽帧核对画面**。不要停下来等人发 `/p3-qc`。这不是 60–90 秒发布剪辑。

产物：`~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4`

## 编码成本

当前 `assemble_episode.py` 只有一条路：从 open + HUD preview + close **全量重拼**。loudness / burn 若再调同一入口，最坏编 3 遍。**推荐：本步不加 `--no-loudness-fix` → 人改字幕 → `/p3-burn`（约编 2 次）。** 急着先转写才加 `--no-loudness-fix`（稍后 loudness = 再全量重拼）。冷开场 prepend 后禁止再跑会覆盖成片的 assemble。

## 不要做的事

- 不要在这里渲 HUD 或从口播卡写字幕
- 不要在本步加 `--ass` 烧字
- 不要把字幕轨 mux 进 mp4
- 不要用 alpha 层当主轨，主轨是 `*-hud-preview.mp4`
- 不要降码
- 成片写好后不要只丢路径；接着抽帧核对画面
- 冷开场不要从 HUD preview / close-stats 截；不要默叠化（默认硬切）
- 冷开场 prepend 之后不要再跑全量 assemble 覆盖

## 前置

`hud-renders/*-run-*-hud-preview.mp4` 齐。`open` / `close` 可缺。**不要等字幕。** 已有 SRT 则拷到成片旁边（可选）。

有高驰截图 `YYYY-MM-DD-stats-*.jpg` 时，先叠到 close 左侧（半透明、多张均分轮播），再拼。原 close 不动：

```bash
.venv/bin/python tools/assemble/overlay_close_stats.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

拼的时候自动用 `*-close-stats.mp4`。

## 步骤

```bash
.venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --dry-run

# 推荐：拼时带响度（不要 --no-loudness-fix）；后台跑
nohup .venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  > ~/Movies/running-content/YYYY-MM-DD-slug/assemble.log 2>&1 &
# 等待期间去做封面 / 鞋账本；结束后看 assemble.log 末尾再核对画面

# 仅当急着先转写：再加 --no-loudness-fix
```

已有字幕时（重拼后）脚本不会拷 SRT，跑一次同步：

```bash
.venv/bin/python tools/subs/txt_to_subs.py \
  --txt episodes/YYYY-MM-DD-slug/subtitles.txt --media-dir auto
```

脚本会（画面侧）：

- 只吃 `hud-renders/*-run-*-hud-preview.mp4`
- `open → 第一段 run` 叠化 0.2 秒，HUD 从 run 起
- run 与 run：一阵风刮过（各约 0.08 秒横向拖影刮出/刮入），叠 `tools/assemble/sfx/whoosh.wav`
- `最后一段 run → close` 叠化 0.2 秒，close 无 HUD
- 统一 60 fps、`settb=1/60`
- 视频 HEVC videotoolbox；音频 AAC 192k（推荐本步走默认响度链）
- 有 `overlays.json` 时按成片时间轴叠动画/小视频

## 叠加层（动画 / 小视频）

每期一个 `overlays.json`，放媒体目录（优先）或 `episodes/YYYY-MM-DD-slug/`；`--overlays <路径>` 指定，`--no-overlays` 关。叠在成片画面上（转场之后、字幕之前），dry-run 会打出每层换算后的起止：

```json
{
  "overlays": [
    {"file": "lt-01.mov", "start": "5:20", "hold_until": "5:50"},
    {"file": "badge.png", "anchor": "close", "start": 2, "hold_until": 8, "x": "W-w-40", "y": 40, "width": 360}
  ]
}
```

- `start` / `hold_until`：`m:ss`、`h:mm:ss` 或秒数。默认 `anchor: final`；`anchor: close` 从 close 在成片里的起点算
- 动画放完后停在最后一帧到 `hold_until`；图片必须写 `hold_until`
- `file` 相对媒体目录。带透明用 ProRes 4444 `.mov` 或 PNG
- 可选：`x` / `y`、`width`、`fade_in` / `fade_out`、`opacity`
- 写进 `overlays.json` 一次拼完，不要拼完再二次压

## 接缝小样

```bash
.venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --preview-joins
```

写出 `qc/join-a-b.mp4`、`qc/join-b-c.mp4`（只听 whoosh/刮过）。要回硬切加 `--run-transition cut`。`--wind` / `--whoosh-volume` / `--no-whoosh` 调转场音效。

## 成片时间轴

`open` 时长 `Do`，各 run `R0..Rn`，叠化 `X=0.2`：

- open 从 0
- 第一段 run 从 `Do - X`
- 其后 run 时长累加（风转场不重叠，轴和硬切一样）
- close 从 `Do + sum(R) - 2X` 开始叠化

## 核对（拼完立刻做 · 只看画面）

至少抽这几帧到媒体目录 `qc/`（本步无烧字，不要从成片里找字幕帧）：

1. open 开头（应无 HUD）
2. open→run 接缝（HUD 刚出现）
3. 跑中 HUD 一帧（鞋名、气温 `°C`、配速）
4. run→close 接缝（HUD 应在叠化里消失）
5. close 结尾（无 HUD）

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

清单：

- open / close 没有 HUD
- 跑鞋名和 `-sk` 与 `training/logs/shoes.md` 一致
- 天气是「数字°C / 数字°C」，不是方框 `℃`
- 没有明显降码、花屏、音画不同步
- 若本步带了响度：听开场与接缝；日志/实测约 I=−16、TP≤−1.5

通过后：`assets.md` 的 `assemble: done`、`qc: done`；拼时带响度则一并 `loudness: done`。`episode.md` 仍是 `hud`。

失败：鞋错 → `p3-hud`；接缝错 → 查 open/close 是否被当成 run。

## 常见翻车（画面）

| 现象 | 原因 |
| --- | --- |
| xfade 报 timebase mismatch | 没做 `fps=60,settb=1/60`，concat 后没再 settb |
| 主轨没有 HUD | 拼了原片而不是 `*-hud-preview.mp4` |
| 平台字幕压 HUD | SRT 没有位置信息，属预期；公开前在网页播放器开 CC |

## 冷开场（可选）

用户指定「把某几句接到 open 前」时再做。**不是默认流程。** 来源可以是**任意一段原片素材**（`open` / `run-*` / `close` / `*-raw` 等），以用户当次点名的句为准。通常在字幕轴能定位目标句之后再截。

1. **只从原片截**：用户指定的 `YYYY-MM-DD-*.mp4`（或 `*-raw`）。不要 HUD preview，不要 `*-close-stats`。
2. **切入点**按字幕轴找目标句，从该句**第一个字**起切到句末（多句则按用户指定顺序）。
3. **转场默认硬切**。
4. **prepend** 到已有 `run-final` 前；记下 bumper 时长 offset；备份旧成片（如 `*-pre-coldopen.mp4`）。
5. 字幕：prepend 后 body 全部 +offset（或从新成片重抽 wav 再 `force_align`），文首补上冷开场几条；同步仓库与媒体 `subtitles.srt`。
6. `assets.md` 记：`cold-open: done`、来源片段与 offset。
7. **prepend 之后**：不要再跑全量 assemble 覆盖 `run-final`。

## 完成后

画面核对通过。不要再推荐 `/p3-qc`，除非核对失败。不要给发布文案。

> 下一步：`/p3-subs`。若本步用了 `--no-loudness-fix`，另开 `/p3-loudness`；拼时已带响度则跳过 loudness。
>
> `/p3-subs`
