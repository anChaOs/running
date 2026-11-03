---
name: p3-publish
description: 发布收尾：用户给齐 B 站 + YouTube 链接后写 episode 发布栏、status=published、该期 episode PR squash 合 main；再列清临时 KEEP/DELETE（体积）→ 人确认 → 进废纸篓。抖音短链不挡 published，随后写入。用户说发布完毕、发完了、已发布、写链接、合 episode PR、清临时时用。不要替用户上传。上传清单与改名见 p3-burn；字幕定稿见 p3-subs；满 7 天整夹归档见 p3-archive。
---

# 发布

烧字 / upload-ready 之后的收尾：**写双链 → `published` → squash 合本期 episode PR → 清临时**。不要替用户上传成片。

```text
总序：… → 烧字 p3-burn → 发布 本 skill（双链齐）→ 清临时
```

## 职责 / 输入 / 输出

| | |
| --- | --- |
| **职责** | 上传清单提示（用户说可以发了）；写 B 站 / YouTube / 抖音链接；`status=published`；自动 squash merge 本期 episode PR；发布后清临时（KEEP/DELETE 真源） |
| **输入** | 用户已上传（或说发完了）+ **B 站 BV/链接** + **YouTube 链接**；媒体目录成片与 sidecar |
| **输出** | `episode.md` 发布栏与 `published`；PR 合进 `main`；确认后临时文件进废纸篓 |
| **不负责** | 替用户上传；烧字/改名（`p3-burn`）；字幕对齐（`p3-subs`）；整夹归档（`p3-archive`） |

**真源：** 清临时 KEEP/DELETE 只写在本 skill。其它 skill / 文档只引用这里，不要另写一份清单。

## 不要做的事

- 不要在缺 B 站或 YouTube 任一链接时写 `published` 或合 PR
- 不要用抖音是否已发来挡 `published`（抖音短链随后补）
- 不要替用户上传；不要在用户确认前删任何临时文件
- 清临时禁止 `rm` / `rm -rf`；只进废纸篓
- 不要整夹删媒体目录；满 7 天搬盘走 `p3-archive`

## 前置

通常已走完 `/p3-burn`（烧字最终片；可选 upload-ready 改名）。用户说「没问题了 / 可以发了」时可先给上传清单；真正写链接与清临时要等双链到手。

## 上传清单（用户说可以发了时给；不要替传）

从 `plan.md` 抄标题、封面句、简介。成片改名规则见 `p3-burn`「发布前改名」。

1. 上传成片（标题名烧字 `.mp4`）→ 换封面 → 挂 `subtitles.srt`（B 站创作中心只收 SRT）→ 先不公开、开 CC → 再公开。
2. `episode.md` 的 `status` 在真正发完、**两边链接齐了**之前仍为 `edited`。

| 用途 | 文件 |
| --- | --- |
| 成片（上传用 = 生产成片） | 媒体目录里以标题命名的 `.mp4`（由 `YYYY-MM-DD-run-final.mp4` 原地改名） |
| 封面 | `cover-1920x1080.jpg` / `cover-4x3-1920x1440.jpg` / `cover-1080x1440.jpg` / `cover.jpg` |
| 外挂 | **`subtitles.srt`**（不要改成标题名；制作阶段可选保留 `YYYY-MM-DD-run-final.srt`） |

**抖音（第三平台，不挡 `published`）**

- 成片：用**已烧字幕**的标题名 `.mp4`（`p3-burn` 产出；抖音不依赖外挂 SRT）。
- 文案：从 `plan.md`「抖音」栏抄正文，再按「建议话题」清单（≤5）在发布页点选变蓝；封面可用 `cover-1080x1440.jpg` 或平台裁切。
- 发完后把分享短链（`https://v.douyin.com/…`）写入 `episode.md`「发布」栏「抖音：」。
- **成片只留一份**：媒体目录只保留标题名烧字幕 `.mp4`。`*-no-burn` 见 `p3-burn`（烧字定稿后立刻进废纸篓，不必等抖音）。

还要 60–90 秒短视频才提 `/p3-jianying`。简介 / 抖音文案正文怎么写见 `p3-subs`（字幕定稿后写入 `plan.md`）。

## 双链齐 → published → 合 PR

触发：用户说「发布完毕 / 发完了 / 已发布」之类，并且同时给了 **B 站 BV（或完整 B 站链接）** 和 **YouTube 链接**。顺序：

1. 写两边链接进 `episode.md`「发布」栏，`status=published`
2. **立刻合并该期 episode PR 进 `main`**（squash；可删远程分支）；不要等用户再点合
3. 再按下文列清临时清单（体积）→ 用户确认 → 进废纸篓（禁止 `rm`）

抖音短链不挡本步；有了再补写「抖音：」。

合 PR：Cursor GitHub 插件若 403，改用本机 `gh pr merge --squash`（用户已登录）。**只自动合 episode 内容 PR**；skill / 工具类 PR 仍等用户合。

## 发布后清临时文件

媒体目录：`~/Movies/running-content/YYYY-MM-DD-slug/`。

### 保留（KEEP）

| 保留 | 说明 |
| --- | --- |
| 原片 | `open-raw` / `run-*` / `close-raw`；若没有 `*-raw` 变体，则保留剪过的 `open` / `close` 当作原片 |
| 成片 | **仅一份**：以标题命名的最终烧字幕 `.mp4`；勿留 `*-no-burn` / 额外 `run-final`（烧字定稿后即可扔，不等抖音） |
| 字幕 | `subtitles.srt`（制作期可选的 `YYYY-MM-DD-run-final.srt` 可留）；烧字源 `subtitles.ass` 可留 |
| 封面 | `cover.jpg`、`cover-1920x1080.jpg`、`cover-4x3-1920x1440.jpg`、`cover-1080x1440.jpg` |
| 封面自拍原图 | 媒体目录里的自拍源照片（非 `cover-*.jpg`） |
| 数据 | FIT、`weather-hourly.json`、`stats-*.jpg` |

仓库 `episodes/` 里的字幕源稿、跑鞋账本一律不动。

### 删除（DELETE）

缺了就跳过，不要报错停住：

| 删 | 说明 |
| --- | --- |
| `*-no-burn.mp4` | 无字幕备份；**永远不留**。烧字成片定稿/改名后立刻进废纸篓，不必等抖音 |
| 多余 `YYYY-MM-DD-run-final.mp4` | 已有标题烧字成片时的旧名/无字幕备份；一并进废纸篓 |
| `*-run-final-pre-*.mp4` | 拼片备份（冷开场前、修剪前等）；发布后不再需要回退 |
| `close-stats` 等渲染中间件 | 叠了数据的 close 中间件、其它可再生成的渲染产物 |
| 剪过的 `open` / `close` | **仅当**已有对应 `open-raw` / `close-raw` 时删；没有 `-raw` 则上面 KEEP 已要求保留 |
| `hud-renders/` | HUD preview / 透明层；可再跑 `p3-hud` |
| `asr/` | 转写中间产物 |
| `qc/` | 抽帧核对图 |
| `cover-candidates/` | 封面候选帧 |
| `cold-open/` | 冷开场中间件 |
| `*.bak`、`.DS_Store` | 备份后缀与系统垃圾 |

### 流程（PROCESS）

1. **先列清单再动手。** 用 `du -sh` / `ls -lh` 列出拟删项与拟留项及体积，报给用户确认。用户没明确同意前不要删。
2. **进废纸篓，禁止 `rm`。** 在 macOS 上把确认要删的路径 **move 进废纸篓**（`mv … ~/.Trash/`，或已安装的 `trash` CLI）。不要用 `rm` / `rm -rf`。同名冲突时先改名再移入。
3. 清完把实际移入废纸篓的路径与腾出的体积报给用户。
4. 这里**不要**整夹归档或删掉整个媒体目录；满 7 天整夹搬走走 `p3-archive`。

## 完成后

> 双链已写、`published`、episode PR 已 squash 进 main。清临时清单如下，确认后进废纸篓。
>
> （列出 KEEP / DELETE + 体积）
