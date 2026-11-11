---
name: p3-assemble
description: 把已经渲好的 HUD / 数据图片段接成整条审片预览（对得上就 stream copy），拼完抽帧核对；不生成最终成片。用户说预览、拼画面、assemble 时用。最终导出走 final_export.py，不能在这里烧字或修响度。
---

# 画面预览

整条审片预览只拼接已经渲好的片段，用来核对时长、字幕和画面元素在不在。**预览不是最终成片，也不能作为最终导出输入。** 不从原片和 HUD alpha 重压。这不是 60–90 秒发布剪辑。

产物：`~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4`

官方命令就是 `preview_episode.py`。`--dry-run` 会打印每一段是 `copy` 还是轻转。

## 前置

- 每个原始 `run-*` 都有对应的 `hud-renders/*-hud-preview.mp4`。缺了就停，先用 `/p3-hud` 把那段渲出来。不要改走整条重压。
- `open` 可缺。没有数据图时，`close` 可缺，有就直接接原 `close`。
- 素材目录里有 stats 图片且有 close 时，必须已经有 `*-close-stats.mp4`（数据图段）。没有就先跑 `tools/assemble/overlay_close_stats.py`。预览接数据图段，不接原 close，也不在整条滤镜里现叠 stats。
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

编码：以已渲好的 HUD preview 为模板，能拷贝就拷贝，只轻转对不上的短段，不要为对齐格式去重压长段。短段按 `tools/export-spec.json` 的 preview profile 转。不降分辨率。

脚本会缩短时间轴，对齐最终成片。预览比各段相加短一点是正常的，不要再剪，也不要挪字幕时间。`subtitles.txt` 还没写就不要传 `--subtitles`。

## 核对

至少抽帧检查：open 开头、open→run、跑中 HUD、run→close、close 结尾。缺的段跳过。接缝是硬切，叠化不算过。确认 HUD、stats 和音画没有明显缺元素后，在 `assets.md` 写 `preview: done`、`qc: done`。`qc: done` 只代表预览画面人工核对，不代表字幕已确认。下一步是 `/p3-subs`。

## 记日志

`preview_episode.py` 写 `review-preview`（`--dry-run` 不写）。脚本已写就不要再记。失败由脚本写 `FAIL`。

## 完成后

> 预览核对通过后走 `/p3-subs`。
