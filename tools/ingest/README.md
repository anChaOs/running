# ingest

把手机未重命名导出收进 `~/Movies/running-content/YYYY-MM-DD-slug/`。

```bash
.venv/bin/python tools/ingest/ingest_run_media.py \
  --src <导出目录> \
  --date YYYY-MM-DD \
  --slug topic \
  --episode-dir episodes/YYYY-MM-DD-slug
```

默认 dry-run。确认角色后加 `--apply`。`VID_` 文件若 mtime 和「开始 + 时长」差超过 5 分钟，会把 mtime 改成结束时间，供 HUD `file-modified` 对齐。

`--apply` 后会粗剪 open/close 里明显长于均值的句间停顿。默认 Silero VAD。原片留 `*-open-raw.mp4` / `*-close-raw.mp4`。不要剪原片 run-*。跑中口播在 HUD preview 出完后剪：

```bash
.venv/bin/python tools/ingest/trim_talk_pauses.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug

.venv/bin/python tools/ingest/trim_talk_pauses.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --targets preview
```

流程见 skill `p3-ingest`。
