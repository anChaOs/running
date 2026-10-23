---
name: p3-assemble
description: 把 open + HUD preview + close 拼成全长成片，拼完立刻抽帧核对。两端 0.2s 叠化、run 默认一阵风刮过+风声。混音后默认 dynaudnorm+loudnorm 到约 −16 LUFS（峰值 ≤ −1.5 dBTP）；拼完仍测 LUFS/峰值。字幕默认外挂，不要烧进成片。用户说拼接、转场、assemble、成片导出时用。不要在这里渲染 HUD 或写字幕稿。只再核对一次走 p3-qc。
---

# 拼接 + 核对

把已有 HUD preview 拼成一条全长成片，**拼完立刻抽帧核对**。不要停下来等人发 `/p3-qc`。这不是 60–90 秒发布剪辑。

```text
~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

HUD 走 `p3-hud`，封面走 `p3-cover`（二者并行），字幕走 `p3-subs`。只换封面走 `p3-cover`。只再核对一次走 `p3-qc`。

## 不要做的事

- 不要在这里渲 HUD 或从口播卡写字幕
- **默认不要传 `--ass`。** 字幕外挂：B 站和 YouTube 都传 `subtitles.srt`。改字幕只改 sidecar，不用重拼
- 不要把字幕轨 mux 进 mp4（平台转码会丢掉）
- 不要用 alpha 层当主轨，主轨是 `*-hud-preview.mp4`
- 不要降码
- 用户没明确说「烧进去」时，不要烧字幕
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
- **混音后默认响度链**（concat + whoosh → leveling → loudnorm）；`--no-loudness-fix` 可关

## 音频（默认响度链 + 拼完必测）

**为什么在 assemble，不在 hud / subs：** HUD 只叠画面；字幕是外挂轴。人声+环境+whoosh 的最终听感只在成片混音这一次定型，所以 leveling / loudnorm 放在 `assemble_episode.py` 的 post-mix（whoosh 叠完、AAC 编码前）。

对比黑影儿TV 等参考片：整轨 flat gain（旧记忆「至少 ×1.5 / ≈+3.5 dB」）不够——峰值先顶满，轻句仍小，麦克风偶发掉音也补不回。默认改为 **dynaudnorm 拉平起伏 → compressor → loudnorm 对齐整体响度**。

脚本默认开启（`--no-loudness-fix` 关掉）。滤镜字符串（**起点参数**，POV 实拍未逐条精调）：

```text
highpass=f=90,afftdn=nf=-25,dynaudnorm=f=250:g=15:p=0.9:m=8,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7,aformat=sample_rates=48000:channel_layouts=stereo
```

顺序：

1. concat / acrossfade 拼主音轨
2. 叠 whoosh（音效单独 volume，不先猛推整轨）
3. 上述响度链 → 目标约 **I=-16 LUFS**，**TP=-1.5 dBTP**（loudnorm 卡住真峰值）
4. AAC 192k 写出

拼完仍要测（单 pass loudnorm 与实片听感可能有偏差；严重麦掉音如 −13 dB 处可能需手工局部增益）：

```bash
# 响度（看 I / TP / LRA）
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af loudnorm=I=-16:TP=-1.5:LRA=7:print_format=summary -f null -

# 峰值兜底
ffmpeg -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -af volumedetect -f null -
```

目标：**LUFS ≈ −16**（与常见跑步口播参考接近）、**峰值 ≤ −1.5 dB**（勿顶到 0 dB 削波）。超标再查是否误关了响度链、或个别句要局部补增益——不要整轨再盲目 ×1.5。

录的时候尽量加风棉/死猫；开场自拍口播清楚，切到 POV 后别炸。拼完用 IINA 听开场、第一段 run、风声最大处与已知掉音处。

只有用户明确要求硬字幕时才加 `--ass episodes/.../subtitles.ass`。

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

至少抽这几帧，写到媒体目录 `qc/`（成片画面没有字幕，不要从成片里找字幕帧）：

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
- 成片画面里没有烧进去的字幕
- 跑鞋名和 `-sk` 与 `training/logs/shoes.md` 一致
- 天气是「数字°C / 数字°C」，不是方框 `℃`
- 没有明显降码、花屏、音画不同步
- 已测 LUFS ≈ −16、峰值 ≤ −1.5 dB（loudnorm summary / volumedetect）；无明显削波；POV 风噪不盖过人声；未误加 `--no-loudness-fix`

通过后：`assets.md` 的 `assemble: done`、`qc: done`。`episode.md` 仍是 `hud`。字幕核对在 `p3-subs`。

失败则指出该重跑哪个 skill：鞋错 → `p3-hud`；接缝错 → 查 open/close 是否被当成 run。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 成片里已经有字 | 误传了 `--ass`，或烧到已有成片上 |
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
