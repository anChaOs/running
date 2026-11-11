# 预览后单次导出

## 编码边界

- `p3-hud --preview` 生成单段 `*-hud-preview.mp4`。`preview_episode.py` 把这些已渲片段，加上 open，以及已叠数据图的 `*-close-stats.mp4`（没有数据图时用原 close）接成整条审片预览。目标跟 HUD preview 走：`yuvj420p` 和 `30000/1001` 直接 stream copy，不把长预览收成 `yuv420p` 或整数 30。只有对不上的段（常见是 HEVC open/close、60fps 数据图段）才按 preview profile 轻转到这个目标，然后再 `-c copy`。不从原片和 HUD alpha 重压。缺 HUD preview，或有 stats 图片却没有 close-stats 时，直接失败。
- 预览保持 30fps（`30/1` 或 `30000/1001`），不为求快降分辨率，不做叠化。open 尾和 close 头按最终成片的 0.2s xfade 剪掉同样的时长，中间段不剪。外挂字幕时间不平移。和最终成片比，剩下的差是 HUD preview 比原始 run 多出来的帧。不烧字幕、不修响度。
- 最终导出唯一入口是 `tools/assemble/final_export.py`。它直接读取 `open`、原始 `run-*`、`close`、HUD alpha、stats 图片和 `subtitles.txt`，在同一张 FFmpeg filter graph 内完成叠加、转场、拼接、字幕和响度，最后只编码一次 HEVC 成片。
- `loudnorm` 第一遍只输出到 `null` 做测量，不写媒体；第二遍才写最终文件。`assemble_episode.py`、`burn_ass.py`、`loudness_only.py` 不是新期正式成片路径。`close-stats.mp4` 只作为审片预览的数据图段；最终导出仍读取原 close 和 stats 图片，不读这条视频。

## 字幕门闩

预览用于人工看画面、转场、stats 和校对字幕。`subtitles.txt` 是唯一字幕源稿；用户确认后由 `p3-subs` 写 `subs: done`。最终导出还要求 `preview: done`、`qc: done` 和命令行 `--confirmed`，缺任一门闩都不生成成片。改字后重新执行最终导出，不先生成无字幕成片再烧第二遍。

## 规格配置

`tools/export-spec.json` 是唯一规格配置：公共时间轴默认 1920×1080、30 fps、yuv420p、48 kHz；预览和最终编码器只在各自 profile 中区别。最终 profile 固定 `hevc_videotoolbox`、`hvc1`、AAC 192k；测试编码器只能通过测试入口显式注入。

## 1080 → 4K

只改 `tools/export-spec.json` 的 `timeline.width`、`timeline.height`，并按设备能力调整 final bitrate；字幕 ASS 的 PlayRes 和字号来自同一配置。需要重新渲染 HUD alpha 并重新审片，不能把旧 1080 preview 当作 4K 最终输入。当前不实现 4K 验收，也不改录制建议（仍为 1080p30）。
