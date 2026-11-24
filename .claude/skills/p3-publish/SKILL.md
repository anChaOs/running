---
name: p3-publish
description: 发布收尾：用户说「可以发了」时打包 upload/；给齐 B 站 + YouTube 链接后写 episode 发布栏、status=published、squash 合 episode PR、触发发布报告并同步复盘日志到 Google Drive、再列清临时清单等确认后移进废纸篓。抖音短链不挡 published。满 7 天归档见 p3-archive。
---

# 发布收尾

本步遵守 `p3-episode` 的全局协议（进度门闩与墙钟日志）。流程：**用户说「可以发了」打包 → 自动/手动上传拿双链 → 写双链 & `published` → squash 合 episode PR → `/p3-publish-report`（写 HTML 并同步复盘到 Google Drive）→ 清临时确认**。

## 不要做的事

- 缺 B 站或 YouTube 任一链接时不要写 `published` 或合 PR（抖音短链不挡 `published`，随后补写）
- 只自动合 **episode 内容 PR**；skill / 工具类 PR 必须等用户合
- 用户确认前不要删任何临时文件；清临时禁止 `rm` / `rm -rf`，只进废纸篓
- 不要整夹删媒体目录（满 7 天搬盘走 `/p3-archive`）；复盘目录严禁放视频、FIT、封面、原片

## 前置与打包（用户说「可以发了」时）

进来先核对 `logs/todo.md`：`final-export` 与 `final-qc` 必须均为 `done`，且用户已说「可以发了」。然后打包 `upload/`（不重编码；ASCII `/` 自动转全角 `／`，平台标题仍用 `plan.md` 原文）：

```bash
.venv/bin/python tools/publish/pack_upload.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --episode-dir episodes/YYYY-MM-DD-slug
```

跑完核对 `logs/todo.md`（`pack-upload: done`，并在 `logs/pack-sha256.txt` 写好成片 SHA-256）。核对 `upload/` 含：标题烧字 `.mp4`、三封面（4:3 / 3:4 / 16:9）、`subtitles.srt`。

- 简介按 `plan.md`「### B 站」「### YouTube」各抄各的；自动上传走 `/p3-bilibili` 与 `/p3-youtube`。
- **抖音（第三平台，不挡 `published`）**：成片用 `upload/` 那份，正文抄 `plan.md`「抖音」栏，话题页内点选（≤5）；短链拿到后补写 `episode.md`「抖音：」。
- 还要短视频才提 `/p3-jianying`。

## 双链齐 → `published` → 合 PR → 复盘同步

触发：用户给齐 **B 站 BV/链接** 和 **YouTube 链接**（且 `logs/todo.md` 中 `bilibili`、`youtube` 均为 `done`）。顺序：

1. 写入 `episode.md`「发布」栏并改 `status: published`；用 `tools/log_timeline.py` 记 `start published` / `end published`，并 `todo_list.py mark published done`。核对 `logs/todo.md`（`published: done`，`cleanup: pending`）。
2. **立刻 squash 合并该期 episode PR 进 `main`**：`gh pr merge --squash --delete-branch`（不改清单；合前 `published` 必须是 `done`）。
3. **立刻出发布报告并同步复盘到 Google Drive**（不要等清临时确认）：
   - 走 `/p3-publish-report` 生成 `publish-report.html`，写完后统一跑一次同步脚本把 `logs/`、`episode-repo/` 和 `publish-report.html` 一并同步到 Google Drive `running-retrospect/<YYYY-MM-DD-slug>/` 并刷新 `INDEX.md`（历史归档期自动保留）：
     ```bash
     .venv/bin/python tools/publish/sync_retrospect_drive.py \
       --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
     ```
   - 若暂不出报告或 PR 暂合不了，也要立刻先跑一次上述同步命令，不要干等。清临时不动 `logs/` 和 `publish-report.html`。
4. **列清临时清单并等确认**：读取 [cleanup-checklist.md](references/cleanup-checklist.md)，按 KEEP / DELETE 规则用 `du -sh` 列出拟删与拟留项及体积，等用户确认后移入 `~/.Trash/`，报出腾出体积再 `todo_list.py mark cleanup done`。

## 完成后

> 双链已写、`published`、episode PR 已 squash 进 `main`。复盘与发布报告已同步到 Google Drive `running-retrospect/<YYYY-MM-DD-slug>/`（如实说明同步结果）。清临时清单如下，确认后进废纸篓：
>
> （列出 KEEP / DELETE + 体积）
