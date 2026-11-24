---
name: p3-episode
description: 一期跑步视频的调度入口、产物总序与全局协议真源。用户丢来未重命名的手机导出、VID_、FIT、跑鞋名和里程，或说做视频/成片/只做某一步时用。先盘点缺什么，向用户确认，再按需加载下一个 stage skill。不要一次加载全部 skill。
---

# 一期成片调度

用户典型输入只有：**未重命名的手机导出** + **跑鞋名和里程**。缺的信息逐步问，不要假设。一次只加载下一步 skill。还没有选题或 `talk.md` 时，先问要不要走 `/p3-topic`。60–90 秒短视频走 `/p3-jianying`，本调度默认全长成片。

## 不要做的事

- 不要一次把全部 stage skill 读进来；没确认目标阶段时不要从头跑到尾
- 不要把 FIT GPS 发给 Open-Meteo；不要用生涯总里程直接当 HUD `-sk`
- 不要覆盖已有原片、HUD、预览或最终成片，除非用户明确要重做
- 不要在成片流程里自行搬盘或删原片（归档走 `/p3-archive`，清临时走 `/p3-publish`）
- 不要在最终导出前单独烧字或对成片补跑响度；历史旁路 `assemble_episode.py --ass`、`burn_ass.py`、`loudness_only.py` 不属于新流程

## 全局协议（所有成片 skill 共用）

子 skill 不重复展开以下 4 条，统一以本节为准：

1. **进度清单门闩（`logs/todo.md`）**：这是硬门闩，不是备忘；**不要拿文件名或 `assets.md` 当进度**。每跑完脚本或完成一步立刻读 `logs/todo.md`，该标的马上标；清单不对就停。前置未完成禁止打勾。手补命令：
   ```bash
   .venv/bin/python tools/todo_list.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug mark <step> done
   ```
   字幕状态为 `waiting-review` / `aligned` / `confirmed`；标 `confirmed` 必须加 `--confirmed` 且仅限用户明确确认后。改刀点、冷开场、插入或重记 HUD 规格时，脚本会把已勾的准备步骤打回 `pending`。
2. **墙钟日志（`logs/timeline.txt` + `logs/failures.md`）**：Asia/Shanghai，`YYYY-MM-DD HH:MM:SS`（不知秒就别编），只追加不改旧行。`START`/`END`/`FAIL` 各一行，失败自动追加 `failures.md`。官方脚本会自动写，无脚本挂钩时用：
   ```bash
   .venv/bin/python tools/log_timeline.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug start|end|fail <step>
   ```
   步名：`scaffold` `ingest` `shoes` `cover` `hud-render` `review-preview` `draft-subs` `force-align` `final-export` `pack-upload` `drive-stage` `youtube-upload` `bilibili-upload` `published`（`p3-qc` 不单记）。
3. **唯三人工等待点**（其它步骤不要停下来等确认；封面确认、打开审片预览、必听硬失败都不是等待点）：
   - `subs: waiting-review`：字幕初稿写完立刻停，等人改错字和换行（期间立刻并行跑 HUD 透明层和响度测量）；用户确认且 `subs: confirmed` 之前禁止 `final_export.py --confirmed`。
   - `final-qc: done`：抽帧通过后停，等用户说「可以发了」再打包或发布。
   - `published: done` 后 `cleanup: pending`：先列 KEEP/DELETE 体积表，用户确认后才能移入废纸篓（禁止 `rm`）并标 `cleanup: done`。
4. **不经同意不开播放器或编辑器（硬规则）**：未经用户明确说「打开」或同意当次询问，禁止启动 IINA / mpv / TextEdit / 预览器（未经同意播放会吓到人）。先问要不要打开 `subtitles.txt` 和审片预览，他只点一样就只开那样。同意后命令：
   ```bash
   open -a TextEdit episodes/YYYY-MM-DD-slug/subtitles.txt   # .md 用 open -a Typora <path.md>
   iina --no-stdin ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.edl
   # 有同名 sidecar 才加：-- --sub-files=~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-review-preview.srt
   # 打开烧字成片：iina --no-stdin ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4（严禁旁边留同名 .srt）
   ```
   IINA 走 libmpv，不要用 `--mpv-sub-file`（会静默丢掉）；mpv 命令行则不加 `--no-stdin`、用 `--sub-file=`。

## 产物总序

```text
手机 VID_ / DCIM + 高驰 FIT
  p3-scaffold → episodes/YYYY-MM-DD-slug/ + 媒体目录 logs/todo.md（全 pending）
  p3-ingest   → open/run-*/close + FIT；锁原片↔FIT，句间刀只写 logs/program.json
  p3-shoes    → -sn / -sk
  p3-hud      → --record-only（鞋/天气/规格入表，不渲未剪预览） ∥ p3-cover（三比例封面）
  冷开场 / 贴图 / 插入入表（layout: done）
  p3-assemble → 按 program.json 写 review-preview.edl（不编预览 mp4）
  p3-subs     → 转写；冻结时间表；waiting-review 停
  [并行] 用户校对字幕 ∥ render_running_hud.py --prep-alpha -j 6 ∥ final_export.py --measure-only
  用户确认字幕（subs: confirmed）
  final_export.py --confirmed → 唯一最终编码，产出 YYYY-MM-DD-run-final.mp4
  p3-qc       → 抽帧核对（final-qc: done）→ 等用户说「可以发了」
  pack_upload.py → upload/ → （可选）p3-bilibili ∥ p3-youtube
  双链齐 → p3-publish（写链接 / published / squash 合 episode PR）
         → p3-publish-report（单屏 HTML + 统一同步 Google Drive running-retrospect/）
         → p3-publish 清临时确认（移废纸篓 → cleanup: done）
```

## 时间表、过渡与贴图

`logs/program.json` 管两套时钟：`source_sync`（原片对 FIT 偏移，HUD 永远按原片取样）和 `program`（成片时间线）。预览与 `final_export.py` 共用同一张表（schema 见 `tools/program_edl.py`）。

- `xfade`：冷开场进首段跑、末段跑进 close，默认 0.2s 重叠（成片变短）。
- `wind`：不同原片的跑步段接缝，默认 0.08s 不缩短总时长（导出时画风刮 + `whoosh.wav`，预览为硬切）。同原片句间刀和插入段默认硬切。
- 手写贴图若按某版成片量秒数，必须带 `--expect-duration`（差超 0.15s 拒绝写入）；数据图用 `close-stats` 自动均分：
  ```bash
  .venv/bin/python tools/program_edl.py \
    --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
    overlay --asset <图> --start <秒> --end <秒> \
    --expect-duration <当时的成片秒数> --role graphic
  ```
  冷开场、贴图、插入都入表后 `layout` 才标 `done`。

## 目标与前置路由

| 目标 | 最低前置 | 加载 |
| --- | --- | --- |
| 只收素材 | 原始视频 | `p3-ingest`（缺目录先 `p3-scaffold`） |
| 只记鞋 | 鞋名 + 里程口径 | `p3-shoes` |
| 只做 HUD | `run-*` + FIT + `-sk` + `source_sync` | `p3-shoes` → `p3-hud` |
| 只做预览 | `logs/program.json`（`layout: done`） | `p3-assemble` |
| 只做字幕 | `review-preview.edl` 且刀点定稿 | `p3-subs` |
| 冻结后准备 | 时间表冻结且 `preview: done` | `render_running_hud.py --prep-alpha -j 6` ∥ `final_export.py --measure-only` |
| 最终导出 | `subs: confirmed` 且时间表冻结 | `final_export.py --confirmed` |
| 再核对 | 审片清单或最终片 | `p3-qc` |
| 投 B 站 / YouTube | `pack-upload: done` | `p3-bilibili` / `p3-youtube` |
| 发布收尾 / 清临时 | 「可以发了」打包；双链齐再 `published` | `p3-publish` |
| 发布报告 | `published: done` | `p3-publish-report` |
| 只换封面 | 自拍 + 封面句 | `p3-cover` |
| 剪映短片 | HUD alpha | `p3-jianying` |
| 满 7 天归档 | 满 7 天本地媒体目录 | `p3-archive` |

用户没说目标时，列出已有产物和缺的阶段，请他们选今天停在哪一步。

## 最终导出（唯一入口）

确认字幕（`subs: confirmed`）后，只跑一次 `final_export.py --confirmed`（缺的透明层或响度会自动补齐，内部编排与规格见 `tools/assemble/final_export.py` 与 `tools/export-spec.json`，默认 1080p30 HEVC）：

```bash
.venv/bin/python tools/assemble/final_export.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug \
  --episode-dir episodes/YYYY-MM-DD-slug \
  --out ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  --confirmed
```

跑完核对 `logs/todo.md`（`final-export: done`，`final-qc: pending`），转 `/p3-qc` 抽帧通过并标 `final-qc: done` 后停下，等用户说「可以发了」。
