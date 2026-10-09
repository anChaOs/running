# 成片 skills

本仓的 Claude Code skill。统一前缀 **`p3-`**（破三实验室）。输入 `/p3` 就能列出这一族。

每个子目录一个阶段，入口文件是 `SKILL.md`（YAML `name` / `description` + 正文）。Claude 按 `description` **按需加载**，不要一次读完全部。

命令和翻车记录写在各自 `SKILL.md` 里。总表也在 `knowledge/production/成片skills.md`。

## 两条总规则

1. **通用，不绑某一期。** 正文只用 `YYYY-MM-DD` / `slug` / `<HUD 名>` / `<跑完后累计 km>` 这种占位。不要把上一期的日期、`-sk`、封面句、BV 号写进 skill。某一期遇到的问题，提炼成通用规则再写，不要把那一期的情节、原话当规则或例子。对用户说话时，把占位符换成**当前这一期**的真实值。
2. **做完必须推荐下一步。** 每个 skill 工作结束、状态写入 `assets.md` 之后，立刻告诉用户：产物路径、下一个 `/p3-xxx`、一条可复制的提示词。不要等他们问「下一步是什么」。可以停或可并行时各写一句。

提示词发给用户时填好当前期，不要把 `YYYY-MM-DD-slug` 原样丢回去。

## 入口

还没拍摄日的主题，走 **`/p3-library`**。拍之前要定题、写成口播，走 **`/p3-topic`**。

用户丢来未重命名的手机导出 + 跑鞋名和里程，或说「做视频 / 成片 / 只做某一步」时，先走 **`/p3-episode`**。它盘点已有产物、确认今天停在哪，再给出下一步的提示词。

也可以直接点名某个阶段，例如 `/p3-hud`、`/p3-subs`、`/p3-cover`。

## 目录

```text
.claude/skills/
  README.md
  p3-library      备选主题库（还没拍摄日）
  p3-topic        选题对谈 → 选题 + 分段口播卡
  p3-episode      成片调度
  p3-scaffold     建 episodes/YYYY-MM-DD-slug
  p3-ingest       VID_ / FIT → open/run-*/close
  p3-shoes        training/logs/shoes.md，算出 -sk
  p3-hud          overlay + 同档 preview，并行封面
  p3-subs         whisper large-v3-turbo + 忠于原句 SRT（外挂）
  p3-cover        只换封面 / 重抽
  p3-assemble     叠化拼接（默认不烧字幕）+ 抽帧核对
  p3-qc           只再核对；默认已在 assemble 里做过
  p3-jianying     60–90 秒剪映，不走全长脚本
```

## 产物顺序

```text
灵光一闪 / 还没拍摄日
  → p3-library      topics/<slug>.md
想法 / 一次训练（当天要拍）
  → p3-topic        选题 + 分段口播卡
  → p3-scaffold     episodes/YYYY-MM-DD-slug/

手机导出 + FIT
  → p3-ingest       ~/Movies/running-content/YYYY-MM-DD-slug/
  → p3-shoes        -sn / -sk（跑完后累计 km）
  → p3-hud          hud-renders/*-hud-preview.mp4 + cover-*.jpg
  → p3-subs         subtitles.srt / txt，停下来手改后再拼
  → p3-assemble     YYYY-MM-DD-run-final.mp4（不烧字幕）+ 抽帧核对，status=edited
```

任意一步都可以停。改字幕只改 sidecar，不用重拼。改 `-sk` 要重渲 HUD 再拼。
