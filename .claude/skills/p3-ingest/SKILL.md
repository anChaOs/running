---
name: p3-ingest
description: 把手机未重命名导出（VID_*.mp4、DCIM）收进 ~/Movies/running-content/YYYY-MM-DD-slug/，按时间改成 open/run-*/close，写 assets.md。FIT 用高驰 MCP 拉，不要等手表拷贝。用户说收素材、重命名、ingest、手机导出时用。必须保留或校正 mtime，HUD 用它当视频结束时间。
---

# 收素材并命名

小米导出常见 `VID_YYYYMMDD_HHMMSS.mp4`。FIT 用高驰 MCP 拉，落到 `YYYY-MM-DD-run-data.fit`。大文件只放仓库外。

## 前置

日期、slug、原始文件夹路径。角色分配要给用户看过再 `--apply`。

## FIT：高驰 MCP

目录里没有当天 FIT 时，**用高驰 MCP 拉**，不要让用户从手表/App 再拷一份。国内账号节点是 `https://mcpcn.coros.com/mcp`（见 `knowledge/production/COROS-MCP.md`）。未授权就走 OAuth，浏览器回调失败则把地址栏 URL 交给 `mcp__coros__complete_authentication`。

1. `querySportRecords` 按**拍摄日**筛跑步记录。对上视频时间窗的那一场。同一天有多场，按开跑时间和视频重叠来挑，不要拿相邻那天的课。
2. `downloadActivityFitFiles` 拉该场 FIT。客户端吃不下二进制时改用 `queryActivityFitFileDownloadUrls`，再 `curl` 到媒体目录。
3. 保存为 `~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-data.fit`。多场只留和跑步重叠的那一个。
4. FIT 日限额大约 50 个，一场只下一份。

MCP 只负责把 FIT 拿回来。HUD 对齐仍看视频 `mtime` 和 FIT 时间窗，不要把 FIT GPS 发给天气接口。MCP 不可用时，才退回手机导出的 FIT（文件名可能是 `上海市_跑步*.fit` 或课表名）。

## 不要做的事

- 不要 `cp` 完再随手 `touch`，会毁掉 HUD 对齐
- 不要覆盖已有 `YYYY-MM-DD-open.mp4` 等，除非 `--force` 且用户同意
- 不要把成片、HUD preview、封面再收进去（脚本会跳过文件名含 `hud` / `run-final` / `cover-` 的）
- 不要把大文件 commit 进 git

## 步骤

先 dry-run：

```bash
.venv/bin/python tools/ingest/ingest_run_media.py \
  --src <原始导出目录> \
  --date YYYY-MM-DD \
  --slug <slug> \
  --episode-dir episodes/YYYY-MM-DD-slug
```

核对角色：

- 第一段通常 `open`（跑前），最后一段 `close`（跑后），中间 `run-a`、`run-b`…
- 只有跑中：`--no-open --no-close`
- 空镜标成 `broll-01`，不要混进 `run-*`（HUD 会扫全部 `*-run-*.mp4`）
- FIT 已由高驰 MCP 写成 `YYYY-MM-DD-run-data.fit`。目录里还有别的 FIT 时，只留和跑步时间重叠的那一个
- 高驰截图（`Screenshot_*` / `*coros*` / `截图*`）改名为 `YYYY-MM-DD-stats-01.jpg`。拼成片时叠到 close 左侧

`VID_` 文件名是开始时间。脚本若发现 `mtime` 和「开始 + 时长」相差超过 5 分钟，会把 `mtime` 改成结束时间。这是 HUD `--video-end-time-mode file-modified` 的前提。把将要改写的 mtime 打给用户看一眼。

用户确认后加 `--apply`。源文件已在目标目录里则只改名；从相册拷来则 `copy2` 保留时间。

`--apply` 之后会给 **open / close** 做句间停顿粗剪（**不剪原片 `run-*`**，HUD 要靠 mtime 和 FIT 1:1。跑中口播的句间粗剪在 HUD preview 上做，见 `p3-hud`）：

```bash
.venv/bin/python tools/ingest/trim_talk_pauses.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

默认 dry-run，列出要剪短的间隔。确认后加 `--apply`。原片改名为 `*-open-raw.mp4` / `*-close-raw.mp4`，工作文件仍是 `*-open.mp4` / `*-close.mp4`。只剪「明显长于句间均值」的停顿：门槛是 `max(2×均值, 均值+1.2s)` 且至少 1.2s，给思考停顿留空。剪的时候收到**均值 + 约 0.45s 安全余量**，不要收到均值；超长停顿左右都留肩，防止切到下一句开头。口播检测默认 **Silero VAD**（`whisper-vad-speech-segments` + `~/Movies/running-content/.models/ggml-silero-v5.1.2.bin`，约 864K）。这是人声 vs 风/车，不是声纹，路人说话也会留下。能量门限兜底才用 `--speech-detect band`（280–3500 Hz）。0.08s 以上的短音节当说话。片尾 **3 秒整段保留**。音画必须同一起止 trim 再 concat，不要用 `select`/`aselect` 分轨切（会漂）。不要剪 `run-*`，也不要动 `run-*` 的 mtime。不需要粗剪时，ingest 加 `--skip-pause-trim`。

ingest `--apply` 会直接跑粗剪 `--apply`。已经收过的素材，单独跑上面这条。

## 完成

- 媒体目录有 `open` / `run-*` / `close` / `*-run-data.fit`；open/close 若粗剪过，另有 `*-raw.mp4`
- `episodes/YYYY-MM-DD-slug/assets.md` 有原名映射和制作状态 `ingest: done`
- `episode.md` 至少 `shot`

## 完成后

`ingest: done`、`episode.md` 至少 `shot` 之后，立刻推荐下一步。鞋名和里程口径用用户说过的，不要编。

> 下一步用 `/p3-shoes`，可以直接发：
>
> `/p3-shoes 鞋是 <HUD 名>，这是开跑前/跑完后 <数字> 公里`

口径必须是三者之一：开跑前、跑完后、现在的生涯总里程。用户没说清楚就先问，不要带着含糊的数去 `p3-hud`。

只要收素材也可以停。记完鞋下一步仍是 `/p3-hud`（成片主轨是 preview）。
