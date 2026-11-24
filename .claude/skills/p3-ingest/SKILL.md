---
name: p3-ingest
description: 把手机未重命名导出（VID_*.mp4、DCIM）收进 ~/Movies/running-content/YYYY-MM-DD-slug/，按时间改成 open/run-*/close，用高驰 MCP 拉 FIT，锁原片↔FIT 并将句间刀写入 logs/program.json。用户说收素材、重命名、ingest、手机导出时用。
---

# 收素材并命名

本步遵守 `p3-episode` 全局协议（进度门闩与墙钟日志）。小米导出常见 `VID_YYYYMMDD_HHMMSS.mp4`。FIT 优先用高驰 MCP 拉，落到 `YYYY-MM-DD-run-data.fit`。大文件只放仓库外。

## 前置

日期、slug、原始文件夹路径。角色分配和 mtime 校正结果必须给用户看过再 `--apply`。

## FIT：高驰 MCP

目录里没有当天 FIT 时，**用高驰 MCP 拉**，不要让用户从手表/App 拷。国内节点 `https://mcpcn.coros.com/mcp`（见 `knowledge/production/COROS-MCP.md`）。

1. `querySportRecords` 按拍摄日筛跑步记录，挑与视频时间窗重叠的那一场。
2. `downloadActivityFitFiles` 拉 FIT；客户端不支持二进制时改 `queryActivityFitFileDownloadUrls` + `curl` 保存为 `YYYY-MM-DD-run-data.fit`（日限额约 50 个，一场只下一份）。
3. FIT 落地本身不标 `ingest`；`--apply` 成功才标。MCP 不可用时才退回手机导出 FIT。

## 不要做的事

- 不要 `cp` 完随手 `touch`（会毁掉 HUD `file-modified` 对齐）
- 不要覆盖已有 `YYYY-MM-DD-open.mp4` 等，除非 `--force` 且用户同意
- 不要把成片、HUD preview、封面再收进去，也不要把大文件 commit 进 git
- 不要用 `trim_talk_pauses.py --apply` 重编一套粗剪成片；句间刀只 `--record` 写时间表

## 步骤

1. **先 dry-run 核对角色与 mtime**：
   ```bash
   .venv/bin/python tools/ingest/ingest_run_media.py \
     --src <原始导出目录> \
     --date YYYY-MM-DD \
     --slug <slug> \
     --episode-dir episodes/YYYY-MM-DD-slug
   ```
   - 首段通常 `open`，尾段 `close`，中间 `run-a`/`run-b`…；无头尾加 `--no-open --no-close`；空镜标 `broll-01`（勿混进 `run-*`）。
   - 多份 FIT 时脚本按时间重叠自动挑；若两场都重叠或都不重叠会停下列候选，用 `--fit <文件名>` 指定。
   - 多段 `close`（FIT 结束后拍摄）自动命名为 `close-1`/`close-2`… 并无损拼成 `YYYY-MM-DD-close.mp4`（可用 `--close-clips N` 覆盖；保留 `close-N` 分段别删）。
   - 高驰截图（`Screenshot_*`/`*coros*`/`截图*`）改名为 `YYYY-MM-DD-stats-01.jpg`。
   - `VID_` 文件名是开始时间；若 `mtime` 与「开始 + 时长」差超 5 分钟，脚本会校正 `mtime` 为结束时间，先把变更给用户看一眼。
2. **用户确认后加 `--apply`**：重命名/拷入（`copy2` 保留时间）、锁原片↔FIT 写入 `logs/program.json` 的 `source_sync`，并自动执行句间刀 `--record`（不需要句间刀时加 `--skip-pause-trim`）。跑完自动记 `ingest` 墙钟并核对 `logs/todo.md`（`ingest: done`，有句间刀时 `edl: done`）。
3. **已收过素材需单独补句间刀**（默认 dry-run，确认后加 `--record`；默认保留片头，掐片头加 `--no-keep-lead-silence`）：
   ```bash
   .venv/bin/python tools/ingest/trim_talk_pauses.py \
     --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
     --record \
     --targets open,close,run
   ```
   算法门槛在脚本内，只调脚本看退出码；跑完核对 `logs/todo.md`（`edl: done`）。

## 完成与下一步

确认 `logs/todo.md` 中 `ingest`（及有句间刀时 `edl`）为 `done`，`assets.md` 写 `ingest: done`，`episode.md` 至少 `shot`。立刻推荐下一步（鞋名与口径用用户说过的，口径须为开跑前 / 跑完后 / 生涯总里程之一）：

> 下一步用 `/p3-shoes`，可以直接发：
>
> `/p3-shoes 鞋是 <HUD 名>，这是开跑前/跑完后 <数字> 公里`
