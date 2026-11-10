---
name: p3-episode
description: 一期跑步视频的调度入口。用户丢来未重命名的手机导出、VID_、FIT、跑鞋名和里程，或说做视频/成片/只做某一步时用。先盘点缺什么，向用户确认，再按需加载下一个 stage skill。不要一次加载全部 skill。成片总序真源在本 skill。
---

# 一期成片调度

用户典型输入只有：**未重命名的手机导出** + **跑鞋名和里程**。缺的信息逐步问，不要假设。一次只加载下一步 skill。还没有选题或 `talk.md` 时，先问要不要走 `p3-topic`，不要在成片流程里临场编观点。

60–90 秒发布剪辑走 `p3-jianying`。本调度默认全长成片。

## 不要做的事

- 不要一次把全部 stage skill 读进来
- 不要在没确认目标阶段时从头跑到尾
- 不要把 FIT GPS 发给 Open-Meteo
- 不要用生涯总里程直接当 HUD `-sk`
- 不要覆盖已有 `open/run-*/close`、HUD、成片，除非用户明确要重做
- 不要在成片流程里自行搬盘或删原片；归档走 `p3-archive`；发布/清临时走 `p3-publish`

## 产物图（总序）

```text
手机 VID_ / DCIM + FIT
  p3-scaffold   → episodes/YYYY-MM-DD-slug/episode.md
  p3-ingest     → ~/Movies/running-content/YYYY-MM-DD-slug/{open,run-*,close,FIT} + assets.md
  p3-shoes      → -sn / -sk

run-* + FIT + -sk
  p3-hud        → hud-renders/*-hud-preview.mp4
  p3-cover      → cover-*.jpg（与 HUD 并行）

hud-preview + open/close
  p3-assemble   → 拼画面（推荐拼时带响度）+ 抽帧核对

然后（可并行）
  p3-subs       → 转写→人改→force_align→subs: done + 简介/抖音文案
  p3-loudness   → 仅当拼时关了响度才补跑（loudness_only，不重拼）

subs + loudness 都就绪
  p3-burn       → burn_ass 烧字（不重拼）→ 可选 upload-ready 改名

双链齐
  p3-publish    → 写链接 / published / 合 episode PR / 复盘日志上 box / 清临时

换封面句 → p3-cover
再核对   → p3-qc（默认抽帧已在 assemble）
```

**推荐墙钟：** `assemble`（带响度）→ `subs` → `burn` → `publish`。响度/烧字勿再全量 assemble；编码成本见 `p3-assemble`。

**耗时记录（每期默认）：** 各 stage 写墙钟到媒体目录 `logs/timeline.txt`（step / elapsed_s / rc）；失败另记 `logs/failures.md`（step、rc、日志路径、短错误）。汇报时给各步加总 + 墙上总时长（并行步会短于加总）。

## 1. 先盘点，再问目标

在仓库和 `~/Movies/running-content/` 里找该日已有文件。对照 `episodes/*/assets.md` 的「制作状态」。先跑：

```bash
python3 tools/episode_status.py YYYY-MM-DD-slug   # 或 --latest
```

| 目标 | 最低前置 | 加载 |
| --- | --- | --- |
| 只收素材 | 原始视频 | `p3-ingest`（缺目录则先 `p3-scaffold`） |
| 只记鞋 | 鞋名 + 里程口径 | `p3-shoes` |
| 只做 HUD | 已命名 `run-*` + FIT + `-sk` | `p3-shoes`（若还没有 `-sk`）→ `p3-hud` |
| 只拼画面 | HUD preview | `p3-assemble`（推荐拼时带响度） |
| 只做字幕 | 成片 `run-final` | `p3-subs` |
| 只补响度 | 成片且尚未 loudness | `p3-loudness` |
| 只烧字 | `subs: done` + `loudness: done` | `p3-burn` |
| 发布 / 清临时 | 双链或用户说发完了 | `p3-publish` |
| 只换封面 | 自拍 + 封面句 | `p3-cover` |
| 再核对 | 成片 | `p3-qc` |
| 剪映短片 | HUD overlay | `p3-jianying` |
| 归档 / 腾空间 | 满 7 天的本地媒体目录 | `p3-archive` |
| 全长成片 | 原始素材或已收好的目录 | 按序走完需要的阶段 |

用户没说目标时，列出已有产物和缺的阶段，请他们选今天停在哪一步。

## 2. 确认清单（缺哪项问哪项）

一次不要超过这些问题里实际缺的：

1. **日期 / slug**：已有 `episodes/YYYY-MM-DD-*` 就复用。
2. **原始文件在哪**。
3. **open / run / close**：用 `VID_` 时间或 FIT 窗口提议；没有跑前口播就 `--no-open`。
4. **FIT**：没有则问 COROS MCP（国内 `mcpcn.coros.com`）。没有 FIT 不能渲 HUD。
5. **跑鞋名**。
6. **里程口径**：开跑前 / 跑完后 / 生涯总里程。本场 km 用 FIT。
7. **天气**：默认 `--weather-city shanghai`；不要则 `--no-weather`。
8. **封面句**：默认标题；封面走 `p3-cover`，与 HUD 并行。
9. **今天停在哪**：ingest / hud / assemble / subs / loudness / burn / publish / full。

## 完成后 / 引导下一步

确认后只加载一个 skill。盘点结束时**立刻**给出可复制提示词：

| 缺什么 | 提示词 |
| --- | --- |
| 没有 `episodes/` 目录 | `/p3-scaffold 日期 YYYY-MM-DD slug <slug>` |
| 没有 `open` / `run-*` | `/p3-ingest 原始文件在 <路径>` |
| 没有这一场 `-sk` | `/p3-shoes 鞋是 <HUD 名>，这是开跑前/跑完后 <数字> 公里` |
| 没有 HUD preview | `/p3-hud`（封面并行走 `/p3-cover`） |
| 没有成片 | `/p3-assemble`（推荐拼时带响度） |
| 没有字幕稿 | `/p3-subs` |
| 成片未修响度（拼时关了） | `/p3-loudness` |
| 字幕+响度都齐、未烧字 | `/p3-burn` |
| 已烧字、要发 / 清临时 | `/p3-publish` |
| 只要换封面 | `/p3-cover 封面句「<封面句>」` |
| 成片要再核对 | `/p3-qc` |
| 只要 60–90 秒 | `/p3-jianying` |
| 还没有选题 / `talk.md` | `/p3-topic` |
| 满 7 天要腾本机 | `/p3-archive` |

## 3. 状态（短）

- `episode.md`：`shot` → `hud` → `edited`（`p3-subs` 用户确认后）→ `published`（`p3-publish`；抖音不挡）。
- `assets.md`：`assemble` / `qc` / `loudness` / `subs` / `burn` / `upload`；拼时带响度则一并写 `loudness: done`。
- 改字幕：改 `subtitles.txt` 后重新生成媒体 SRT，一般不用重拼。改 `-sk`：重 HUD 再 assemble；preview 时长变了就重对口型。改封面句：只 `p3-cover`。
