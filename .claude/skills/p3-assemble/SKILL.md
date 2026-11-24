---
name: p3-assemble
description: 按 logs/program.json 写一份 mpv 审片播放清单 review-preview.edl（不拼预览 mp4、不重编码、不渲 HUD）。用户说预览、拼画面、assemble 时用。最终导出走 final_export.py --confirmed。
---

# 画面预览

本步遵守 `p3-episode` 全局协议（进度门闩、墙钟日志与不自动开播放器）。有 `logs/program.json` 时，预览**只写 mpv EDL 播放清单**，不拼预览 mp4、不渲 HUD、不烧字幕、不修响度。没有该表时才退回旧路径（拼已有 `*-hud-preview.mp4`），不要为走旧路径去补渲预览。

## 前置

- `logs/program.json` 已完成 `source_sync`、句间刀、冷开场和贴图入表，且 `logs/todo.md` 的 `layout: done`（否则脚本拒绝）
- 不要为了预览先做 `*-close-stats.mp4`，也不要触碰 `*-run-final.mp4` 或 `upload/`

## 生成审片播放清单

产物：`~/Movies/running-content/YYYY-MM-DD-slug/preview/YYYY-MM-DD-review-preview.edl`（分类目录下写进 `preview/` 并引用 `../raw/...`，整夹搬走仍可播；旧平铺目录兼容写根）。

```bash
.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --dry-run

.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

- 正式执行后自动写 `review-preview` 墙钟并标 `logs/todo.md` 的 `preview: done`；跑完立刻核对清单。
- `subtitles.txt` 还没写不要传 `--subtitles`；不要在成片旁边留同名 `.srt`。
- 打开方式遵循 `p3-episode` 协议（先问再开；IINA 用 `--no-stdin` 与 `-- --sub-files=`，不用 `--mpv-sub-file`；本机无 mpv 不算失败）。

## 核对与下一步

预览用于听旁白和检查是否缺段（接缝、HUD、贴图和烧字在最终片上抽帧）。确认无明显缺段后在 `assets.md` 写 `preview: done`、`qc: done`（仅代表审片核对，不代表字幕确认）。

> 下一步走 `/p3-subs` 转写与校对（对口型前冻结时间表，期间立刻并行跑 `--prep-alpha -j 6` 与 `--measure-only`）。
