---
name: p3-qc
description: 核对审片播放清单或对最终成片抽帧验收（final-qc）。默认预览核对在 p3-assemble 完成；用户说再核对、抽帧、QC、审片、接缝不对时用。只写 qc / final-qc；episode status 的 edited 由 p3-subs 写。
---

# 成片核对

默认预览核对已在 `p3-assemble` 完成；本 skill 用于最终片抽帧验收（`final-qc`）或补充核对。遵守 `p3-episode` 全局协议（进度门闩与不自动开播放器）；本步不单记 `timeline.txt`。

## 两个阶段

- **预览核对**：看播放清单 `preview/YYYY-MM-DD-review-preview.edl`（旧期在根目录，不带 HUD 和烧字），听旁白、查缺段；通过后 `assets.md` 写 `preview: done`、`qc: done`，核对 `logs/todo.md` 中 `preview: done`。
- **最终核对（`final-qc`）**：`final_export.py --confirmed` 跑完后自动做结构检查（可解码、1080p30 HEVC `hvc1` + AAC、时长对齐、响度 ~-16 LUFS）并标 `final-export: done`，但**不会标 `final-qc`**。核对 `logs/todo.md` 确认 `final-export: done` 后，对最终片抽帧检查字幕、HUD、贴图与接缝。
  - 抽帧发现问题：改 `subtitles.txt` 或 `logs/program.json` 重跑 `final_export.py --confirmed`，禁止对成片单独烧字或补跑响度。
  - 抽帧通过后执行：
    ```bash
    .venv/bin/python tools/todo_list.py \
      --media-dir ~/Movies/running-content/YYYY-MM-DD-slug mark final-qc done
    ```
    标完核对 `logs/todo.md`（`final-qc: done`），**立刻停下等用户审片并说「可以发了」**（清单等待点；不要在这里提前打包）。

## 抽帧命令（只对最终片，不抽不存在的预览 mp4）

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

成片旁不要留同名 `.srt`（会和烧字叠两层）。需开 IINA 审片时先问用户，同意后按 `p3-episode` 协议命令打开（可加 `--mpv-geometry=320x180-8+8`）。

## 完成后

- 还没字幕：`/p3-subs`（先跑完 `draft_subs.py` 交出初稿 `subs: waiting-review`，再立刻并行 `--prep-alpha -j 6` 与 `--measure-only`）。
- 最终片抽帧通过、`final-qc: done`：等用户说「可以发了」，再走 `/p3-publish`。
