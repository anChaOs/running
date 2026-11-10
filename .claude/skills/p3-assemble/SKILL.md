---
name: p3-assemble
description: 从原片 + HUD alpha + stats 图片一次生成整条审片预览，拼完抽帧核对；不生成最终成片。用户说预览、拼画面、assemble 时用。最终导出走 final_export.py，不能在这里烧字或修响度。
---

# 画面预览

从原片、HUD alpha 和 stats 图片生成一条审片预览，**预览不是最终成片，也不能作为最终导出输入**。整条预览只编码一次；拼完立刻抽帧核对画面。这不是 60–90 秒发布剪辑。

产物：`~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4`

## 前置

- 原始 `run-*`、对应 `hud-renders/*-hud-alpha.mov` 已齐；单段 `*-hud-preview.mp4` 只用于单段检查，不作为整条预览输入。
- `open` / `close` 可缺；有 close 时 stats 图片会直接在预览滤镜图里叠加。`close-stats.mp4` 不是新期必经步骤，最终导出和预览都读取原 `close` + stats 图片。旧期若仅有 close-stats，按旧流程兼容处理。
- 不要使用或覆盖 `*-run-final.mp4`，不要写 `upload/`。

## 步骤

```bash
.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --dry-run

.venv/bin/python tools/assemble/preview_episode.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --out ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4
```

预览只做一次轻量编码以统一播放规格，不能按最终成片替代最终输入。预览阶段不烧字幕、不做最终响度；字幕校对时外挂字幕或直接对照音频检查。

## 核对

至少抽帧检查：open 开头、open→run、跑中 HUD、run→close、close 结尾。确认接缝、HUD、stats 和音画没有明显错误后，在 `assets.md` 写 `preview: done`、`qc: done`。`qc: done` 只代表预览画面人工核对，不代表字幕已确认。

字幕仍走 `/p3-subs`：写 `subtitles.txt` 后必须停，等人手改字；用户确认后才写 `subs: done`。最终导出必须用：

```bash
.venv/bin/python tools/assemble/final_export.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --episode-dir episodes/YYYY-MM-DD-slug \
  --out ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  --confirmed
```

最终导出会直接读取原始片段与 HUD alpha，并在一次编码中叠 HUD、stats、字幕和响度。修改字幕后只改 `subtitles.txt`，重新运行最终导出；不要先生成无字幕成片再单独 burn。

## 完成后

> 预览核对通过后走 `/p3-subs`。字幕用户确认后运行 `final_export.py --confirmed`，不要走旧的 `assemble --ass`、`burn_ass.py` 或 `loudness_only.py`。
