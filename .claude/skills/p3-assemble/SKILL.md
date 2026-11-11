---
name: p3-assemble
description: 把已经渲好的 HUD / 数据图片段接成整条审片预览（对得上就 stream copy），拼完抽帧核对；不生成最终成片。用户说预览、拼画面、assemble 时用。最终导出走 final_export.py，不能在这里烧字或修响度。
---

# 画面预览

整条审片预览只拼接已经渲好的片段，用来核对时长、字幕和画面元素在不在。**预览不是最终成片，也不能作为最终导出输入。** 不从原片和 HUD alpha 重压。这不是 60–90 秒发布剪辑。

产物：`~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4`

官方命令就是 `preview_episode.py`。`--dry-run` 会打印每一段是 `copy` 还是轻转。

## 前置

- 每个原始 `run-*` 都有对应的 `hud-renders/*-hud-preview.mp4`。缺了就停，先用 `/p3-hud` 把那段渲出来。不要改走整条重压。
- `open` 可缺。没有数据图时，`close` 可缺，有就直接接原 `close`。
- 素材目录里有 stats 图片且有 close 时，必须已经有 `*-close-stats.mp4`（数据图段）。没有就先跑 `tools/assemble/overlay_close_stats.py`。预览接数据图段，不接原 close，也不在整条滤镜里现叠 stats。
- 不要使用或覆盖 `*-run-final.mp4`，不要写 `upload/`。

## 步骤

```bash
.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --dry-run

.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --out ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4
```

编码：目标跟 HUD preview 走。手机 HUD preview 常见是 H.264 High、`yuvj420p`、`30000/1001`（29.97）。`yuvj420p` 和 `yuv420p` 都能当拷贝目标，但互不相等，以 preview 自己的像素格式为准。`30/1` 和 `30000/1001` 都算 30fps，不要为了收成整数 30 去重编码长 preview。整数 30 的 HEVC open/close 轻转到这个目标（含帧率和像素格式）后再 `-c copy`。只有编码、分辨率、像素格式、帧率或音频对不上的段才按 `tools/export-spec.json` 的 preview profile（libx264 veryfast crf 23、AAC 128k）轻转。多出来的音轨或数据轨只做 remux，不重编码。不降分辨率。`overlay_close_stats.py` 的数据图段是 60fps HEVC，对不上就只转它。

时长对齐最终成片的 xfade，不做叠化。`final_export.py` 在 open→第一段跑、最后一段跑→close 各叠 0.2s，时间轴因此各短 0.2s；段与段之间不缩短。预览在这两处已经要轻转的短段上剪掉同样的 0.2s（open 的尾、close 或数据图段的头），中间的 HUD preview 继续 stream copy，然后硬切。字幕按秒，不用改。和最终成片比，剩下的差只是 HUD preview 比原始 run 多出来的帧（通常每段约 1 帧）。不烧字幕、不做最终响度。字幕还没写就不要传 `--subtitles`。已经有 `subtitles.txt`、想让 IINA 自动挂时：

```bash
.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --subtitles episodes/YYYY-MM-DD-slug/subtitles.txt
```

这只在预览旁边写同名 `.srt`，cue 时间原样拷贝。

## 核对

至少抽帧检查：open 开头、open→run、跑中 HUD、run→close、close 结尾。接缝是硬切。确认 HUD、stats 和音画没有明显缺元素后，在 `assets.md` 写 `preview: done`、`qc: done`。`qc: done` 只代表预览画面人工核对，不代表字幕已确认。

字幕仍走 `/p3-subs`：写 `subtitles.txt` 后必须停，等人手改字；用户确认后才写 `subs: done`。最终导出必须用：

```bash
.venv/bin/python tools/assemble/final_export.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --episode-dir episodes/YYYY-MM-DD-slug \
  --out ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  --confirmed
```

最终导出直接读取原始片段与 HUD alpha，并在一次编码中叠 HUD、stats、字幕和响度。它不读 HUD preview、review preview 或 close-stats。修改字幕后只改 `subtitles.txt`，重新运行最终导出；不要先生成无字幕成片再单独 burn。

## 完成后

> 预览核对通过后走 `/p3-subs`。字幕用户确认后运行 `final_export.py --confirmed`，不要走旧的 `assemble --ass`、`burn_ass.py` 或 `loudness_only.py`。
