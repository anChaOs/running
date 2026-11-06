# 成片 skills

文件在 `.claude/skills/<name>/SKILL.md`，目录说明见 `.claude/skills/README.md`。统一前缀 `p3-`（破三实验室），输入 `/p3` 可列出。按需加载，不要一次读完全部。入口是 `p3-episode`（**总序真源**）。用户可以只做到某一步。推荐墙钟：拼时带响度 → 字幕 → 烧字 → 发布；编码成本见 `p3-assemble`。

| skill | 做什么 | 典型输入 | 产物 |
| --- | --- | --- | --- |
| `p3-library` | 备选主题库 | 还没拍摄日的主题 | `topics/<slug>.md` + `topics/index.md` |
| `p3-topic` | 选题对谈 | 有拍摄日、要写成口播 | 一条选题 + 分段口播卡（`talk.md`） |
| `p3-episode` | 盘点、确认、调度 | 手机导出 + 鞋名里程，或「只做 X」 | 下一步 skill 名称 |
| `p3-scaffold` | 建期 | 日期、slug | `episodes/YYYY-MM-DD-slug/` |
| `p3-ingest` | 收素材、命名、校正 mtime | `VID_*.mp4`、FIT | `open/run-*/close`、`assets.md` |
| `p3-shoes` | 算 HUD `-sk` | 鞋名 + 开跑前/跑完后/生涯总里程 | `training/logs/shoes.md` 更新 |
| `p3-hud` | 同档 preview（出完 VAD 句间粗剪）+ 透明层中间件 | 已命名 run + FIT + `-sk` | `hud-renders/` |
| `p3-assemble` | 拼画面 + 抽帧（推荐拼时带响度；总序见 `p3-episode`） | HUD preview | `*-run-final.mp4` + `qc/*.jpg`；`assemble/qc`（+常 `loudness`） |
| `p3-subs` | 字幕：转写→人改→对齐；简介/抖音文案 | 成片 | `subtitles.*`；`subs: done`；`plan.md` |
| `p3-loudness` | 响度补跑（`loudness_only`，`-c:v copy`；拼时已带则跳过） | 未响度成片 | `loudness: done` |
| `p3-burn` | 烧字（`burn_ass`）；改名/`subtitles.srt`/`no-burn` 真源 | `subs`+`loudness` | 烧字片；`burn`/`upload` |
| `p3-publish` | 发布门闩/清临时真源：双链、`published`、合 PR、复盘日志上 box、KEEP/DELETE | 双链或发完了 | `published`；复盘在 box；临时进废纸篓 |
| `p3-bilibili` | 可选：biliup-rs 自动投 B 站（4×3 封面）；独立于 publish | `upload/` + plan 文案 + cookie | BV；只写 B 站链，不改 published |
| `p3-youtube` | 可选：Drive「跑步成片」→ box → YouTube Data API（public）；独立于 publish；默认禁止用户电脑上传 | `upload/` + plan 文案 + box token | youtu.be 链；只写 YT 链，不改 published |
| `p3-cover` | 封面：拍摄单 → 自拍抠图 → 粗描边 → 设计底 → 三比例手排（与 HUD 并行） | 手持自拍 + 封面句 | `cover-*.jpg` |
| `p3-qc` | 只再核对 / 重抽 | 成片 | `qc/*.jpg`；`edited` 由字幕确认后写 |
| `p3-jianying` | 60–90 秒发布剪辑 | 原片 + HUD alpha | 剪映工程 / 发布版 |
| `p3-archive` | 满 7 天素材归档到 Passport | 本地 `YYYY-MM-DD-slug/` | `running-content/YYYYMM/`，核过再删本地 |

每个 skill 做完必须主动推荐下一步，并给出可复制提示词（`/p3-xxx …`）。正文只用占位符，对用户说话时换成当前期真实值。命令和翻车记录写在各自 skill 里，这里不复制。
