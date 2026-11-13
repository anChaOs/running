---
name: p3-episode
description: 一期跑步视频的调度入口。用户丢来未重命名的手机导出、VID_、FIT、跑鞋名和里程，或说做视频/成片/只做某一步时用。先盘点缺什么，向用户确认，再按需加载下一个 stage skill。不要一次加载全部 skill。成片总序真源在本 skill。
---

# 一期成片调度

用户典型输入只有：**未重命名的手机导出** + **跑鞋名和里程**。缺的信息逐步问，不要假设。一次只加载下一步 skill。还没有选题或 `talk.md` 时，先问要不要走 `p3-topic`。

60–90 秒发布剪辑走 `p3-jianying`。本调度默认全长成片。

## 不要做的事

- 不要一次把全部 stage skill 读进来
- 不要在没确认目标阶段时从头跑到尾
- 不要把 FIT GPS 发给 Open-Meteo
- 不要用生涯总里程直接当 HUD `-sk`
- 不要覆盖已有原片、HUD、预览或最终成片，除非用户明确要重做
- 不要在成片流程里自行搬盘或删原片；归档走 `p3-archive`；发布/清临时走 `p3-publish`

## 产物图（总序）

```text
手机 VID_ / DCIM + FIT
  p3-scaffold → episodes/YYYY-MM-DD-slug/episode.md
  p3-ingest   → 收成 open/run-*/close + FIT
              → 锁原片↔FIT，句间刀只写进 logs/program.json（不重编码）
  p3-shoes    → -sn / -sk

p3-hud --record-only → 鞋、天气、透明层规格记进同一张表，不渲未剪预览
p3-cover             → cover-*.jpg（与记录 HUD 并行）

冷开场 / 贴图 / 插入写进同一张表
  p3-assemble → 按时间表写 review-preview.edl 播放清单（不拼预览成片，不渲 HUD）

review-preview
  p3-subs     → 转写。对口型前冻结时间表。之后改刀点必须按新表重对齐
              → 冻结后，用户只改错字和换行；同时可以画 HUD、测响度

frozen，字幕还在校对
  render_running_hud.py --prep-alpha
              → 按留下的入出点直接画透明层，不写 hud-renders/keeps/
  final_export.py --measure-only
              → 只测切点 + 风刮/whoosh 的成片混音，不读字幕

subs: done，且时间表已冻结、logs/todo.md 允许导出
  final_export.py --confirmed
              → 缺的透明层或响度自己补上
              → 同一张表：裁原片、叠 HUD、xfade、风刮和 whoosh、贴图、烧字幕、套用已测响度，一次编码
              → YYYY-MM-DD-run-final.mp4

双链齐
  p3-publish  → 写链接 / published / 合 episode PR / 复盘日志上 box / 清临时
  p3-publish-report → 复盘拷完后立刻出单屏 HTML（清临时仍在 p3-publish）
```

时间表在媒体目录 `logs/program.json`。两套时钟：`source_sync` 是原片对 FIT 的偏移，HUD 永远按原片时间取样；`program` 是成片时间，句间刀、冷开场、插入、转场只改这张。预览和 `final_export.py` 读同一份。schema 见 `tools/program_edl.py` 模块说明。

两种过渡不要混：

- `xfade`：冷开场进第一段跑、最后一段跑进 close。默认 0.2 秒，两段重叠，成片变短。
- `wind`：不同原片的跑步段接缝。默认 0.08 秒，不重叠、不缩短总时长。确认导出时落到整数帧，画风刮并叠 `whoosh.wav`。同一条原片里的句间刀仍是硬切。插入段默认硬切；要过渡就在插入上写 `transition: wind` 或 `xfade`。

预览不画风刮，只保证时长和导出一致。

手写贴图的秒数如果是从某一条成片上量的，必须带上当时的成片时长。差过 0.15 秒就拒绝写入。之后刀点、冷开场或插入改了表，导出也会拒绝，直到按新表重放这张图。数据图用 `close-stats`，按 close 段均分，不手写秒数。

```bash
.venv/bin/python tools/program_edl.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  overlay --asset <图> --start <秒> --end <秒> \
  --expect-duration <当时的成片秒数> --role graphic
```

**唯一最终导出入口：** `tools/assemble/final_export.py --confirmed`。它不读取 HUD preview、review preview、close-stats 或 `hud-renders/keeps/`。有 `logs/program.json` 时按那张表裁原片，并叠已经画好的透明层；透明层或响度测量对不上当前表时，这条命令先补再编码。没有这张表时仍走旧的整段原片路径。`assemble_episode.py --ass`、`burn_ass.py`、`loudness_only.py` 不属于新流程。不要先导出无字幕成片，再烧字，再改响度。

**人工字幕门闩不能跳过：** `subtitles.txt` 是唯一源稿。用户确认前保持 `subs: waiting-review`，不能最终导出；用户确认后才写 `subs: done`，再执行 `final_export.py --confirmed`。对口型前时间表必须 `frozen`。改了刀点、冷开场或插入段之后，旧字幕作废，必须按新表重对齐，不能假定还对准。

**墙钟日志（硬规则）：** 媒体目录 `logs/timeline.txt`，Asia/Shanghai，`YYYY-MM-DD HH:MM:SS`（不知道秒就不要编）。只追加，不改旧行。`START` / `END` / `FAIL` 各一行；`elapsed` 是这一步的墙钟，并行步不要把子步相加。失败再追加 `logs/failures.md`。没有该步的 `START` 和 `END`（或 `FAIL`）就不算做完。官方脚本会自己写；否则用 `tools/log_timeline.py`：

`.venv/bin/python tools/log_timeline.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug start|end|fail <step>`

步名：`scaffold` `ingest` `shoes` `cover` `hud-render` `review-preview` `draft-subs` `force-align` `final-export` `pack-upload` `drive-stage` `youtube-upload` `bilibili-upload` `published`。重试是新行。`p3-scaffold` 建期时就建 `logs/`，不要拖到最终导出。`p3-qc` 抽帧不单记一步。

**进度清单（硬规则）：** 同一目录 `logs/todo.md`，和 `timeline.txt` 一起维护，一直到 `published`。这是门闩，不是备忘。状态以这份文件为准，不能只看文件名或 `assets.md` 里写了 done。未写入 todo 不算这一步完成。有前置的步骤，前置没完成不能打勾。`hud-render` 和 `loudness-measure` 只要求预览已完成，字幕校对时可以先打勾；`final-export` 仍要字幕 `confirmed` 再加 `--confirmed`。改刀点、冷开场、插入，或重记鞋和规格时，脚本会把已经打勾的准备步骤改回 pending。官方脚本会写；手补用：

`.venv/bin/python tools/todo_list.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug mark <step> done`

字幕状态是 `waiting-review` / `aligned` / `confirmed`。写成 `confirmed` 必须加 `--confirmed`，而且只有用户明确确认之后才能写。导出、打包、发布会读这份文件：todo 不合法就停。

## 目标与前置

| 目标 | 最低前置 | 加载 |
| --- | --- | --- |
| 只收素材 | 原始视频 | `p3-ingest`（缺目录则先 `p3-scaffold`） |
| 只记鞋 | 鞋名 + 里程口径 | `p3-shoes` |
| 只做 HUD | 已命名 `run-*` + FIT + `-sk`，时间表已有原片对齐 | `p3-shoes` → `p3-hud`（只记录，不渲） |
| 只做预览 | `logs/program.json` 已排好成片时间 | `p3-assemble` |
| 只做字幕 | 审片播放清单已写出，且刀点不再改 | `p3-subs` |
| 冻结后的准备 | 时间表已冻结、预览已完成；字幕可以还在校对 | `render_running_hud.py --prep-alpha`，可选 `final_export.py --measure-only` |
| 最终导出 | `subs: done` + `qc: done` + 用户确认 + 时间表已冻结 + `logs/todo.md` 允许导出 | `final_export.py --confirmed` |
| 发布 / 清临时 | 双链或用户说发完了 | `p3-publish` |
| 发布报告 | 已 published，复盘已拷 | `p3-publish-report` |
| 只换封面 | 自拍 + 封面句 | `p3-cover` |
| 再核对 | 审片清单或最终成片 | `p3-qc` |
| 剪映短片 | HUD alpha | `p3-jianying` |
| 归档 / 腾空间 | 满 7 天的本地媒体目录 | `p3-archive` |

用户没说目标时，列出已有产物和缺的阶段，请他们选今天停在哪一步。

## 字幕与最终导出

`p3-subs` 在写完 `subtitles.txt` 后必须停下来等人改字。force_align 可以在用户说改好后运行，但硬失败行仍须人听；只有用户明确确认后才改 `subs: done` 和 `episode.md` 的 `edited`。

最终导出命令：

```bash
.venv/bin/python tools/assemble/final_export.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --episode-dir episodes/YYYY-MM-DD-slug \
  --out ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  --confirmed
```

最终 profile 来自 `tools/export-spec.json`，默认 1080p30 HEVC；`--test-codec` 只给隔离测试使用。切到 4K 主要改规格配置并重新渲 HUD/预览，不在本次实现完整 4K 验收。
