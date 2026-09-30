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
| `p3-hud` | 同档 preview（出完 VAD 句间粗剪）+ 透明层中间件，并行出封面 | 已命名 run + FIT + `-sk` | `hud-renders/` + `cover-*.jpg` |
| `p3-subs` | whisper + 忠于原句 SRT（只纠错、删显著卡顿；外挂） | 分段音频 | `subtitles.srt` / `.txt` |
| `p3-cover` | 只换封面 / 重抽 | `run-a` + 封面句 | `cover-*.jpg` |
| `p3-assemble` | 叠化拼接（默认不烧字幕）+ 立刻抽帧核对 | HUD preview | `*-run-final.mp4` + 外挂 SRT + `qc/*.jpg` |
| `p3-qc` | 只再核对 / 重抽 | 成片 | `qc/*.jpg`，status=edited |
| `p3-jianying` | 60–90 秒发布剪辑 | 原片 + HUD alpha | 剪映工程 / 发布版 |

每个 skill 做完必须主动推荐下一步，并给出可复制提示词（`/p3-xxx …`）。正文只用占位符，对用户说话时换成当前期真实值。命令和翻车记录写在各自 skill 里，这里不复制。
