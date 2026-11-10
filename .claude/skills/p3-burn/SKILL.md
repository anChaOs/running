---
name: p3-burn
description: 已废弃的旧烧字入口。最终字幕、响度和画面必须由 final_export.py 在一次最终导出中完成；不要对已有成片再烧字。
---

# 已废弃

正式流程不再使用 `burn_ass.py`。字幕源是 `episodes/YYYY-MM-DD-slug/subtitles.txt`，人工确认后由 `tools/assemble/final_export.py --confirmed` 临时生成 ASS，并在唯一最终编码中完成字幕和响度。

不要：

- 在 `waiting-review` 时导出；
- 先生成无字幕 `run-final`，再用 `burn_ass.py` 重压；
- 把 `*-hud-preview.mp4`、`*-close-stats.mp4` 当最终输入；
- 修改 `.srt` / `.ass` 代替 `subtitles.txt`。

字幕写错后改 `subtitles.txt`，用户确认后重新执行 `final_export.py --confirmed`。旧脚本仅为历史素材维护保留，不属于本期成片管线。
