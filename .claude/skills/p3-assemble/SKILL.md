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

编码：各段的视频编码、分辨率、像素格式、音频参数一致，并且已经是 30fps 时，整段 stream copy，再 `-c copy` 接起来。只有对不上的段才按 `tools/export-spec.json` 的 preview profile（libx264 veryfast crf 23、AAC 128k）轻转，转完仍是 `-c copy` 拼接。多出来的音轨或数据轨只做 remux，不重编码。保持 30fps，不降分辨率。手机 open 常是 HEVC，`overlay_close_stats.py` 的数据图段是 60fps HEVC，这两段会对不上 HUD preview，只转它们；已经是 30fps H.264 的 HUD preview 不再编码。

预览不做叠化。时长等于 open + 各段 HUD preview + close 或数据图段之和，字幕时间不用改。不烧字幕、不做最终响度。字幕还没写就不要传 `--subtitles`。已经有 `subtitles.txt`、想让 IINA 自动挂时：

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
