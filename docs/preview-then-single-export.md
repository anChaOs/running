# 预览后单次导出

## 编码边界

有 `logs/program.json` 时，审片预览是 `preview_episode.py` 写出的 mpv EDL（`*-review-preview.edl`），按时间表直接播原片，不写预览成片。下面是没有这张表时的旧路径。

- `p3-hud --preview` 生成单段 `*-hud-preview.mp4`。没有时间表时，`preview_episode.py` 把这些已渲片段，加上 open，以及已叠数据图的 `*-close-stats.mp4`（没有数据图时用原 close）接成整条审片预览。目标跟 HUD preview 走：`yuvj420p` 和 `30000/1001` 直接 stream copy，不把长预览收成 `yuv420p` 或整数 30。只有对不上的段（常见是 HEVC open/close、60fps 数据图段）才按 preview profile 轻转到这个目标，然后再 `-c copy`。不从原片和 HUD alpha 重压。缺 HUD preview，或有 stats 图片却没有 close-stats 时，直接失败。
- 预览保持 30fps（`30/1` 或 `30000/1001`），不为求快降分辨率，不做叠化。open 尾和 close 头按最终成片的 0.2s xfade 剪掉同样的时长，中间段不剪。外挂字幕时间不平移。和最终成片比，剩下的差是 HUD preview 比原始 run 多出来的帧。不烧字幕、不修响度。
- 最终导出唯一入口仍是 `tools/assemble/final_export.py --confirmed`，仍然只写出一个成片文件。它读取 `open`、原始 `run-*`、`close`、已经按窗口画好的 HUD alpha、stats 图片和 `subtitles.txt`。画面来源是原片，不是 `hud-renders/keeps/`。确认导出按大约 120 秒切段，段界不落在风刮或 xfade 里面。每一段只打开自己用到的原片和透明层：同一条原片在这一段里只打开一次，`-ss` 到这段最早的入点，多段句间刀用 `select` 丢掉空隙，不再 `split`。同一段里一条原片上的窗口 alpha 仍收成一条再叠一次，多窗用 concat 解复用读那些短 mov。然后这一段烧字幕（ASS 时间改成本段从 0 起算）、套用已经测好的同一组 loudnorm 参数，用 `hevc_videotoolbox` 编码。`-filter_complex_threads` 是 3；这一段若十几秒内起不来，退回 1。不要加 `-threads 1`。段与段顺序编码，不并行。编完用 concat 解复用流拷贝接成最终 mp4，不再进滤镜。临时段文件成功和失败都删。130 段 / 7 条原片 / 118 个 alpha、大约 1152.6 秒这种表，是 10 段，每段 2 到 5 个 `-i`，不是每个窗口一个输入。
- 时间表冻结后，字幕校对可以和准备并行。`render_running_hud.py --prep-alpha` 按留下的入出点直接画透明层。8 核机器加 `-j 6`（默认仍是 2），留 1–2 核给系统和写 mov 的 ffmpeg。同一条原片加载一次 FIT 和模板，每个窗口仍写成自己的 alpha mov；占了大部分窗口的原片最多拆成 `-j` 个进程。`final_export.py --measure-only` 把 loudnorm 第一遍测在成片混音上，只输出到 `null`，不写媒体，也不读字幕。确认导出套用这次测量；对不上当前表就先补测再编码。补画透明层同样认 `--jobs`。刀点只挪了大约 1 秒、片段顺序没变时，可以不重测。`assemble_episode.py`、`burn_ass.py`、`loudness_only.py` 不是新期正式成片路径。`close-stats.mp4` 只作为审片预览的数据图段；最终导出仍读取原 close 和 stats 图片，不读这条视频。

## 字幕门闩

预览用于人工看画面、转场、stats 和校对字幕。`subtitles.txt` 是唯一字幕源稿；用户确认后由 `p3-subs` 写 `subs: done`。最终导出还要求 `preview: done`、`qc: done` 和命令行 `--confirmed`，缺任一门闩都不生成成片。改字后重新执行最终导出，不先生成无字幕成片再烧第二遍。HUD 和响度可以在确认前准备好，但确认导出仍然是烧进字幕的那一次命令。

## 规格配置

`tools/export-spec.json` 是唯一规格配置：公共时间轴默认 1920×1080、30 fps、yuv420p、48 kHz；预览和最终编码器只在各自 profile 中区别。最终 profile 固定 `hevc_videotoolbox`、`hvc1`、AAC 192k；测试编码器只能通过测试入口显式注入。

## 1080 → 4K

只改 `tools/export-spec.json` 的 `timeline.width`、`timeline.height`，并按设备能力调整 final bitrate；字幕 ASS 的 PlayRes 和字号来自同一配置。需要重新渲染 HUD alpha 并重新审片，不能把旧 1080 preview 当作 4K 最终输入。当前不实现 4K 验收，也不改录制建议（仍为 1080p30）。
