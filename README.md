# 跑步自媒体内容库

严肃业余跑者冲击全马破三的长期记录：边跑边说口播、训练实验、跑步知识，以及把 FIT 叠进跑中画面的 HUD 工具。

> 一个严肃业余跑者，用训练理论、真实数据和长期实践，记录自己冲击全马破三的过程。

核心不是「我已经很强」，而是「我如何训练、试错、复盘，并把理论翻译成普通跑者能用的方法」。账号主线是破三实验室；自身经历、社会热点、AI、金融投资理财只是口播配菜。

AI 协作规则见 `CLAUDE.md`（`AGENT.md` 是它的软链）。

## 目录

```text
.
├── inbox/                 # 未整理想法
├── calendar/              # 未来排期
├── topics/                # 备选主题库
├── episodes/              # 一期一个文件夹
├── knowledge/wiki/        # 编译知识（先读 wiki/index.md）
├── knowledge/raw/         # 知识来源只读
├── knowledge/production/  # 拍摄 / HUD / 剪映 SOP
├── training/logs/         # 训练记录
├── training/reviews/      # 复盘
├── templates/             # Markdown 模板
└── tools/hud/             # HUD 脚本和 XML
```

大文件在仓库外：`~/Movies/running-content/YYYY-MM-DD-slug/`。

## 一期视频

`episodes/YYYY-MM-DD-slug/` 与本地素材目录同名。常见文件：

- `episode.md`：元数据、status、媒体路径
- `plan.md` / `talk.md` / `script.md` / `assets.md`

status：`idea` → `planned` → `shot` → `hud` → `edited` → `published`。

## 工作流

1. 想法进 `inbox/`。
2. 在 `calendar/` 排未来几天，绑定训练场景。
3. 新建 `episodes/YYYY-MM-DD-slug/`，用 `templates/episode.md`。
4. 当天用 `talk.md` 边跑边说。
5. 素材收进 `~/Movies/running-content/YYYY-MM-DD-slug/`，按 `open` / `run-*` / `close` 命名。
6. 用 `tools/hud/` 给跑中段加 HUD，再进剪映。
7. 有长期价值的写进 `knowledge/`；周期结束做 `training/reviews/`。

## HUD

```bash
.venv/bin/python tools/hud/probe_video_times.py <mp4>
.venv/bin/python tools/hud/render_running_hud.py --media-dir ~/Movies/running-content/YYYY-MM-DD-topic --dry-run
.venv/bin/python tools/hud/render_running_hud.py --media-dir ~/Movies/running-content/YYYY-MM-DD-topic
```

说明在 `tools/hud/README.md`。自动拼接成片以后再做。

## 边跑边说结构

开头 3 秒钩子 → 一句话观点 → 今天的训练场景 → 一个核心解释 → 一个个人体验或数据 → 适用边界 → 结尾互动。一条视频只讲一个观点。
