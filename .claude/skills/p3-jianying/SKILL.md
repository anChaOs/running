---
name: p3-jianying
description: 60–90 秒发布剪辑走剪映，不走全长成片脚本。用户说剪映、短视频发布、60秒、90秒时用。
---

# 剪映短视频

全长成片是 `p3-assemble`。视频号/抖音 30–90 秒、小红书视频仍用剪映。操作细节：`knowledge/production/剪映剪辑工作流.md`。

## 前置

- 原片：`open` / `run-*` / `close`
- HUD 透明层：`hud-renders/*-hud-alpha.mov`（不要用 preview 再叠一层）
- 可选：`episodes/.../subtitles.srt` 当听写底稿，剪映里会重切时长

## 注意

- HUD 渲染是 1920×1080 横屏；教程按 9:16 写，进剪映前决定裁切
- 只给 `run-*` 叠 HUD
- 一条视频一个观点，先排主线再删废话
- 字幕不要压 HUD 底栏（`MarginV` 思路和全长成片一样）

出片后把发布记录写进该期 `episode.md`，`status` 可改为 `published`。

## 完成后

剪映导出完成后立刻说明：短视频没有下一个制作 skill。

> 可以发视频号 / 抖音 / 小红书。发布后把链接发我，我写进 `episode.md`。
>
> 全长成片如果还没做：
>
> `/p3-assemble`
>
> 全长已经 QC 过、只差上传：停在这里，按 `/p3-qc` 结束时的发布清单挂外挂字幕。
