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

## 产物图

```text
手机 VID_ / DCIM + FIT
  p3-scaffold     → episodes/YYYY-MM-DD-slug/episode.md
  p3-ingest     → ~/Movies/running-content/YYYY-MM-DD-slug/{open,run-*,close,FIT} + assets.md
  p3-shoes          → -sn / -sk（跑完后累计 km）

run-* + FIT + -sk
  p3-hud       → hud-renders/*-hud-preview.mp4 + cover-*.jpg（封面并行，用原片 run-a）

口播音频（分段或成片时间轴）
  p3-subs  → asr/* + 忠于原句 subtitles.srt / .txt（校正不改写；外挂）

hud-preview + open/close
  p3-assemble   → YYYY-MM-DD-run-final.mp4（不烧字幕）+ 抽帧核对，status=edited

换封面句
  p3-cover       → 只重出 cover-*.jpg，不重渲 HUD

再核对
  p3-qc         → 只再抽一轮；默认已在 assemble 里做过
```

## 1. 先盘点，再问目标

在仓库和 `~/Movies/running-content/` 里找该日已有文件。对照 `episodes/*/assets.md` 的「制作状态」。

| 目标 | 最低前置 | 加载 |
| --- | --- | --- |
| 只收素材 | 原始视频 | `p3-ingest`（缺目录则先 `p3-scaffold`） |
| 只记鞋 | 鞋名 + 里程口径 | `p3-shoes` |
| 只做 HUD | 已命名 `run-*` + FIT + `-sk` | `p3-shoes`（若还没有 `-sk`）→ `p3-hud`（顺带封面） |
| 只做字幕 | 已命名片段或成片时间轴 | `p3-subs` |
| 只换封面 | `run-a` + 标题 | `p3-cover` |
| 只拼接 | HUD preview | `p3-assemble`（默认不烧字幕；拼完立刻核对） |
| 再核对 | 成片 | `p3-qc` |
| 剪映短片 | HUD overlay | `p3-jianying` |
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
8. **封面句**：默认 `episode.md` / `talk.md` 标题，系列名「破三实验室」。跟 HUD 一起做，除非用户只要换封面。
9. **今天停在哪**：ingest / hud / subs / assemble / full。

## 完成后 / 引导下一步

确认后只加载一个 skill。盘点结束时**立刻**给出可复制提示词，不要只说「下一步是某某」。把日期、slug、路径、鞋名换成当前期：

| 缺什么 | 提示词 |
| --- | --- |
| 没有 `episodes/` 目录 | `/p3-scaffold 日期 YYYY-MM-DD slug <slug>` |
| 没有 `open` / `run-*` | `/p3-ingest 原始文件在 <路径>` |
| 没有这一场 `-sk` | `/p3-shoes 鞋是 <HUD 名>，这是开跑前/跑完后 <数字> 公里` |
| 没有 HUD preview | `/p3-hud`（封面一并做） |
| 没有字幕稿 | `/p3-subs` |
| 只要换封面 | `/p3-cover 封面句「<封面句>」` |
| 没有成片 | `/p3-assemble`（拼完立刻核对） |
| 成片要再核对 | `/p3-qc` |
| 只要 60–90 秒 | `/p3-jianying` |
| 还没有选题 / `talk.md` | `/p3-topic` |

用户说继续，再加载下一阶段。各 stage skill 做完也会自己推荐下一步。

改字幕：改 `subtitles.txt` 后跑 `tools/subs/txt_to_subs.py` 回写 SRT，不用重拼成片。`p3-subs` 写完稿必须停，等人手改字；改好后再对口型，再拼。用户没明确说烧进去时，assemble 不要加 `--ass`。
改 `-sk`：重跑 HUD，再 assemble。
改封面句：只重跑 `p3-cover`。

## 3. 状态

`episode.md`：ingest 完成后至少 `shot`；HUD 完成后 `hud`；assemble 核对通过后 `edited`。
