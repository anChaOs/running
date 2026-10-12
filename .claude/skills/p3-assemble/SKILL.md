---
name: p3-assemble
description: 把 open + HUD preview + close 拼成全长成片，拼完立刻抽帧核对。两端 0.2s 叠化、run 默认一阵风刮过+风声。成片音频峰值限制 ≤ −1 dB（先降风噪再推人声）。字幕默认外挂，不要烧进成片。用户说拼接、转场、assemble、成片导出时用。不要在这里渲染 HUD 或写字幕稿。只再核对一次走 p3-qc。
---

# 拼接 + 核对

把已有 HUD preview 拼成一条全长成片，**拼完立刻抽帧核对**。不要停下来等人发 `/p3-qc`。这不是 60–90 秒发布剪辑。

```text
~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

HUD 和封面走 `p3-hud`（并行），字幕走 `p3-subs`。只换封面走 `p3-cover`。只再核对一次走 `p3-qc`。

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

.venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

已有 SRT 时拷到成片旁边：

```bash
cp episodes/YYYY-MM-DD-slug/subtitles.srt \
   ~/Movies/running-content/YYYY-MM-DD-slug/
cp episodes/YYYY-MM-DD-slug/subtitles.srt \
   ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.srt
```

脚本会：

- 只吃 `hud-renders/*-run-*-hud-preview.mp4`
- `open → 第一段 run` 叠化 0.2 秒，HUD 从 run 起
- run 与 run：一阵风刮过（各约 0.08 秒横向拖影刮出/刮入），叠 `tools/assemble/sfx/whoosh.wav`。吃的是两段头尾，成片时长不变
- `最后一段 run → close` 叠化 0.2 秒，close 无 HUD
- 统一 60 fps、`settb=1/60`（open/close 和 preview 时间基不同，不统一 xfade 会失败）
- 视频 HEVC videotoolbox，码率对齐 preview；音频 AAC 192k

## 音频（成片必做）

这不是改 HUD 代码，是成片导出时的听感底线：

- **峰值限制 ≤ −1 dB**（ceiling −1 或 −1.5 dB）。实测口播顶到 0 dB 会削波，刺耳。
- 先降 POV 跑段风噪，再推人声；不要整轨盲目加大。
- 录的时候尽量加风棉/死猫；开场自拍口播清楚，切到 POV 后音量别突然炸。
- 拼完用 IINA 听一遍开场、第一段 run、风声最大处；削波或风盖过人声就不算过。

只有用户明确要求硬字幕时才加 `--ass episodes/.../subtitles.ass`。

先看接缝小样（不拼全片）：

```bash
.venv/bin/python tools/assemble/assemble_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --preview-joins
```

写出 `qc/join-a-b.mp4`、`qc/join-b-c.mp4`。要回硬切加 `--run-transition cut`。`--wind 0.08` 调刮过时长，`--whoosh-volume 0.85` 调风声，`--no-whoosh` 不要音效。

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
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

清单：

- open / close 没有 HUD
- 成片画面里没有烧进去的字幕
- 跑鞋名和 `-sk` 与 `training/logs/shoes.md` 一致
- 天气是「数字°C / 数字°C」，不是方框 `℃`
- 没有明显降码、花屏、音画不同步
- 音频峰值 ≤ −1 dB，无明显削波；POV 风噪不盖过人声

通过后：`assets.md` 的 `assemble: done`、`qc: done`。`episode.md` 仍是 `hud`。字幕核对在 `p3-subs`。

失败则指出该重跑哪个 skill：鞋错 → `p3-hud`；接缝错 → 查 open/close 是否被当成 run。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 成片里已经有字 | 误传了 `--ass`，或烧到已有成片上 |
| xfade 报 timebase mismatch | 没做 `fps=60,settb=1/60`，concat 后没再 settb |
| 主轨没有 HUD | 拼了原片而不是 `*-hud-preview.mp4` |
| 平台字幕压 HUD | SRT 没有位置信息，属预期；公开前在网页播放器开 CC |
| 口播刺耳 / 风盖过人声 | 峰值顶到 0 dB 削波，或没先降风噪就推音量；限制器 ceiling −1 dB 后重听 |


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

1. 把媒体目录里的生产成片 `YYYY-MM-DD-run-final.mp4` **原地改名**为 `plan.md` / `episode.md` 标题原文 + `.mp4`；同名 sidecar `.srt` 一并改名。
2. **文件名保留标题全部标点**，包括 `|`、`？`、空格等。**不要**把 `|` 换成 `-`，也不要另复制一份副本。
3. 备份文件（如 `*-run-final-pre-coldopen.mp4`、`*-run-final-pre-trimfix.mp4`）**保留原名**，不要跟着改。
4. `assets.md`：`assemble` 注明新文件名；加 `upload: ready`。`episode.md` 的 `status` 仍为 `edited`，发完两边链接齐了才 `published`。

详细发布清单与清临时文件见 `p3-subs`。

## 完成后

画面声音核对通过。不要再推荐 `/p3-qc`，除非核对失败。不要给发布文案。

> 下一步用 `/p3-subs`，可以直接发：
>
> `/p3-subs`
