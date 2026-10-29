---
name: p3-assemble
description: 把 open + HUD preview + close 拼成全长成片，拼完立刻抽帧核对。两端 0.2s 叠化、run 默认一阵风刮过+风声。混音后默认 dynaudnorm+loudnorm 到约 −16 LUFS（峰值 ≤ −1.5 dBTP）；拼完仍测 LUFS/峰值。从 2026-10-29 起最终片默认传 `--ass` 烧字幕；可对字幕中间版可不烧。用户说拼接、转场、assemble、成片导出时用。不要在这里渲染 HUD 或写字幕稿。只再核对一次走 p3-qc。
---

# 拼接 + 核对

把已有 HUD preview 拼成一条全长成片，**拼完立刻抽帧核对**。不要停下来等人发 `/p3-qc`。这不是 60–90 秒发布剪辑。

```text
~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

HUD 走 `p3-hud`，封面走 `p3-cover`（二者并行），字幕走 `p3-subs`。只换封面走 `p3-cover`。只再核对一次走 `p3-qc`。

## 不要做的事

- 不要在这里渲 HUD 或从口播卡写字幕
- **最终片（从 2026-10-29 起）传 `--ass episodes/.../subtitles.ass` 烧硬字幕。** 可对字幕中间版（`--no-loudness-fix` / waiting-review）可不烧；平台仍可另挂 `subtitles.srt`
- 不要把字幕轨 mux 进 mp4（平台转码会丢掉）；烧字用滤镜，不是 mux
- 不要用 alpha 层当主轨，主轨是 `*-hud-preview.mp4`
- 不要降码
- 改字幕字/时间后要重烧才更新画面；校对期改 sidecar 不用重拼
- 成片写好后不要只丢路径；接着抽帧核对
- 冷开场不要从 HUD preview / close-stats 截；不要默叠化（默认硬切）

## 前置

`hud-renders/*-run-*-hud-preview.mp4` 齐。`open` / `close` 可缺。不要等字幕。已有 SRT 则拷到成片旁边。

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

# 正式拼一律后台跑，日志进媒体目录；不要前台阻塞等 ffmpeg
nohup .venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  > ~/Movies/running-content/YYYY-MM-DD-slug/assemble.log 2>&1 &
# 等待期间去做封面 / 鞋账本；结束后看 assemble.log 末尾再核对
```

## 流程顺序（从 2026-10-29 起）

**先出可对字幕成片，响度链后置。** 用户校对字幕期间再跑音频优化，提高并行效率：

1. `assemble_episode.py --no-loudness-fix` → 写出 `YYYY-MM-DD-run-final.mp4`（画面+转场+whoosh 齐，响度未修、可不烧字）供 `p3-subs` 立刻开工
2. `p3-subs` 做到 `waiting-review`（等人手改字；外挂 SRT）
3. 校对期间另开一遍：对同一媒体目录再跑 `assemble_episode.py`（**不加** `--no-loudness-fix`，即默认响度链），覆盖/写出响度版；或保留预响度副本为 `YYYY-MM-DD-run-final-pre-loudnorm.mp4` 再覆盖 `run-final`
4. 字校对 + force_align 定稿后：生成 `subtitles.ass`，备份无烧字片为 `YYYY-MM-DD-run-final-no-burn.mp4`，再跑 `assemble_episode.py --ass episodes/.../subtitles.ass`（保留响度链）→ **最终发布片**
5. QC 峰值/LUFS 与烧字抽帧跟**最终片**（响度 + 烧字）

不要等响度链跑完才开字幕。`--no-loudness-fix` 就是「可对字幕版」开关。最终片从 2026-10-29 起默认带 `--ass`。

已有字幕时（重拼后）脚本不会拷 SRT，跑一次同步：

```bash
.venv/bin/python tools/subs/txt_to_subs.py \
  --txt episodes/YYYY-MM-DD-slug/subtitles.txt --media-dir auto
```

脚本会：

- 只吃 `hud-renders/*-run-*-hud-preview.mp4`
- `open → 第一段 run` 叠化 0.2 秒，HUD 从 run 起
- run 与 run：一阵风刮过（各约 0.08 秒横向拖影刮出/刮入），叠 `tools/assemble/sfx/whoosh.wav`。吃的是两段头尾，成片时长不变
- `最后一段 run → close` 叠化 0.2 秒，close 无 HUD
- 统一 60 fps、`settb=1/60`（open/close 和 preview 时间基不同，不统一 xfade 会失败）
- 视频 HEVC videotoolbox，码率对齐 preview；音频 AAC 192k
- **混音后默认响度链**（concat + whoosh → leveling → loudnorm），**默认两遍**；`--no-loudness-fix` 可关
- 有 `overlays.json` 时按成片时间轴叠动画/小视频，可停住到指定时间（见下「叠加层」）
- 写完自动实测成片 I / TP / LRA 打到日志末尾

## 音频（默认响度链 + 拼完必测）

响度只在成片混音定型：`assemble_episode.py` 的 post-mix（whoosh 叠完、AAC 编码前）。不要整轨 flat gain（旧习惯 ×1.5 / ≈+3.5 dB）——峰值先顶满，轻句仍小。默认 **dynaudnorm → compressor → loudnorm**。

脚本默认开启（`--no-loudness-fix` 关掉）。滤镜字符串（**起点参数**，POV 实拍未逐条精调）：

```text
highpass=f=90,afftdn=nf=-25,equalizer=f=3500:t=q:w=1.2:g=2.5,dynaudnorm=f=250:g=15:p=0.9:m=8,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7,aformat=sample_rates=48000:channel_layouts=stereo
```

顺序：

1. concat / acrossfade 拼主音轨
2. 叠 whoosh（音效单独 volume，不先猛推整轨）
3. 上述响度链 → 目标约 **I=-16 LUFS**，**TP=-1.5 dBTP**（loudnorm 卡住真峰值）
4. AAC 192k 写出

**两遍 loudnorm（默认）：** 第一遍只解码音频，跑同一条链（loudnorm 之前的滤镜完全一样，loudnorm 加 `print_format=json`）测出 `measured_I/TP/LRA/thresh/offset`；第二遍把最后的 loudnorm 换成带测量值 + `linear=true` 的版本再编码。线性增益不会像单遍那样边走边推，句间起伏更自然，I 更贴近 −16。日志里有 `Loudnorm pass 1`（链内 loudnorm 之前的 I / 峰值 TP）和 `Loudnorm pass 2` 的完整滤镜；loudnorm 判断线性做不到（LRA/峰值卡住）会自己退回动态，日志 summary 的 `Normalization Type` 能看到。测量失败（报错、全静音 `-inf`）自动退回单遍 `LOUDNESS_AF`，日志有 `⚠ Loudnorm 测量失败`。想强制单遍加 `--single-pass-loudnorm`。

拼完日志末尾有 `成片实测: I=… TP=…`（AAC 编码后真峰值可能比 −1.5 高零点几，−1.0 以内算过）。还要人工复核时（严重麦掉音如 −13 dB 处可能需手工局部增益）：

```bash
# 响度（看 I / TP / LRA）
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af loudnorm=I=-16:TP=-1.5:LRA=7:print_format=summary -f null -

# 峰值兜底
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af volumedetect -f null -
```

目标：**LUFS ≈ −16**、**峰值 ≤ −1.5 dB**（勿顶到 0 dB 削波）。超标再查是否误关了响度链、或个别句要局部补增益——不要整轨再盲目 ×1.5。

拼完用 IINA 听开场、第一段 run、风声最大处、已知掉音处。开场口播要清楚，切到 POV 后别炸。

## 叠加层（动画 / 小视频，按时间停住）

每期一个 `overlays.json`，放媒体目录（优先）或 `episodes/YYYY-MM-DD-slug/`；`--overlays <路径>` 指定，`--no-overlays` 关。叠在成片画面上（转场之后、字幕之前），dry-run 会打出每层换算后的起止：

```json
{
  "overlays": [
    {"file": "lt-01.mov", "start": "5:20", "hold_until": "5:50"},
    {"file": "lt-02.mov", "start": "6:00", "hold_until": "6:30"},
    {"file": "lt-03.mov", "start": "6:44", "hold_until": "7:11", "fade_out": 0.3},
    {"file": "badge.png", "anchor": "close", "start": 2, "hold_until": 8, "x": "W-w-40", "y": 40, "width": 360}
  ]
}
```

- 上面 start 是示意，按实际填。`start` / `hold_until`：`m:ss`、`h:mm:ss` 或秒数。默认 `anchor: final`（成片时间轴，和抽帧/字幕同一根轴）；`anchor: close` 从 close 在成片里的起点算
- 动画放完后**停在最后一帧**到 `hold_until` 再撤（`tpad` clone）；`hold_until` 早于动画结束就提前截掉；不写 `hold_until` 就放完一遍。图片必须写 `hold_until`
- `file` 相对媒体目录。带透明的动画用 ProRes 4444 `.mov` 或 PNG；全画幅透明动画 `x/y` 不写（默认 0,0）
- 可选：`x` / `y`（ffmpeg overlay 表达式，如 `W-w-40`）、`width`（等比缩放）、`fade_in` / `fade_out`（秒）、`opacity`（0–1）
- 超出成片的 `hold_until` 会截到片尾并警告；`start` 超出直接报错
- 写进 `overlays.json` 让 assemble 一次拼完，不要拼完再二次压。核对时在每层起点、停住中段、撤掉后各抽一帧

最终片（从 2026-10-29 起）加 `--ass episodes/.../subtitles.ass`；可对字幕中间版省略。

先看接缝小样（不拼全片）：

```bash
.venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --preview-joins
```

写出 `qc/join-a-b.mp4`、`qc/join-b-c.mp4`（接缝小样**不**跑响度链，只听 whoosh/刮过）。要回硬切加 `--run-transition cut`。`--wind 0.08` 调刮过时长，`--whoosh-volume 0.85` 调风声，`--no-whoosh` 不要音效。全片不要响度链时加 `--no-loudness-fix`。

## 成片时间轴

`open` 时长 `Do`，各 run `R0..Rn`，叠化 `X=0.2`：

- open 从 0
- 第一段 run 从 `Do - X`
- 其后 run 时长累加（风转场不重叠，轴和硬切一样）
- close 从 `Do + sum(R) - 2X` 开始叠化

## 核对（拼完立刻做）

至少抽这几帧，写到媒体目录 `qc/`（最终片应有烧字；可对字幕中间版可以无，那时不要从成片里找字幕帧）：

1. open 开头（应无 HUD）
2. open→run 接缝（HUD 刚出现）
3. 跑中 HUD 一帧（鞋名、气温 `°C`、配速）
4. run→close 接缝（HUD 应在叠化里消失）
5. close 结尾（无 HUD）

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
# 制作期用 run-final；若已 upload-ready 改名，把输入换成标题名 .mp4
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

清单：

- open / close 没有 HUD
- 最终片画面里**应有**烧进去的字幕（底中、不挡左栏 HUD）；可对字幕中间版可以无烧字
- 跑鞋名和 `-sk` 与 `training/logs/shoes.md` 一致
- 天气是「数字°C / 数字°C」，不是方框 `℃`
- 没有明显降码、花屏、音画不同步
- 最终片（响度链后）已测 LUFS ≈ −16、峰值 ≤ −1.5 dB；可对字幕版允许先加 `--no-loudness-fix`，响度在字幕 waiting-review 期间补上后再测

通过后：`assets.md` 的 `assemble: done`、`qc: done`。`episode.md` 仍是 `hud`。字幕核对在 `p3-subs`。

失败则指出该重跑哪个 skill：鞋错 → `p3-hud`；接缝错 → 查 open/close 是否被当成 run。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 最终片没有字 / 中间版不该有字 | 最终片漏传 `--ass`；或中间版误烧；ASS Style/MarginV 压 HUD 则调样式重烧 |
| xfade 报 timebase mismatch | 没做 `fps=60,settb=1/60`，concat 后没再 settb |
| 主轨没有 HUD | 拼了原片而不是 `*-hud-preview.mp4` |
| 平台字幕压 HUD | SRT 没有位置信息，属预期；公开前在网页播放器开 CC |
| 口播刺耳 / 风盖过人声 | 峰值顶到 0 dB 削波，或 flat gain 猛推；确认默认响度链开着，再测 I/TP；仍炸再查局部掉音/风噪 |
| 整体偏 quieter 参考片 | 误加了 `--no-loudness-fix`，或单句麦掉音需局部增益（整轨再 ×1.5 不够且易削波） |


## 冷开场（可选，字幕定稿后）

用户指定「从 run-c / close 各抽一句接到 open 前」时再做。不是默认流程。

1. **只从原片截**：`YYYY-MM-DD-run-*.mp4` / `open` / `close`（或 `*-raw`）。不要 HUD preview，不要 `*-close-stats`。
2. **切入点**按字幕轴找目标句，从该句**第一个字**起切到句末；不要带上上一句最后一个字。
3. **转场默认硬切**（jump cut）。白闪 / 声音冲击 / 画面抖动可另做几秒预览给人选，定稿用哪版听用户的。
4. **prepend** 到已有 `YYYY-MM-DD-run-final.mp4` 前；记下 bumper 时长 offset。备份旧成片（如 `*-pre-coldopen.mp4`）。
5. **字幕**：body 全部 +offset，文首补上冷开场几条；或从新成片重抽 wav 再 `force_align`。同步 episode 与媒体 sidecar。
6. `assets.md` 记：`cold-open: done`、两句来源与秒数、offset。

详细切口与对口型约束见 `p3-subs`「切条易错」第 6 条。

## 发布前改名（upload-ready）

用户说可以发了、要准备上传时（通常在 `p3-subs` 定稿之后）：

**路径约定：** 制作期工具与抽帧一律用 `YYYY-MM-DD-run-final.mp4`；改名后成片=标题名 `.mp4`，外挂仍=`subtitles.srt`。改名后再 QC / 对口型时，视频走标题名，字幕显式 `--sub-file=subtitles.srt`，不要找与成片同名的 `.srt`。

1. **只改成片名**：把媒体目录里的生产成片 `YYYY-MM-DD-run-final.mp4` **原地改名**为 `plan.md` / `episode.md` 标题原文 + `.mp4`。
2. **不要改字幕文件名。** 上传外挂始终用 `subtitles.srt`（仓库 `episodes/.../subtitles.srt` 与媒体目录同名拷贝）。**不要**把 SRT 改成标题名。制作阶段若曾拷过 `YYYY-MM-DD-run-final.srt`（给 IINA 同名挂载用），可保留，但发布上传优先 `subtitles.srt`。
3. **文件名保留标题全部标点**，包括 `|`、`？`、空格等。**不要**把 `|` 换成 `-`，也不要另复制一份成片副本。
4. 备份文件（如 `*-run-final-pre-coldopen.mp4`、`*-run-final-pre-trimfix.mp4`）改名阶段**保留原名**，不要跟着改。发布后按 `p3-subs`「发布后清临时文件」进废纸篓，不要长期留在媒体目录。
5. `assets.md`：`assemble` 注明新成片文件名；加 `upload: ready`（成片=标题名 `.mp4`，外挂=`subtitles.srt`）。`episode.md` 的 `status` 仍为 `edited`，发完两边链接齐了才 `published`。

详细发布清单与清临时文件（保留/删除真源）见 `p3-subs`。

## 完成后

画面声音核对通过。不要再推荐 `/p3-qc`，除非核对失败。不要给发布文案。

> 下一步用 `/p3-subs`，可以直接发：
>
> `/p3-subs`
