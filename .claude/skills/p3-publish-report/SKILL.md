---
name: p3-publish-report
description: 发布报告。published 之后立刻做，只出一张可打开的单屏 HTML，并统一同步复盘与报告到 Google Drive running-retrospect/。不要等用户要报告。不写双链、不合 PR、不清临时。
---

# 发布报告

`p3-publish` 写完 `published`、试过合 episode PR 之后立刻做，不要等用户要报告。只交这一张 HTML，不另写 Markdown，不在聊天里再铺表。未 `published` 就停，先走 `/p3-publish`。遵守 `p3-episode` 全局协议。

## 不要做的事

- 不要编秒（无据写「约」或「缺日志」）；不要把旁路核对片算进官方成片
- 不要加开场段、使用说明、时区说明；不要让整页滚动
- 不要把文件大小写到字节，只写到 G（如 `1.1G`、`2.5G`）
- 不要在这里标 `cleanup` 或删文件

## 证据

时间一律 Asia/Shanghai。优先 `logs/timeline.txt` 和 `logs/failures.md`（媒体目录或 Google Drive `running-retrospect/` 归档）；缺失再用文件 birth/mtime、ffmpeg 日志、git commit。日志与成片 mtime 不一致时用文件/编码时间，标「日志后写」。墙钟 = 起止时刻之差（非表内耗时相加）：制作段到最终导出，发布段从打包到 `published`/PR。

## 输出与同步

正式文件只写文本 HTML 到素材目录：

- `~/Movies/running-content/<YYYY-MM-DD-slug>/publish-report.html`

写完后统一跑一次同步脚本，把 `logs/`、`episode-repo/` 与 `publish-report.html` 一并同步到 Google Drive `running-retrospect/<YYYY-MM-DD-slug>/` 并刷新 `INDEX.md`：

```bash
.venv/bin/python tools/publish/sync_retrospect_drive.py \
  --media-dir ~/Movies/running-content/<YYYY-MM-DD-slug>
```

聊天里只给素材目录路径。核对 `logs/todo.md`（`published: done`；`cleanup` 若仍 `pending` 就在「还欠」里写清临时确认）。清临时清单仍由 `/p3-publish` 列。

## 页面布局

一屏看完，白底黑字，无卡片/阴影/图标。正文 ~15px 行高略松、标题 ~22px 略粗、节标题 ~16px 配细黑下划线；对照表耗时列加粗等宽数字，失败行结果加粗。整页固定视口不滚动，阶段行多时只让阶段表内部滚动。

按以下顺序写，不另加栏目：

1. 标题一行；下一行 `published` + episode PR 链接（已合写 hash 和时间，未合写未合）；再一行 YouTube、Bilibili、抖音（空写「空」）。
2. 「预览和成片」：先一句结论（耗时谁长谁短、片长是否一致、非同一次编码），再出对照表（列：文件、时间、耗时、编码、里面有什么、大小）。新流程审片为 `*-review-preview.edl`（写清单与虚拟时长，不找预览 mp4）；旁路核对片另起一行；单段 HUD preview 不入表。
3. 「阶段」：列只能是开始、步骤、耗时、结果，覆盖 scaffold、ingest、鞋、封面、HUD（重做/中断各一行）、assemble/预览、字幕、最终导出、打包、B 站、YouTube、published/PR；失败尝试保留并写「失败」。
4. **墙钟**：制作段对发布段。
5. **坑**：没有写无。
6. **还欠**：抖音短链、清临时确认、未合的工具 PR、字幕等；没有写无。
