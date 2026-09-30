---
name: p3-cover
description: 只换封面或重抽封面。默认成片流程里封面已在 p3-hud 里和 HUD 并行做完。用户说换封面句、封面糊、重做封面时用。
---

# 封面（补做 / 重做）

默认流程：封面跟 HUD 一起在 `p3-hud` 里做。本 skill 只在要换句、换帧、或不走全长成片时用。

## 前置

- 片源：通常原片 `YYYY-MM-DD-run-a.mp4`（不要用成片，也不要用 HUD preview）
- 标题：该期封面句；默认系列名「破三实验室」
- 抽帧秒数：**清晰是硬条件。** 近处树叶、树皮、路沿要能看出纹理。运动模糊、远景发虚的帧直接丢掉，即使路上没人也不用。
- 同时避开行人特写、过曝、低头看表。先抽 2–3 个**清楚的**候选给用户看，不要先定空路再将就糊的。

## 不要做的事

- 不要用 HUD preview 当底图，数据条会进封面
- 不要在封面堆第二句鸡汤
- 不要为了空路、构图好看而用糊帧
- 不要为了换封面去重渲 HUD

## 步骤

```bash
.venv/bin/python tools/assemble/make_cover.py \
  --src ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-a.mp4 \
  --title "封面句" \
  --sub "破三实验室" \
  --ss 40 \
  --out-dir ~/Movies/running-content/YYYY-MM-DD-slug
```

产出：

```text
cover-1920x1080.jpg   # 视频号 / B 站
cover-1080x1440.jpg   # 小红书 3:4
cover-frame.jpg       # 未叠字的抽帧
```

`assets.md` 制作状态 `cover: done`。

## 完成后

用户只是要换封面句：停在这里，不用重拼成片。

还缺字幕：

> `/p3-subs`

HUD 和字幕都齐了：

> `/p3-assemble`
