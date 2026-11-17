# tools

- `ingest/`：手机 `VID_` / FIT 收进素材目录并命名。
- `hud/`：用 FIT 给跑中素材叠配速、心率、距离、地图、天气。成片先 `--record-only` 记进时间表；冻结后 `--prep-alpha` 按留下的区间直接画透明层，不写 `hud-renders/keeps/`。8 核机器加 `-j 6`（默认 2）。同一条原片加载一次 FIT，再按窗口写出各自的 alpha。
- `subs/`：字幕初稿（`draft_subs.py`）、改字后强制对齐（`force_align.py`）、质检门（`check_subs.py`）、txt 收成外挂 SRT/ASS 生成物。
- `assemble/preview_episode.py`：有 `logs/program.json` 时按时间表写 mpv EDL 审片清单，不拼预览成片。没有这张表时才拼接已渲 HUD 片段。不生成最终成片，不从原片和 alpha 重压。
- `assemble/final_export.py`：字幕人工确认后的唯一最终导出入口。`--measure-only` 可在校对时先测成片混音。`--confirmed` 从原片、HUD alpha 和 stats 图片一次完成裁切、叠加、拼接、烧字幕、套用已测响度与 HEVC 输出；缺准备会先补上。
- `assemble/assemble_episode.py`、`burn_ass.py`、`loudness_only.py`：历史旁路，仅供旧期维护，不属于新流程。
- `cover/`：三比例封面排版（4:3 / 3:4 / 16:9）。
- `publish/`：上传打包（`pack_upload.py` → 媒体目录 `upload/`）；把成片切成亚 100MB 块并拷进 Google Drive 桌面版目录。

规格统一配置：`tools/export-spec.json`。默认最终规格为 1080p30 HEVC；切换 4K 时先改配置并重新渲 HUD/预览，当前不做完整 4K 验收。
