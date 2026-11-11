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
  p3-ingest   → ~/Movies/running-content/YYYY-MM-DD-slug/{open,run-*,close,FIT} + assets.md
  p3-shoes    → -sn / -sk

run-* + FIT + -sk
  p3-hud      → hud-renders/*-hud-alpha.mov + *-hud-preview.mp4
  p3-cover    → cover-*.jpg（与 HUD 并行）

HUD preview + open / 数据图段或 close
  p3-assemble → review-preview.mp4 + 预览画面核对

review-preview
  p3-subs     → subtitles.txt → 人工改字 → 对齐/质检；用户确认后 subs: done

人工确认字幕后
  final_export.py --confirmed
              → 原片 + HUD alpha + stats + 字幕 + 响度一次编码
              → YYYY-MM-DD-run-final.mp4

双链齐
  p3-publish  → 写链接 / published / 合 episode PR / 复盘日志上 box / 清临时
  p3-publish-report → 复盘拷完后立刻出单屏 HTML（清临时仍在 p3-publish）
```

**唯一最终导出入口：** `tools/assemble/final_export.py`。它不读取 HUD preview、review preview 或 close-stats 视频；直接读取原片和 HUD alpha。`assemble_episode.py --ass`、`burn_ass.py`、`loudness_only.py` 不属于新流程。

**人工字幕门闩不能跳过：** `subtitles.txt` 是唯一源稿。用户确认前保持 `subs: waiting-review`，不能最终导出；用户确认后才写 `subs: done`，再执行 `final_export.py --confirmed`。

**墙钟日志（硬规则）：** 媒体目录 `logs/timeline.txt`，Asia/Shanghai，`YYYY-MM-DD HH:MM:SS`（不知道秒就不要编）。只追加，不改旧行。`START` / `END` / `FAIL` 各一行；`elapsed` 是这一步的墙钟，并行步不要把子步相加。失败再追加 `logs/failures.md`。没有该步的 `START` 和 `END`（或 `FAIL`）就不算做完。官方脚本会自己写；否则用 `tools/log_timeline.py`：

`.venv/bin/python tools/log_timeline.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug start|end|fail <step>`

步名：`scaffold` `ingest` `shoes` `cover` `hud-render` `review-preview` `draft-subs` `force-align` `final-export` `pack-upload` `drive-stage` `youtube-upload` `bilibili-upload` `published`。重试是新行。`p3-scaffold` 建期时就建 `logs/`，不要拖到最终导出。`p3-qc` 抽帧不单记一步。

## 目标与前置

| 目标 | 最低前置 | 加载 |
| --- | --- | --- |
| 只收素材 | 原始视频 | `p3-ingest`（缺目录则先 `p3-scaffold`） |
| 只记鞋 | 鞋名 + 里程口径 | `p3-shoes` |
| 只做 HUD | 已命名 `run-*` + FIT + `-sk` | `p3-shoes` → `p3-hud` |
| 只做预览 | 各段 HUD preview 已渲（有数据图则 close-stats） | `p3-assemble` |
| 只做字幕 | review preview | `p3-subs` |
| 最终导出 | `subs: done` + `qc: done` + 用户确认 | `final_export.py` |
| 发布 / 清临时 | 双链或用户说发完了 | `p3-publish` |
| 发布报告 | 已 published，复盘已拷 | `p3-publish-report` |
| 只换封面 | 自拍 + 封面句 | `p3-cover` |
| 再核对 | review preview 或最终成片 | `p3-qc` |
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
