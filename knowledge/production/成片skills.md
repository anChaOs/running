# 成片 skills

文件在 `.claude/skills/<name>/SKILL.md`，目录说明见 `.claude/skills/README.md`。入口是 `p3-episode`，按需加载，不要一次读完全部。

| skill / 工具 | 做什么 | 产物 |
| --- | --- | --- |
| `p3-library` / `p3-topic` | 备选主题、选题与可念口播 | `topics/`、`talk.md` |
| `p3-scaffold` / `p3-ingest` / `p3-shoes` | 建期、收素材、鞋账本 | episode 目录、素材、鞋里程 |
| `p3-hud` | 原始 run 渲 HUD alpha 与审片 preview | `hud-renders/` |
| `p3-assemble` | 把 HUD preview 接成整条审片预览并核对 | `*-review-preview.mp4`、`qc/` |
| `p3-subs` | 转写、人工改字、force_align、质检门 | `subtitles.txt`、外挂 SRT |
| `final_export.py` | 字幕确认后从原片一次叠 HUD/stats、拼接、烧字幕、响度并编码 | `*-run-final.mp4` |
| `p3-publish` | 双链、发布状态、复盘日志、清临时 | `published`、box 复盘 |
| `p3-publish-report` | 复盘拷完后的发布报告 | 单屏 `publish-report.html` |
| `p3-bilibili` / `p3-youtube` | 独立上传拿平台链接 | BV / YouTube URL |
| `p3-cover` / `p3-qc` | 封面、补充核对 | 封面 / QC |
| `p3-jianying` / `p3-archive` | 短视频剪辑、满 7 天归档 | 剪映工程 / Passport |

## 总序

```text
p3-library / p3-topic / p3-scaffold
  → ingest → shoes → hud ∥ cover
  → p3-assemble（review preview，只供人工检查）
  → p3-subs（字幕源稿；人工确认门）
  → final_export.py --confirmed（唯一最终编码：原片 + alpha + stats + 字幕 + 响度）
  → publish
  → p3-publish-report
```

最终导出不读取 HUD preview、review preview 或 close-stats 视频。`assemble_episode.py --ass`、`burn_ass.py`、`loudness_only.py` 是历史旁路，不属于新流程。仓库只跟踪 `subtitles.txt`；SRT/ASS 是生成物。

每步墙钟追加到媒体目录 `logs/timeline.txt`（`p3-scaffold` 建期时建 `logs/`）。官方脚本会写；没写上的步用 `tools/log_timeline.py`。
