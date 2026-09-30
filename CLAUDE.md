# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

这是跑步自媒体内容库，不是普通应用仓库。目标是持续产出高质量「边跑边说」口播视频，而不是跑步鸡汤。`AGENT.md` 是本文件的软链；`AGENTS.md` 只作入口指针。`.omx/` 是旧工具工作记忆，不当作内容源。

## 定位

作者是跑步 3 年多、月跑量 300+、冲击全马破三的严肃业余跑者，把理论和自己的训练实践结合。

> 严肃业余跑者的破三实验室。

内容核心不是「我已经很强」，而是「我如何训练、试错、复盘，并把理论翻译成普通跑者能用的方法」。面向有一定基础、想系统提升成绩的业余跑者。

主线：边跑边说（当天训练当场景，只讲一个观点）；破三训练记录；跑步理论转译；训练实验复盘；比赛和装备实战。

配菜：自身经历、社会热点、AI、金融投资理财。挂在跑步场景里说，不另开杂谈账号。配菜卡放 `topics/`。能沉淀的进 `knowledge/wiki/` 对应种类，日记和过期热点不进 wiki。

## 写作规则

1. 真实、克制、具体；先结论后原因。用数据、训练记录、比赛体验和来源支撑，并区分事实 / 个人体验 / 推测。
2. 口播用短句；一条视频只服务一个核心观点。禁止空泛句和通用营销腔。
3. 不冒充医生、营养师、职业教练或运动科学专家。伤病、康复、医学、补剂要提醒个体差异和专业咨询。
4. 个人经验不写成普适结论；不无依据推荐高风险训练（盲目堆量、长期硬顶、带伤练）。
5. 引用研究、书籍、课程或他人观点时记录来源。修改已有文案时保留作者个人表达。

## 目录

内容进仓库；原始视频、FIT、HUD 成片放 `~/Movies/running-content/YYYY-MM-DD-slug/`，slug 与 `episodes/` 目录名对齐。

| 路径 | 用途 |
|------|------|
| `inbox/` | 连主题都说不清的碎片 |
| `calendar/` | 只放未来排期，不放单期拍摄手册 |
| `topics/` | 备选主题库（`/p3-library`）；有拍摄日再 `/p3-topic` |
| `episodes/YYYY-MM-DD-slug/` | 一期一个文件夹：`episode.md` + plan/talk/script/assets |
| `knowledge/wiki/` | 跑步等编译知识；查询先读 `wiki/index.md` |
| `knowledge/raw/` | 知识来源只读 |
| `knowledge/production/` | 拍摄、命名、HUD、剪映 SOP（人写，先不编进 wiki） |
| `training/logs/` | 训练周期、关键课、比赛；跑鞋累计里程在 `shoes.md` |
| `training/reviews/` | 周 / 月 / 周期 / 账号复盘 |
| `templates/` | Markdown 写作模板 |
| `tools/ingest/` | 手机导出收进素材目录 |
| `tools/hud/` | HUD 时间探测与批量渲染 |
| `tools/assemble/` | 全长成片拼接、封面 |
| `tools/subs/` | txt 收成外挂 SRT |
| `.claude/skills/` | 按需加载；主题库 `p3-library`，选题 `p3-topic`，成片入口 `p3-episode` |

新一期用 `templates/episode.md`。口播可用 `templates/run-talk-video.md`。知识页用 `templates/wiki-page.md`，规则见 `knowledge/CLAUDE.md`。

`episode.md` 的 status：`idea` → `planned` → `shot` → `hud` → `edited` → `published`。

## 工作流

```text
inbox 碎片 / 灵光一闪 → skill `p3-library` 进主题库 → 有拍摄日 skill `p3-topic` 定题和口播卡 → 建 episodes/YYYY-MM-DD-slug/
  → talk.md 口播提纲 → 拍跑前/跑中/跑后/B-roll，拿到当天 FIT
  → 收进 ~/Movies/running-content/YYYY-MM-DD-slug/ 并统一命名
  → 成片走 skill `p3-episode`（按需：ingest / 鞋账本 / HUD / 字幕 / 拼接核对）
  → 或进剪映做 60–90 秒发布剪辑（skill `p3-jianying`）
  → 需要则打磨 script.md → 发布后把 status 改为 published
  → 有长期价值的 ingest 进 knowledge/wiki/，周期结束做 training/reviews
```

出片清单见 `knowledge/production/跑步视频制作工作流.md`。

边跑边说结构：3 秒钩子 → 一句话结论 → 当天训练/数据 → 一个能听懂的解释 → 一个具体方法 → 作者体验和结果 → 适用边界 → 互动或下篇铺垫。

未指定平台时按边跑边说短视频。视频号/抖音 30–90 秒；小红书视频+图文；B 站 5–15 分钟；公众号沉淀系统思考。

默认产出：

- 文案 → 可直接口播拍摄的视频版，写入该期 `talk.md` / `script.md`
- 选题 → 标题、核心观点、适合平台、展开角度、这条不讲什么
- 知识整理 → ingest 进 `knowledge/wiki/`（先读 `wiki/index.md`）
- 复盘 → 训练、身体反馈、内容表现、下一步动作

## HUD 脚本

依赖：Python 3.10+、系统 `ffmpeg`、仓库 `.venv` 里的 `gopro-overlay`。渲染脚本会 `import fitdecode`，必须用 `.venv/bin/python`。macOS 缺图形依赖时：`brew install cairo pkg-config`。

默认模板 `tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-safe.xml`：带地图，不放右上角。无地图版是 `...-landscape.xml`。默认字体 `/System/Library/Fonts/SFCompactRounded.ttf` 的 Black 字重，字色纯白、无描边。温度写 `°C`，不要写 `℃`（字体没有这个字）。右下是运动时长、日期、当天时间、`气温 °C / 体感 °C`、湿度；不再显示 GPS。运动时长用 FIT timer 起停，不含暂停。天气用 `--weather-city shanghai`（FIT 时间窗 + 上海城市场点，不发 GPS）；不需要时加 `--no-weather`。跑鞋 `-sk` 查 `training/logs/shoes.md`。默认把文件 `mtime` 当视频结束时间再对齐 FIT。HUD 优先加在 `run-*`，一般不加 `open`/`close`。生产默认出透明图层 `*-hud-alpha.mov`（`--overlay-only`）。看效果加 `--preview`，按原片同档（编码/码率/分辨率）叠成 `*-hud-preview.mp4`，不降码。不加这些 flag 仍会把 HUD 烤进 mp4。

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/YYYY-MM-DD-topic/YYYY-MM-DD-run-a.mp4

.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-topic \
  --overlay-only \
  --preview \
  --weather-city shanghai \
  --dry-run

.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-topic \
  --overlay-only \
  --preview \
  --weather-city shanghai \
  -sn Cumulus \
  -sk 642
```

细节见 `tools/hud/README.md`。没有测试套件；改脚本后先 `--dry-run`，再用单片段 `--clips` 检查对齐。成片阶段表见 `knowledge/production/成片skills.md`。
