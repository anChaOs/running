---
name: p3-qc
description: 核对审片预览或最终成片。默认预览画面核对在 p3-assemble 完成；用户说再核对、抽帧、QC、审片、接缝不对时用。只写 qc: done；episode status 的 edited 由 p3-subs 在用户确认字幕后写。
---

# 成片核对

默认核对跟审片预览在 `p3-assemble` 里完成。本 skill 只在要再抽一轮、或当时没核对时用。

## 两个阶段

- **预览核对**：看播放清单 `YYYY-MM-DD-review-preview.edl`，听旁白、看有没有明显缺段。清单不带渲好的 HUD，也不烧字幕。通过后 `assets.md` 写 `preview: done`、`qc: done`。接缝、HUD、贴图和烧进去的字幕在最终片上抽帧。
- **最终核对**：`final_export.py --confirmed` 会在写出成片后做一道结构检查：能解码、一路视频一路音频、1920×1080、30fps、HEVC、`hvc1`、AAC、时长接近时间表、综合响度在 -16 LUFS 附近。结构不过就停，脚本只把 `final-export` 标成 done，**不会**标 `final-qc`。另外抽帧看字幕、HUD、贴图。失败应改 `subtitles.txt` 或时间表，再重新导出，不能对最终片单独 burn/loudness。抽帧通过之后才 `todo_list.py mark final-qc done`。这一步没打勾，`pack_upload.py` 会停。

## 看预览

预览是 `YYYY-MM-DD-review-preview.edl`，不是 mp4。用 IINA 或 mpv 看清单，不要对一条不存在的预览片抽帧。字幕要显式挂上，不要用 `--mpv-sub-file`：

```bash
iina --no-stdin --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.edl \
  -- --sub-files=~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.srt
```

没有 sidecar 就不要加 `-- --sub-files=`。用户同意后才打开 IINA，agent 不自行打开播放器。

## 抽帧

抽帧只对最终片。不要抽 `YYYY-MM-DD-review-preview.mp4`。

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

不要在成片旁边留同名 `.srt`（会和烧进去的字叠两层）；外挂只留 `subtitles.srt`。用户同意后才打开 IINA，agent 不自行打开播放器。打开烧字成片要带 `--no-stdin`，避免 IINA 占着 stdin 挂住：

```bash
iina --no-stdin --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

## 字幕门

字幕错误只改 `episodes/YYYY-MM-DD-slug/subtitles.txt`，重新 force_align / check_subs，并在用户确认后重新 `final_export.py --confirmed`。不要改生成的 SRT/ASS 当源稿。

## 完成后

还没有字幕：`/p3-subs`。字幕用户确认后：`final_export.py --confirmed`。已经导出并要上传：`/p3-publish`。
