---
name: p3-assemble
description: 把 open + HUD preview + close 拼成全长成片，拼完立刻抽帧核对。两端 0.2s 叠化、run 默认一阵风刮过+风声。字幕默认外挂，不要烧进成片。用户说拼接、转场、assemble、成片导出时用。不要在这里渲染 HUD 或写字幕稿。只再核对一次走 p3-qc。
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

## 前置

`hud-renders/*-run-*-hud-preview.mp4` 齐。`open` / `close` 可缺。字幕可缺（先拼母版再听写也可以；没有 SRT 时核对跳过对口型）。

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

有已定稿的字幕时，把外挂拷到成片旁边方便上传和本地播放器自动挂：

```bash
cp episodes/YYYY-MM-DD-slug/subtitles.srt \
   ~/Movies/running-content/YYYY-MM-DD-slug/
cp episodes/YYYY-MM-DD-slug/subtitles.srt \
   ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.srt
```

脚本会：

- 只吃 `hud-renders/*-run-*-hud-preview.mp4`
- `open → 第一段 run` 叠化 0.2 秒，HUD 从 run 起
- run 与 run：一阵风刮过（各约 0.08 秒横向拖影刮出/刮入），叠 `tools/assemble/sfx/whoosh.wav`。吃的是两段头尾，成片时长不变，字幕轴不用重算
- `最后一段 run → close` 叠化 0.2 秒，close 无 HUD
- 统一 60 fps、`settb=1/60`（open/close 和 preview 时间基不同，不统一 xfade 会失败）
- 视频 HEVC videotoolbox，码率对齐 preview；音频 AAC 192k

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

至少抽这几帧，写到媒体目录 `qc/`（成片上没有字幕，不要从成片里找字幕帧）：

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

有 SRT 时用 **IINA** 对口型（不要推荐 ffplay）。成片旁边已有同名 `YYYY-MM-DD-run-final.srt`，IINA 会自动挂外挂。抽查 open 第一句、第一段 run 开头、各 run 接缝、close 第一句：

```bash
iina --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

小窗、贴右上角（IINA 在 macOS 上 `-0-0` 是右上，不是右下）。同名 `YYYY-MM-DD-run-final.srt` 会自动挂。

清单：

- open / close 没有 HUD
- 成片画面里没有烧进去的字幕
- 外挂跟嘴、单行、不要太长；没有 `\N` 两行；用词跟口播，没有被改写成另一种说法
- 没有两条字幕叠在一起
- 跑鞋名和 `-sk` 与 `training/logs/shoes.md` 一致
- 天气是 `13°C / 12°C` 这种，不是方框 `℃`
- 没有明显降码、花屏、音画不同步

通过后：`episode.md` 的 `status` 改为 `edited`，`assets.md` 制作状态 `assemble: done`、`qc: done`。

失败则指出该重跑哪个 skill：鞋错 → `p3-hud`；字幕错 → 改 txt/SRT，**不用重拼**；接缝错 → 查 open/close 是否被当成 run。不要把失败写成 `edited`。

## 上传外挂

| 平台 | 文件 | 哪里挂 |
| --- | --- | --- |
| B 站 | `subtitles.srt` | 稿件管理 / 字幕；创作中心只收 SRT |
| YouTube | `subtitles.srt` | Studio → 字幕 → 添加「中文（简体）」→ 上传文件 |

SRT 没有位置信息，默认贴底栏，可能压 HUD。公开前在 B 站、YouTube 网页播放器开 CC 看一眼。

## 常见翻车

| 现象 | 原因 |
| --- | --- |
| 成片里已经有字 | 误传了 `--ass`，或烧到已有成片上 |
| xfade 报 timebase mismatch | 没做 `fps=60,settb=1/60`，concat 后没再 settb |
| 主轨没有 HUD | 拼了原片而不是 `*-hud-preview.mp4` |
| 平台字幕压 HUD | SRT 没有位置信息，属预期；公开前在网页播放器开 CC |

## 完成后

核对通过后立刻告诉用户：全长成片流程结束，没有下一个制作 skill。不要再推荐 `/p3-qc`，除非核对失败、要再抽一轮。

**先不要给发布流程和文案。** 用户还没看过成片。这一条只给 IINA 怎么打开（不要推荐 ffplay），请他们审片。路径换成当前期，不要留 `YYYY-MM-DD-slug`：

```bash
iina --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

小窗贴右上角。成片旁边已有同名 `YYYY-MM-DD-run-final.srt` 才会自动挂。没出字按 `v`，或菜单「字幕 → 显示字幕」。

看完没问题再说，例如「没问题了 / 可以发了」，再给发布流程和文案。还要改成片就按他们说的改，不要把文案先甩过去。

用户确认可以发之后，从该期 `plan.md` 抄标题、封面句、简介、标签。简介应已在 `p3-subs` 对口型完成后按字幕写好；还缺就读校准后的 `subtitles.txt` 补进 `plan.md`，不要按 `talk.md` 补，也不要在字幕没校准前写。不要现场编一套和字幕不一致的。

简介只总结字幕里实际说了什么，短句。不要推理，不要方法论，不要复读「严肃业余跑者，当天训练当天讲」。不要写「这期不是 xxx / 不是让人抄 / 不念公报」，除非标题或题材会让人误认（比如鞋期才点当天脚感）。已发布的旧期简介不要回改。

同一条回复里写清：

| 用途 | 文件 |
| --- | --- |
| 成片 | `~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4` |
| 封面 16:9 | `cover-1920x1080.jpg` |
| 封面 3:4 | `cover-1080x1440.jpg` |
| 外挂字幕 | `subtitles.srt`（B 站创作中心只收 SRT；YouTube 加「中文（简体）」） |

步骤：上传成片 → 换封面 → 挂 SRT → **先不公开**，网页播放器开 CC 看会不会压 HUD → 再转公开。不要替用户上传。

还要 60–90 秒短视频才提 `/p3-jianying`。

发布后把链接写进该期 `episode.md` / `plan.md`，`status` 改为 `published`。用户说「发到 B 站了 BV…」时再记。
