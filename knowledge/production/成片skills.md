# 成片 skills

文件在 `.claude/skills/<name>/SKILL.md`，目录说明见 `.claude/skills/README.md`。统一前缀 `p3-`（破三实验室），输入 `/p3` 可列出。按需加载，不要一次读完全部。入口是 `p3-episode`。用户可以只做到某一步。

| skill | 做什么 | 典型输入 | 产物 |
| --- | --- | --- | --- |
| `p3-library` | 备选主题库 | 还没拍摄日的主题 | `topics/<slug>.md` + `topics/index.md` |
| `p3-topic` | 选题对谈 | 有拍摄日、要写成口播 | 一条选题 + 分段口播卡（`talk.md`） |
| `p3-episode` | 盘点、确认、调度 | 手机导出 + 鞋名里程，或「只做 X」 | 下一步 skill 名称 |
| `p3-scaffold` | 建期 | 日期、slug | `episodes/YYYY-MM-DD-slug/` |
| `p3-ingest` | 收素材、命名、校正 mtime | `VID_*.mp4`、FIT | `open/run-*/close`、`assets.md` |
| `p3-shoes` | 算 HUD `-sk` | 鞋名 + 开跑前/跑完后/生涯总里程 | `training/logs/shoes.md` 更新 |
| `p3-hud` | 同档 preview（出完 VAD 句间粗剪）+ 透明层中间件 | 已命名 run + FIT + `-sk` | `hud-renders/` |
| `p3-subs` | 词级转写 + 忠于原句 SRT（只纠错、删显著卡顿）；校对期外挂；定稿后 ASS 烧进最终片；改字后强制对齐，质检门按比例过门；发布完毕记链接后清临时文件（真源见该 skill「发布后清临时文件」） | 成片音频 | `subtitles.srt` / `.txt` / `.ass`；发布后按 KEEP/DELETE 清单清理（确认后进废纸篓） |
| `p3-cover` | 封面：拍摄单 → 自拍抠图 → 粗描边 → 设计底 → 三比例手排（与 HUD 并行） | 手持自拍 + 封面句 | `cover-*.jpg` |
| `p3-assemble` | 叠化拼接（最终片默认烧 ASS，从 2026-10-29 起）+ 立刻抽帧核对 | HUD preview + 可选 `--ass` | `*-run-final.mp4` + `qc/*.jpg` |
| `p3-qc` | 只再核对 / 重抽 | 成片 | `qc/*.jpg`；有校准字幕才 `edited` |
| `p3-jianying` | 60–90 秒发布剪辑 | 原片 + HUD alpha | 剪映工程 / 发布版 |
| `p3-archive` | 满 7 天素材归档到 Passport | 本地 `YYYY-MM-DD-slug/` | `running-content/YYYYMM/`，核过再删本地 |

每个 skill 做完必须主动推荐下一步，并给出可复制提示词（`/p3-xxx …`）。正文只用占位符，对用户说话时换成当前期真实值。命令和翻车记录写在各自 skill 里，这里不复制。
