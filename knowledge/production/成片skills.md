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
| `p3-assemble` | 拼画面：叠化/whoosh 拼接 + 立刻抽帧核对（默认不响度、不烧字） | HUD preview | `*-run-final.mp4` + `qc/*.jpg`；`assemble/qc: done` |
| `p3-subs` | 字幕支路：词级转写 + 忠于原句 SRT；人改后 force_align / check_subs；简介与清临时真源；可与响度并行 | 可对字幕成片 | `subtitles.srt` / `.txt`；`subs: done` |
| `p3-loudness` | 响度支路：assemble 脚本默认响度链；可与字幕并行；烧字前须就绪 | 已拼成片 | 响度版成片；`loudness: done` |
| `p3-burn` | 烧字收尾：ASS + `--ass`；清 no-burn；upload-ready 改名 | `subs: done` + `loudness: done` | 烧字最终片；`burn: done` / `upload: ready` |
| `p3-cover` | 封面：拍摄单 → 自拍抠图 → 粗描边 → 设计底 → 三比例手排（与 HUD 并行） | 手持自拍 + 封面句 | `cover-*.jpg` |
| `p3-qc` | 只再核对 / 重抽 | 成片 | `qc/*.jpg`；`edited` 由字幕确认后写 |
| `p3-jianying` | 60–90 秒发布剪辑 | 原片 + HUD alpha | 剪映工程 / 发布版 |
| `p3-archive` | 满 7 天素材归档到 Passport | 本地 `YYYY-MM-DD-slug/` | `running-content/YYYYMM/`，核过再删本地 |

每个 skill 做完必须主动推荐下一步，并给出可复制提示词（`/p3-xxx …`）。正文只用占位符，对用户说话时换成当前期真实值。命令和翻车记录写在各自 skill 里，这里不复制。
