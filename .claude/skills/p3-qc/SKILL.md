---
name: p3-qc
description: 核对审片预览或最终成片。默认预览画面核对在 p3-assemble 完成；用户说再核对、抽帧、QC、审片、接缝不对时用。只写 qc: done；episode status 的 edited 由 p3-subs 在用户确认字幕后写。
---

# 成片核对

默认核对跟审片预览在 `p3-assemble` 里完成。本 skill 只在要再抽一轮、或当时没核对时用。

## 两个阶段

- **预览核对**：检查 open/run/close 接缝、HUD、stats、音画和无明显花屏。预览没有硬字幕；通过后 `assets.md` 写 `preview: done`、`qc: done`。
- **最终核对**：`final_export.py --confirmed` 写出最终片后，抽帧检查字幕、HUD、stats 和最终音量。失败应改 `subtitles.txt` 或配置，再重新执行最终导出，不能对最终片单独 burn/loudness 二次编码。

## 抽帧

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

最终片需要检查字幕时，对 `YYYY-MM-DD-run-final.mp4` 抽帧；用户同意后才打开 IINA，agent 不自行打开播放器。

## 字幕门

字幕错误只改 `episodes/YYYY-MM-DD-slug/subtitles.txt`，重新 force_align / check_subs，并在用户确认后重新 `final_export.py --confirmed`。不要改生成的 SRT/ASS 当源稿。

## 完成后

还没有字幕：`/p3-subs`。字幕用户确认后：`final_export.py --confirmed`。已经导出并要上传：`/p3-publish`。
