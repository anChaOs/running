---
name: p3-scaffold
description: 新建一期 episodes/YYYY-MM-DD-slug 和 episode.md。用户说建期、新一期、scaffold、还没有 episode 目录时用。
---

# 建一期目录

## 前置

调度 `p3-episode` 已确认 **日期** 和 **slug**。slug 短英文或拼音，与 `~/Movies/running-content/YYYY-MM-DD-slug/` 对齐。

## 不要做的事

- 已有同日目录就复用，不要平行再建一个
- 不要把大视频拷进仓库
- 不要把未来排期写进 `calendar/` 当拍摄手册

## 步骤

1. 列 `episodes/`，按日期撞车时把现有 `episode.md` 标题给用户看，问是续做还是新 slug。
2. 从 `templates/episode.md` 建 `episodes/YYYY-MM-DD-slug/episode.md`。
3. 需要口播卡再拷 `templates/run-talk-video.md` → `talk.md`；素材索引用 `templates/assets.md`。空壳 `talk.md` 里也加上简介占位：`等字幕完成并校准后再写。不要按本口播卡写。` 不要写简介正文。
4. `status` 先 `planned`；素材进目录后再改 `shot`。
5. 建空的媒体目录（可选）：

```bash
mkdir -p ~/Movies/running-content/YYYY-MM-DD-slug
```

## 完成后

建好目录后立刻推荐下一步。把日期、slug、导出路径换成当前期。

还没拍、只有空目录：停在这里，等素材。

素材已经在磁盘上：

> 下一步用 `/p3-ingest`，可以直接发：
>
> `/p3-ingest 原始文件在 <导出目录路径>`

原始文件已经在 `~/Movies/running-content/YYYY-MM-DD-slug/` 里、只是还没改名，也走 `/p3-ingest`，把该路径当作 `--src`。
