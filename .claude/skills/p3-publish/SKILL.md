---
name: p3-publish
description: 发布收尾：用户给齐 B 站 + YouTube 链接后写 episode 发布栏、status=published、该期 episode PR squash 合 main；接着将制作复盘日志同步到 Google Drive 长期留存并出发布报告；再列清临时 KEEP/DELETE（体积）→ 人确认 → 进废纸篓。抖音短链不挡 published，随后写入。用户说发布完毕、发完了、已发布、写链接、合 episode PR、清临时时用。满 7 天整夹归档见 p3-archive。
---

# 发布

烧字 / upload-ready 之后：**写双链 → `published` → squash 合本期 episode PR → 复盘日志同步 Google Drive（随 `/p3-publish-report` 一并同步）→ 清临时**。

## 不要做的事

- 不要在缺 B 站或 YouTube 任一链接时写 `published` 或合 PR
- 不要用抖音是否已发来挡 `published`（抖音短链随后补）
- 不要在用户确认前删任何临时文件
- 清临时禁止 `rm` / `rm -rf`；只进废纸篓
- 不要整夹删媒体目录；满 7 天搬盘走 `p3-archive`
- `published` 之后必须把复盘日志同步到 Google Drive `running-retrospect/`
- 复盘目录不要放视频、FIT、封面、原片

## 前置

通常已走完一次 `final_export.py --confirmed`，并完成最终片人工核对。HUD 透明层和响度测量可以在字幕校对时先做完；确认导出仍然是烧进字幕的那一次命令，不是先出无字幕成片再补。`logs/todo.md` 里 `final-qc` 已是 done 之后，等用户说「没问题了 / 可以发了」再打包。这是清单上的等待点。真正写链接与清临时要等双链到手。进来先读清单。`final-export` 和 `final-qc` 不是 done 就停，不要拿文件名或 `assets.md` 当进度。

## 上传清单（用户说可以发了时给）

从 `plan.md` 抄标题、封面句、简介。简介按平台原样抄：「### B 站」和「### YouTube」各抄各的。最终导出文件改名与外挂文件名按 `upload/` 现有打包规则处理；不要重新编码成片。文件名里的 ASCII `/` 换成全角 `／`（`pack_upload.py --print-filename`），平台标题仍用 `plan.md` 原文。打包前 `logs/todo.md` 必须是最终导出和最终 QC 都完成，否则 `pack_upload.py` 会停。`pack_upload.py` 跑完立刻读清单，`pack-upload` 应为带时间的 done。清单不对就停。不要攒到后面再标，也不要拿文件名或 `assets.md` 当进度。

核对：
- `upload/` 已有：标题烧字 `.mp4`、三封面（4:3→3:4→16:9）、`subtitles.srt`（`pack_upload.py` 打好）
- 自动上传走 `/p3-bilibili`、`/p3-youtube`
- `status` 在 **B 站 + YouTube 双链齐**之前仍为 `edited`

**抖音（第三平台，不挡 `published`）**：成片用 `upload/` 里那份；正文从 `plan.md`「抖音」栏抄，话题在发布页点选（≤5）。短链随后写 `episode.md`「抖音：」。

还要短视频才提 `/p3-jianying`。

## 双链齐 → published → 合 PR

触发：用户说「发布完毕 / 发完了 / 已发布」之类，并且同时给了 **B 站 BV（或完整 B 站链接）** 和 **YouTube 链接**。顺序：

1. 写两边链接进 `episode.md`「发布」栏，`status=published`，并 `todo_list.py mark published done`。立刻读 `logs/todo.md`：`published` 应为 done，`cleanup` 仍是 pending。B 站或 YouTube 还没 done 就不要改 `episode.md`。清单不对就停。不要拿文件名或 `assets.md` 当进度。
2. **立刻合并该期 episode PR 进 `main`**（squash；可删远程分支）；不要等用户再点合
3. **出报告并同步复盘日志到 Google Drive**（下一节，必做；不要等清临时确认）：立刻走 `/p3-publish-report` 写 `publish-report.html`，写完后统一跑一次 `sync_retrospect_drive.py` 把 `logs/`、`episode-repo/` 和 `publish-report.html` 一并传到 Google Drive（若暂不出报告则直接同步 `logs/` + `episode-repo/`）
4. 再按下文列清临时清单（体积）→ 用户确认 → 进废纸篓（禁止 `rm`）

抖音短链不挡本步；有了再补写「抖音：」。

合 PR：用本机 `gh pr merge --squash`（用户已登录）。**只自动合 episode 内容 PR**；skill / 工具类 PR 仍等用户合。合完不改清单。合之前 `published` 应已是 done；不是就停。

## 复盘日志上 Google Drive（published 之后必做）

双链和 `published` 写上之后马上做。episode PR 能合就先合完再传；合不了也要传，不要干等。清临时要等用户点头，这一步不要等。只留文本和小文件（绝不传视频、FIT、封面、原片），长期存在用户 Google Drive `running-retrospect/<YYYY-MM-DD-slug>/`，方便跨设备随时复盘。

```bash
.venv/bin/python tools/publish/sync_retrospect_drive.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

目录结构（同名幂等覆盖，并自动刷新根目录 `INDEX.md`）：

| 来源 | 放到（Google Drive `running-retrospect/`） | 说明 |
| --- | --- | --- |
| 媒体 `logs/` 下全部文本/JSON（`timeline.txt`、`todo.md`、`program.json`、`pack-sha256.txt`、`failures.md`、`youtube-upload-result.json` 等） | `<slug>/logs/` | 跳过 `.pid` 与二进制/大文件 |
| 本期 `episode.md`、`plan.md`、`assets.md` | `<slug>/episode-repo/` | 刚写上 `published` 的那份 |
| 媒体 `publish-report.html` | `<slug>/publish-report.html` | 生成报告后再跑一次即同步 |

清临时不要动 `logs/`。本地日志留着，满 7 天随整夹走 `p3-archive`。同步完立刻读 `logs/todo.md`。`published` 不是 done 就不要当这步做完。这一步不改清单步骤，也不要在这里标 `cleanup`。

## 发布后清临时文件

媒体目录：`~/Movies/running-content/YYYY-MM-DD-slug/`。

### 保留（KEEP）

| 保留 | 说明 |
| --- | --- |
| 原片 | `open-raw` / `run-*` / `close-raw`；若没有 `*-raw` 变体，则保留剪过的 `open` / `close` 当作原片 |
| 成片 | **仅一份**：`upload/<标题>.mp4`；根目录不要再留同名成片；勿留 `*-no-burn` / 额外 `run-final` |
| 封面 / 外挂 | `upload/` 内三封面（4:3→3:4→16:9）+ `subtitles.srt`；根目录若仍有同名，须为硬链（同 inode），勿再 copy 一份 |
| 媒体字幕产物 | 上传用 `subtitles.srt`。不要在烧字成片旁边留 `*-run-final.srt` |
| 审片播放清单 | `YYYY-MM-DD-review-preview.edl` 留下 |
| 封面自拍原图 | 媒体目录里的自拍源照片（非 `cover-*.jpg`） |
| 数据 | FIT、`weather-hourly.json`、`stats-*.jpg` |
| `logs/` | 制作日志。已同步到 Google Drive `running-retrospect/`；本地留到满 7 天归档，清临时不删 |
| `publish-report.html` | 发布报告，在素材目录。清临时不删 |

仓库只保留 `subtitles.txt`，清理媒体临时文件时不要改它。跑鞋账本一律不动。

### 删除（DELETE）

缺了就跳过，不要报错停住：

| 删 | 说明 |
| --- | --- |
| `*-no-burn.mp4` | 无字幕备份；**永远不留**。烧字成片定稿/改名后立刻进废纸篓，不必等抖音 |
| 多余 `YYYY-MM-DD-run-final.mp4` | 已有标题烧字成片时的旧名/无字幕备份 |
| `*-run-final-pre-*.mp4` | 拼片备份（冷开场前、修剪前等） |
| `close-stats` 等渲染中间件 | 叠了数据的 close 中间件、其它可再生成的渲染产物 |
| 剪过的 `open` / `close` | **仅当**已有对应 `open-raw` / `close-raw` 时删；没有 `-raw` 则上面 KEEP 已要求保留 |
| `hud-renders/` | HUD preview / 透明层；可再跑 `p3-hud` |
| `asr/` | 转写中间产物 |
| `qc/` | 抽帧核对图 |
| `cover-candidates/` | 封面候选帧 |
| `cold-open/` | 冷开场中间件 |
| `YYYY-MM-DD-review-preview.srt` | 审片清单旁的外挂。用户说留下才留 |
| 其它预览旁路 | 旧的 `*-review-preview.mp4` 等可再生成的预览片。`YYYY-MM-DD-review-preview.edl` 不在此列 |
| `*.bak`、`.DS_Store` | 备份后缀与系统垃圾 |

### 流程（PROCESS）

1. **先列清单再动手。** 用 `du -sh` / `ls -lh` 列出拟删项与拟留项及体积，报给用户确认。`YYYY-MM-DD-review-preview.edl` 放在 KEEP。用户没明确同意前不要删，也不要标 `cleanup` done。列完立刻读 `logs/todo.md`：`published` 应为 done，`cleanup` 仍是 pending。清单不对就停。
2. **进废纸篓，禁止 `rm`。** 在 macOS 上把确认要删的路径 **move 进废纸篓**（`mv … ~/.Trash/`，或已安装的 `trash` CLI）。同名冲突时先改名再移入。
3. 清完把实际移入废纸篓的路径与腾出的体积报给用户。然后 `todo_list.py mark cleanup done`，立刻再读 `logs/todo.md`，`cleanup` 应为带时间的 done。清单不对就停。不要攒到后面再标，也不要拿文件名或 `assets.md` 当进度。
4. 这里**不要**整夹归档或删掉整个媒体目录；满 7 天整夹搬走走 `p3-archive`。

## 记日志

`pack_upload.py` 会写 `pack-upload`，并在 `logs/pack-sha256.txt` 记下成片的 SHA-256。写上 `published` 之前，`logs/todo.md` 里 B 站和 YouTube 都必须是 done，否则不要改 `episode.md`。写的时候用 `.venv/bin/python tools/log_timeline.py --media-dir ~/Movies/running-content/YYYY-MM-DD-slug start published`，再 `end`，并 `todo_list.py mark published done`。`mark published` 之后立刻读清单，`published` 应为 done，`cleanup` 仍是 pending。清单不对就停。不要攒到后面再标，也不要拿文件名或 `assets.md` 当进度。脚本或 helper 已写的行不要重复；失败用 `fail`。复盘同步到 Google Drive 之后也读一遍清单，这一步不改步骤；`published` 不是 done 就不要当复盘做完。

## 完成后

> 双链已写、`published`、episode PR 已 squash 进 main。复盘与发布报告已同步到 Google Drive `running-retrospect/<YYYY-MM-DD-slug>/`（logs / episode-repo / publish-report.html 有或无，如实说；同步失败不要说成已同步）。清临时清单如下，确认后进废纸篓。
>
> （列出 KEEP / DELETE + 体积）
