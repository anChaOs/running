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

`--apply` 后会锁原片↔FIT（写入 `logs/program.json` 的 `source_sync`），并自动对 `open`/`close`/`run` 做句间停顿检测（默认 Silero VAD），**只把保留区间写入 `logs/program.json`（`--record`），不重编码原片**。不需要句间刀时加 `--skip-pause-trim`。

已收过素材需单独补跑句间刀（默认 dry-run，确认后加 `--record`）：

```bash
.venv/bin/python tools/ingest/trim_talk_pauses.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --record \
  --targets open,close,run
```

流程见 skill `p3-ingest`。
