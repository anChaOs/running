---
name: p3-qc
description: 核对审片预览或最终成片。默认预览画面核对在 p3-assemble 完成；用户说再核对、抽帧、QC、审片、接缝不对时用。只写 qc: done；episode status 的 edited 由 p3-subs 在用户确认字幕后写。
---

# 成片核对

默认核对跟审片预览在 `p3-assemble` 里完成。本 skill 只在要再抽一轮、或当时没核对时用。

## 两个阶段

- **预览核对**：看播放清单 `YYYY-MM-DD-review-preview.edl`，听旁白、看有没有明显缺段。清单不带渲好的 HUD，也不烧字幕。通过后 `assets.md` 写 `preview: done`、`qc: done`。进度以 `logs/todo.md` 为准，`preview` 应为 done。打开播放器不是清单上的等待点。接缝、HUD、贴图和烧进去的字幕在最终片上抽帧。看完立刻读清单。清单不对就停。不要攒到后面再标，也不要拿文件名或 `assets.md` 当进度。
- **最终核对**：`final_export.py --confirmed` 是唯一确认导出，仍然只写出一个文件。画面按大约 120 秒分段，每一段只出画面：裁自己用到的原片、把这段的窗口 alpha 收成一条再叠一次、做落在这段里的转场、烧字幕，用 HEVC 编码。整片音频用和测响度同一张图混一次、编一次 AAC。响度没测好就和第一段画面一起测，测完再开音频编码，不挡画面；音频一直留在内存监控里直到结束。第一段同时对帧头和逐帧数，一致之后后面的段只读帧头。监控把每段的内存和墙钟打在日志里（macOS 有 `footprint` 就记 phys_footprint，读不到或接近 0 就退回 RSS），合计超过 8GB 就停。最后把画面段流拷贝接起来，配上这一条音频。缺透明层或响度测量时会先补上再编码，不会先出无字幕成片再烧字、再改响度。写出成片后做一道结构检查：能解码、一路视频一路音频、1920×1080、30fps、HEVC、`hvc1`、AAC、时长接近时间表、综合响度在 -16 LUFS 附近。结构不过就停，脚本只把 `final-export` 标成 done，**不会**标 `final-qc`。导出命令返回后立刻读 `logs/todo.md`，`final-export` 应为 done，`final-qc` 仍是 pending。另外抽帧看字幕、HUD、贴图。失败应改 `subtitles.txt` 或时间表，再重新导出，不能对最终片单独 burn/loudness。抽帧通过之后才 `todo_list.py mark final-qc done`。标完立刻再读清单，`final-qc` 应为带时间的 done。这一步没打勾，`pack_upload.py` 会停。然后停下来，等用户审片并说「可以发了」再打包或发布。这是清单上的等待点。清单不对就停。不要攒到后面再标，也不要拿文件名或 `assets.md` 当进度。

## 看预览

预览是 `YYYY-MM-DD-review-preview.edl`，不是 mp4。他同意之后才用 IINA 或 mpv 看清单，不要对一条不存在的预览片抽帧。字幕要显式挂上，不要用 `--mpv-sub-file`：

```bash
iina --no-stdin --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.edl \
  -- --sub-files=~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.srt
```

没有 sidecar 就不要加 `-- --sub-files=`。用户同意后才打开 IINA，agent 不自行打开播放器。同意是他说「打开」，或明确同意这次询问。字幕初稿校对不再是例外。打开播放器不是清单上的等待点。看完立刻读 `logs/todo.md`，`preview` 应为 done。清单不对就停。不要拿文件名或 `assets.md` 当进度。

## 抽帧

抽帧只对最终片。不要抽 `YYYY-MM-DD-review-preview.mp4`。

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug/qc
ffmpeg -y -ss <秒> -i ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  -frames:v 1 ~/Movies/running-content/YYYY-MM-DD-slug/qc/<label>.jpg
```

不要在成片旁边留同名 `.srt`（会和烧进去的字叠两层）；外挂只留 `subtitles.srt`。用户同意后才打开 IINA，agent 不自行打开播放器。各阶段都一样，字幕校对也不例外：没有这句同意就不要开。打开成片不是清单上的等待点；等待点是抽帧通过、`final-qc` 已 done 之后等「可以发了」。抽帧命令跑完立刻读 `logs/todo.md`。还没标 `final-qc` 就不要往下走。不要拿文件名或 `assets.md` 当进度。打开烧字成片要带 `--no-stdin`，避免 IINA 占着 stdin 挂住：

```bash
iina --no-stdin --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

## 字幕门

字幕错误只改 `episodes/YYYY-MM-DD-slug/subtitles.txt`，重新 force_align / check_subs，并在用户确认后重新 `final_export.py --confirmed`。不要改生成的 SRT/ASS 当源稿。重新导出跑完立刻读 `logs/todo.md`。`final-export` 会回到 done，`final-qc` 要抽帧通过后再标。清单不对就停。

## 完成后

还没有字幕：`/p3-subs`。时间表已冻结、人还在改错字时，可以同时 `--prep-alpha`（8 核加 `-j 6`）和 `final_export.py --measure-only`。字幕用户确认后：一次 `final_export.py --confirmed`。`final-qc` 已 done 之后先等用户说「可以发了」，再 `/p3-publish`。不要在这一步直接打包。
