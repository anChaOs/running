# 预览后单次导出

## 编码边界

- `p3-hud --preview`、`preview_episode.py` 只生成审片预览；预览可以轻量编码，不是最终输入。
- 最终导出唯一入口是 `tools/assemble/final_export.py`。它直接读取 `open`、原始 `run-*`、`close`、HUD alpha、stats 图片和 `subtitles.txt`，在同一张 FFmpeg filter graph 内完成叠加、拼接、字幕和响度，最后只编码一次 HEVC 成片。
- `loudnorm` 第一遍只输出到 `null` 做测量，不写媒体；第二遍才写最终文件。`assemble_episode.py`、`burn_ass.py`、`loudness_only.py` 和 `close-stats.mp4` 不再是正式成片路径。

## 字幕门闩

预览用于人工看画面、接缝和校对字幕。`subtitles.txt` 是唯一字幕源稿；用户确认后由 `p3-subs` 写 `subs: done`。最终导出还要求 `qc: done` 和命令行 `--confirmed`，缺任一门闩都不生成成片。改字后重新执行最终导出，不先生成无字幕成片再烧第二遍。

## 规格配置

`tools/export-spec.json` 是唯一规格配置：公共时间轴默认 1920×1080、30 fps、yuv420p、48 kHz；预览和最终编码器只在各自 profile 中区别。最终 profile 固定 `hevc_videotoolbox`、`hvc1`、AAC 192k；测试编码器只能通过测试入口显式注入。

## 1080 → 4K

只改 `tools/export-spec.json` 的 `timeline.width`、`timeline.height`，并按设备能力调整 final bitrate；字幕 ASS 的 PlayRes 和字号来自同一配置。需要重新渲染 HUD alpha 并重新审片，不能把旧 1080 preview 当作 4K 最终输入。当前不实现 4K 验收，也不改录制建议（仍为 1080p30）。
