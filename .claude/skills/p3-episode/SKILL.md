---
name: p3-episode
description: 一期跑步视频的调度入口。用户丢来未重命名的手机导出、VID_、FIT、跑鞋名和里程，或说做视频/成片/只做某一步时用。先盘点缺什么，向用户确认，再按需加载下一个 stage skill。不要一次加载全部 skill。
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
- 不要在成片流程里自行搬盘或删原片；归档走 `p3-archive`。发布完毕且两边链接都齐时，写链接 / `published` / 合 PR / 清临时走 `p3-publish`（真源；先确认再进废纸篓）
- 发布前**只把成片** `YYYY-MM-DD-run-final.mp4` 原地改成标题名；**字幕文件名不要改**，上传外挂用 `subtitles.srt`

## 产物图

```text
手机 VID_ / DCIM + FIT
  p3-scaffold     → episodes/YYYY-MM-DD-slug/episode.md
  p3-ingest     → ~/Movies/running-content/YYYY-MM-DD-slug/{open,run-*,close,FIT} + assets.md
  p3-shoes          → -sn / -sk（跑完后累计 km）

run-* + FIT + -sk
  p3-hud       → hud-renders/*-hud-preview.mp4
  p3-cover     → cover-*.jpg（与 HUD 并行，自拍抠图合成）

hud-preview + open/close
  p3-assemble   → 拼画面：可对字幕成片 + 抽帧核对（默认不响度、不烧字）

然后并行（互不等待开工）
  p3-subs       → 转写→人改→force_align→subs: done + 简介
  p3-loudness   → 响度链定稿（loudness: done）

两者都就绪
  p3-burn       → ASS 烧字最终片 → 可选 upload-ready 改名

双链齐
  p3-publish    → 写链接 / published / 合 episode PR / 清临时

换封面句
  p3-cover       → 重出 cover-*.jpg，不重渲 HUD

再核对
  p3-qc         → 只再抽一轮；默认已在 assemble 里做过
```

## 1. 先盘点，再问目标

在仓库和 `~/Movies/running-content/` 里找该日已有文件。对照 `episodes/*/assets.md` 的「制作状态」。先跑一次盘点脚本（只读，不开播放器），它会列出已有/缺失并给下一步提示词：

```bash
python3 tools/episode_status.py YYYY-MM-DD-slug   # 或 --latest
```

| 目标 | 最低前置 | 加载 |
| --- | --- | --- |
| 只收素材 | 原始视频 | `p3-ingest`（缺目录则先 `p3-scaffold`） |
| 只记鞋 | 鞋名 + 里程口径 | `p3-shoes` |
| 只做 HUD | 已命名 `run-*` + FIT + `-sk` | `p3-shoes`（若还没有 `-sk`）→ `p3-hud` |
| 只拼画面 | HUD preview | `p3-assemble`（默认不响度、不烧字；拼完立刻核对） |
| 只做字幕 | 成片 `run-final` | `p3-subs`（可与响度并行） |
| 只做响度 | 成片 `run-final` | `p3-loudness`（可与字幕并行） |
| 只烧字 | `subs: done` + `loudness: done` | `p3-burn` |
| 发布 / 清临时 | 双链（B 站+YouTube）或用户说发完了 | `p3-publish` |
| 只换封面 | 自拍 + 封面句 | `p3-cover` |
| 再核对 | 成片 | `p3-qc` |
| 剪映短片 | HUD overlay | `p3-jianying` |
| 归档 / 腾空间 | 满 7 天的本地媒体目录 | `p3-archive` |
| 全长成片 | 原始素材或已收好的目录 | 按序走完需要的阶段 |

用户没说目标时，列出已有产物和缺的阶段，请他们选今天停在哪一步。

## 2. 确认清单（缺哪项问哪项）

一次不要超过这些问题里实际缺的：

1. **日期 / slug**：已有 `episodes/YYYY-MM-DD-*` 就复用，不要新建平行目录。
2. **原始文件在哪**：相册导出文件夹、AirDrop 下载目录，或已经在 `~/Movies/running-content/`。
3. **open / run / close**：用 `VID_` 时间或 FIT 窗口提议，B-roll 单独标。没有跑前口播就 `--no-open`。
4. **FIT**：没有则问要不要 COROS MCP 拉（国内节点 `mcpcn.coros.com`）。没有 FIT 不能渲 HUD。
5. **跑鞋名**。
6. **里程口径**：开跑前 / 跑完后 / 现在的生涯总里程。生涯总里程要减去本场 km 才是开跑前。本场 km 用 FIT。
7. **天气**：默认上海城市场点 `--weather-city shanghai`。明确不要则 `--no-weather`。
8. **封面句**：默认 `episode.md` / `talk.md` 标题，系列名「破三实验室」。封面走 `p3-cover`，与 HUD 并行。
9. **今天停在哪**：ingest / hud / assemble / subs / loudness / burn / publish / full。

## 完成后 / 引导下一步

确认后只加载一个 skill。盘点结束时**立刻**给出可复制提示词，不要只说「下一步是某某」。把日期、slug、路径、鞋名换成当前期：

| 缺什么 | 提示词 |
| --- | --- |
| 没有 `episodes/` 目录 | `/p3-scaffold 日期 YYYY-MM-DD slug <slug>` |
| 没有 `open` / `run-*` | `/p3-ingest 原始文件在 <路径>` |
| 没有这一场 `-sk` | `/p3-shoes 鞋是 <HUD 名>，这是开跑前/跑完后 <数字> 公里` |
| 没有 HUD preview | `/p3-hud`（封面并行走 `/p3-cover`） |
| 没有成片 | `/p3-assemble`（拼画面；拼完立刻核对） |
| 没有字幕稿 | `/p3-subs`（对着成片转写；可与响度并行） |
| 成片未修响度 | `/p3-loudness`（可与字幕并行） |
| 字幕+响度都齐、未烧字 | `/p3-burn` |
| 已烧字、要发 / 清临时 | `/p3-publish` |
| 只要换封面 | `/p3-cover 封面句「<封面句>」` |
| 成片要再核对 | `/p3-qc` |
| 只要 60–90 秒 | `/p3-jianying` |
| 还没有选题 / `talk.md` | `/p3-topic` |
| 满 7 天要腾本机 | `/p3-archive` |

用户说继续，再加载下一阶段。各 stage skill 做完也会自己推荐下一步。

改字幕：改 `subtitles.txt` 后跑 `tools/subs/txt_to_subs.py` 回写 SRT，不用重拼成片。`p3-subs` 写完稿必须停，等人手改字；改好后用 `tools/subs/force_align.py` 对时间，`tools/subs/check_subs.py` 过门比例不超标。烧字只走 `p3-burn`（须响度也就绪），不要在 assemble/subs 里加 `--ass`。
改 `-sk`：重跑 HUD，再 assemble。preview 时长变了，就对着新成片重新对口型；响度/烧字按需重跑。
改封面句：只重跑 `p3-cover`。

## 3. 状态

`episode.md`：ingest 完成后至少 `shot`；HUD 完成后 `hud`；字幕对口型完成后 `edited`；发布后记链接（B 站 + YouTube）后 `published`（**抖音不挡** `published`）；`published` 且双链写完后，**自动 merge 该期 episode PR 进 `main`**（细节以 `p3-publish` 为准），再按 `p3-publish` 清该期媒体目录（先列保留/删除清单与体积 → 用户确认 → 进废纸篓，禁止 `rm`）。抖音短链随后写入「发布」栏。成片按 `p3-burn` / `p3-publish`：**只留一份标题烧字 `.mp4`**；`*-no-burn` 清理见 `p3-burn`。抖音文案与 `#` 话题规则见 `p3-subs`；写链接与清临时见 `p3-publish`。
`assets.md`：拼画面核对后 `assemble: done`、`qc: done`；响度后 `loudness: done`；字幕确认后 `subs: done`；烧字后 `burn: done`。`episode.md` 在拼画面后仍是 `hud`，字幕确认后才 `edited`。
