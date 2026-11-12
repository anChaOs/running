---
name: p3-assemble
description: 按 logs/program.json 立刻拼一条低成本审片预览（能拷贝就拷贝，不渲 HUD），拼完抽帧核对；不生成最终成片。用户说预览、拼画面、assemble 时用。最终导出走 final_export.py，不能在这里烧字或修响度。
---

# 画面预览

有 `logs/program.json` 时，预览只按这张表拼，用来决定刀点并开始转写。**不渲 HUD，不按原片码率粗剪，不烧字幕，不修响度。** 整段能接上就 stream copy；只有被切开的短段才按预览规格轻压（h264 用 crf 23，hevc 用 8M，不是源片大约 49Mbps）。跑步段的原片区间和最终导出是同一份。预览不是最终成片，也不能当作最终导出的输入。

没有这张表时，才退回旧路径：拼接已经渲好的 `*-hud-preview.mp4`。不要为了走旧路径去补渲未剪预览。

产物：`~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.mp4`

官方命令就是 `preview_episode.py`。`--dry-run` 会打印每一段是 `copy` 还是轻压。

## 前置

- `logs/program.json` 里原片对齐、句间刀、冷开场和贴图已经入表。缺了就停，不要改去整段重压。
- 贴图和数据图记在表的 `overlays` 里，预览可以先不叠。不要为了预览先做 `*-close-stats.mp4`。
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

冷开场进跑步、跑步进 close 的 0.2 秒 xfade，预览只把同样的时长从非跑步那一侧剪掉，不做叠化。成片时长和导出一致。预览比各段相加短一点是正常的。`subtitles.txt` 还没写就不要传 `--subtitles`；传了也只在旁边写同时间轴的外挂，不烧进画面。

和 HEVC 原片 stream copy 混接时，切开的段用 `hevc_videotoolbox` 8M。参数对不齐时 concat copy 会失败并停。不要改回按源片大约 49Mbps 重压，也不要改走 `assemble_episode.py`。

## 核对

至少抽帧检查：open 开头、open→run、跑中、run→close、close 结尾。缺的段跳过。这条预览默认没有最终质量数据条；接缝是硬切，叠化不算过。确认音画没有明显缺段之后，在 `assets.md` 写 `preview: done`、`qc: done`。`qc: done` 只代表预览画面人工核对，不代表字幕已确认。脚本成功时会把 `logs/todo.md` 的 `preview` 标成 done；没标上就不算这步完成。下一步是 `/p3-subs`。

## 记日志

`preview_episode.py` 写 `review-preview`（`--dry-run` 不写）。脚本已写就不要再记。失败由脚本写 `FAIL`。

## 完成后

> 预览核对通过后走 `/p3-subs`。
