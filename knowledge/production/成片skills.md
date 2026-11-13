# 成片 skills

文件在 `.claude/skills/<name>/SKILL.md`，目录说明见 `.claude/skills/README.md`。入口是 `p3-episode`，按需加载，不要一次读完全部。

| skill / 工具 | 做什么 | 产物 |
| --- | --- | --- |
| `p3-library` / `p3-topic` | 备选主题、选题与可念口播 | `topics/`、`talk.md` |
| `p3-scaffold` / `p3-ingest` / `p3-shoes` | 建期、收素材、鞋账本 | episode 目录、素材、鞋里程 |
| `p3-hud` | 先把鞋、天气、透明层规格记进时间表；冻结后按入出点直接画透明层 | `logs/program.json` 的 `hud`，`hud-renders/<profile>/*-hud-alpha.mov` |
| `p3-assemble` | 按时间表写审片播放清单并核对 | `*-review-preview.edl` |
| `p3-subs` | 转写、人工改字、force_align、质检门；对口型前冻结时间表。校对可与准备并行 | `subtitles.txt`、外挂 SRT |
| `final_export.py` | 确认后按同一张表裁原片、叠已画好的 HUD、xfade、跑步段风刮和 whoosh、叠贴图、烧字幕、套用已测响度，一次编码。缺准备会先补 | `*-run-final.mp4` |
| `p3-publish` | 双链、发布状态、复盘日志、清临时 | `published`、box 复盘 |
| `p3-publish-report` | 复盘拷完后的发布报告 | 单屏 `publish-report.html` |
| `p3-bilibili` / `p3-youtube` | 独立上传拿平台链接 | BV / YouTube URL |
| `p3-cover` / `p3-qc` | 封面、补充核对 | 封面 / QC |
| `p3-jianying` / `p3-archive` | 短视频剪辑、满 7 天归档 | 剪映工程 / Passport |

## 总序

```text
p3-library / p3-topic / p3-scaffold
  → ingest（锁原片↔FIT，句间刀只记表）→ shoes → hud 记录 ∥ cover
  → 冷开场 / 贴图 / 插入入表
  → p3-assemble（按表出低成本预览）
  → p3-subs（对口型前冻结时间表）
  → 冻结后：用户校对字幕 ∥ `--prep-alpha`（8 核 `-j 6`，默认 2）∥ 可选 `--measure-only`
  → 确认字幕
  → final_export.py --confirmed（同一张表，一次编码）
  → publish
  → p3-publish-report
```

最终导出不读取 HUD preview、review preview 或 close-stats 视频。`assemble_episode.py --ass`、`burn_ass.py`、`loudness_only.py` 是历史旁路，不属于新流程。仓库只跟踪 `subtitles.txt`；SRT/ASS 是生成物。

时间表是媒体目录 `logs/program.json`。进度清单是 `logs/todo.md`，和 `logs/timeline.txt` 一起写到发布完成。操作以 `p3-episode` 为准。
