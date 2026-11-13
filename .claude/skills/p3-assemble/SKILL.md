---
name: p3-assemble
description: 按 logs/program.json 写一份 mpv 播放清单来审片（不拼预览成片、不重编码、不渲 HUD）。用户说预览、拼画面、assemble 时用。最终导出走 final_export.py，不能在这里烧字或修响度。
---

# 画面预览

有 `logs/program.json` 时，预览只按这张表写一份播放清单，让播放器按入点和时长直接播原片。看起来像一条时间线，**不写出预览 mp4**。不渲 HUD，不重编码，不烧字幕，不修响度。不要用 ffmpeg 把切开的段 copy 或 concat 成文件，也不要 trim 滤镜从头解码，更不要为了预览走 libx264 / `hevc_videotoolbox`。

预览和导出共用表里的入出点。冷开场进跑步、跑步进 close 的 0.2 秒 xfade，预览只把同样的时长从非跑步那一侧扣掉，不做叠化。不同原片的跑步接缝在导出时有 0.08 秒风刮，那不缩短总时长，预览仍是硬切，不要把这 0.08 秒当成 xfade 剪掉。清单里各段时长加起来等于时间表（`frame_program_duration`），不能把关键帧前面的预卷算进去。

没有这张表时，才退回旧路径：拼接已经渲好的 `*-hud-preview.mp4`。不要为了走旧路径去补渲未剪预览。成片仍走 `final_export.py --confirmed`。预览清单不能当作最终导出的输入。

产物：`~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.edl`（mpv EDL v0，每行 `路径,起始秒,时长秒`）。原片在同一目录时路径相对清单，整夹搬走还能播。路径里有逗号、分号、换行或 `!` 时按 mpv 的 `%字节数%原文` 写。

```bash
.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --dry-run

.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

脚本打印怎么打开：

```text
mpv ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.edl
```

mpv 不要加 `--no-stdin`。那是 IINA 占着 stdin 才用的。IINA 1.5.1 能直接打开这份 `.edl`。需要当场播再加 `--play`；本机没有 mpv 时清单仍然写好，并说明启动失败。打不开播放器不算这步失败。

`subtitles.txt` 还没写就不要传 `--subtitles`。传了只在清单旁边写一份外挂 `.srt`，时间用虚拟时间线（和 txt 里的成片时间同一套），不烧进画面。没有字幕文件就不要造。不要在成片旁边留同名 `.srt`。

mpv 挂字幕用 `--sub-file=`。这是命令行别名，等于 `--sub-files-append`，mpv 自己认。IINA 走 libmpv，不认这个别名，`--mpv-sub-file` 会被静默丢掉。IINA 要把文件放在前面，选项放在 `--` 后面：

```bash
iina --no-stdin ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.edl \
  -- --sub-files=~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.srt
```

没有 sidecar 就不要加 `-- --sub-files=`。

## 前置

- `logs/program.json` 里原片对齐、句间刀、冷开场和贴图已经入表。缺了就停，不要改去整段重压。
- 贴图和数据图记在表的 `overlays` 里，预览可以先不叠。不要为了预览先做 `*-close-stats.mp4`。
- `logs/todo.md` 的 `layout` 还没 done 时，脚本拒绝写清单。`--dry-run` 不写文件、不记日志。
- 不要使用或覆盖 `*-run-final.mp4`，不要写 `upload/`。

## 核对

预览用来听旁白、对字幕错别字和换行，不必对着画面逐帧对时间。画面和时间对齐是导出成片的事。确认没有明显缺段之后，在 `assets.md` 写 `preview: done`、`qc: done`。`qc: done` 只代表这次审片核对，不代表字幕已确认。脚本成功时会把 `logs/todo.md` 的 `preview` 标成 done；没标上就不算这步完成。下一步是 `/p3-subs`。

## 记日志

`preview_episode.py` 写 `logs/timeline.txt` 的 `review-preview`（`--dry-run` 不写）。脚本已写就不要再记。失败由脚本写 `FAIL`。

## 完成后

> 预览核对通过后走 `/p3-subs`，对口型前先冻结时间表。冻上之后，用户校对字幕的同时可以 `--prep-alpha` 和 `final_export.py --measure-only`。8 核机器画透明层加 `-j 6`（默认仍是 2），留 1–2 核给系统和写 mov 的 ffmpeg。同一条原片加载一次 FIT，再按窗口写出各自的 alpha。成片仍只走 `final_export.py --confirmed`，仍然只写出一个文件。确认导出按大约 120 秒分段编码：段界不切断风刮或 xfade，每一段只打开自己用到的原片，窗口 alpha 在这一段里收成一条再叠一次，套用已测响度，烧字幕，`hevc_videotoolbox`。`-filter_complex_threads` 是 3。段与段顺序编码，最后 concat 流拷贝接成片。不把 `hud-renders/keeps/` 当画面。
