# 跑步视频 HUD 图层制作：概念与非脚本方案

> 现状：批量渲染走 `tools/hud/`，默认模板是 `tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-safe.xml`（带地图，放左上，无底框，避开右上角水印）。生产推荐 `--overlay-only` 出 `*-hud-alpha.mov` 透明层，剪映里叠在原片上方；不加该 flag 仍会烤进 mp4。视频结束时间默认按文件 `mtime` 推断。右下时间区块是运动时长、日期、当天时间、`气温 °C / 体感 °C`、湿度，无 GPS；天气来自 Open-Meteo。运动时长用 FIT timer 起停，不含暂停。字体是 SF Compact Rounded Black，纯白、无描边；温度写 `°C`，不要写 `℃`。下文「明确不做地图」和部分 `file-created` 示例是早期 v1 手写边界，不要当成当前默认。

这篇文档只解决两件事：

1. 跑步视频 HUD 图层到底要解决什么问题
2. 如果**不走 `tools/hud/` 自动化脚本**，手动做一版 HUD，应该怎么做

如果你想直接用现成脚本批量出 HUD，请看：

- `tools/hud/README.md`

---

## 1. HUD 在跑步视频里到底是干嘛的

HUD 不是为了“炫”。

对于你这种边跑边说、训练记录型内容，HUD 的核心作用只有三个：

- **数据可信感**：让观众知道这不是空口讲训练
- **训练背景**：让视频里的状态有上下文
- **节奏补充**：让画面在口播之外还有信息层

HUD 不应该做的事：

- 抢走口播主体
- 把视频做成赛车仪表盘
- 一次塞进太多指标
- 用花哨动画把可读性打碎

---

## 2. 这次第一版 HUD 的设计边界

当前已经定下来的 v1 边界是：

### 保留的 5 个信息位

1. 左下竖排：`PACE`
2. 左下竖排：`HR`
3. 左下竖排：`CADENCE`
4. 顶部居中：`DISTANCE`
5. 右下角：`TIME`

### 平台水印安全区提醒

如果后续真的要加地图 / 轨迹小窗，**不要默认放右上角**。

原因很简单：

- 很多短视频平台右上角会有平台水印或平台 UI
- 右侧中上区域也常常是信息最容易打架的位置

更稳的策略是：

- **默认模板可以带地图，但地图不要放右上角**
- 真要用地图，优先放**左上安全区**或别的非平台高风险区域
- 把右上角地图 variant 当成特殊场景，而不是默认方案

### 明确不做的东西

- 不做地图 / 轨迹小窗
- 不做额外指标扩张（海拔、卡路里、步幅、功率等）
- 不做重装饰面板
- 不做复杂动画
- 不强行兼容竖屏裁切

### 取舍原则

如果画面略挤：

> 优先保住 5 个核心信息位的完整表达，而不是为了“极简感”继续删字段。

---

## 3. 为什么当前主推 `gopro-dashboard-overlay`

当前主路线是：

> 横屏原视频 + FIT 文件 + `gopro-dashboard-overlay`

选择它，不是因为它最花哨，而是因为它适合你现在的生产方式：

- 免费开源
- CLI 友好
- 支持 XML 布局
- 支持 GPX/FIT
- 适合以后固定成稳定流程

备选方案仍然可以知道，但不是主路线：

1. `GPStitch`：图形界面调样式方便，但不适合作为你的长期主流程
2. `GPSBabel`：只做 FIT → GPX 转换备用，不是 HUD 主工具

---

## 4. 当前素材怎么理解

当前素材目录：

```text
~/Movies/running-content/2026-04-23-first-video/
```

主要文件：

```text
2026-04-23-open.mp4
2026-04-23-run-a.mp4
2026-04-23-run-b.mp4
2026-04-23-run-c.mp4
2026-04-23-close.mp4
2026-04-23-run-data.fit
```

更适合做动态 HUD 的，是这三段：

```text
2026-04-23-run-a.mp4
2026-04-23-run-b.mp4
2026-04-23-run-c.mp4
```

不建议一开始就给这两段做动态 HUD：

```text
2026-04-23-open.mp4
2026-04-23-close.mp4
```

因为它们更适合静态信息条，不一定精确落在跑步数据时间线上。

---

## 5. 当前推荐的横屏布局

```text
┌──────────────────────────────────────────────────────────┐
│ 路线(无框)              2.48 km  ══●════  12.05 km        │
│                                                          │
│                                                          │
│                                                          │
│ 6′15″                                                    │
│ 158 bpm                                    06:06:13      │
│ 172 spm                                    2026-04-23    │
│ Cumulus  642 km                            13°C / 11°C   │
│                                            89%           │
└──────────────────────────────────────────────────────────┘
```

### 视觉原则

- 字体：SF Compact Rounded Black，纯白、无描边
- 颜色：白字 + 半透明褐土底
- 面板：克制，不做电竞风，模块不要描边框
- 字幕：和 HUD 分层，不要互相打架
- 温度：`°C`，不要 `℃`

---

## 6. 不用 `tools/hud/` 自动化时，手动怎么做

这里说的“非脚本化”，不是不用 CLI，
而是：**不用仓库里那两个自动化脚本**，自己手动执行步骤。

### 第一步：先确认环境

至少要有：

- Python 3.10+
- `ffmpeg`
- `gopro-overlay`

安装示例：

```bash
python -m venv .venv
.venv/bin/pip install gopro-overlay
```

macOS 里如果需要额外图形依赖：

```bash
brew install cairo pkg-config
```

如果默认字体报错，可显式指定：

```bash
--font /System/Library/Fonts/Supplemental/Arial.ttf
```

---

### 第二步：先确认 CLI 能力

```bash
.venv/bin/gopro-dashboard.py --help
.venv/bin/gopro-dashboard.py --help | grep -i fit
```

当前我本地实测的 `gopro-overlay 0.128.0`，关键参数包括：

- `--gpx/--fit`
- `--layout xml`
- `--layout-xml`
- `--units-distance`
- `--use-gpx-only/--use-fit-only`
- `--video-time-start`
- `--video-time-end`

---

### 第三步：准备 layout XML

当前现成模板已经在仓库里：

```text
tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape.xml
```

如果你手动跑，也可以直接用这个模板，不一定非要自己重新写。

---

### 第四步：先做一个最小样例

先只拿一个片段测试，比如：

```text
2026-04-23-run-a.mp4
```

目标不是马上出成片，而是先验证：

1. FIT 能读进去
2. 时间线能对齐
3. 5 个信息位能正常显示
4. HUD 不挡主体画面

---

### 第五步：手动跑一条命令

如果你的视频不是 GoPro 原生带 metadata 的视频，而是手机视频，当前更实用的方式是：

- 用 FIT 作为数据源
- 用视频文件时间来锚定 FIT 时间线

手动命令形态大致是：

```bash
.venv/bin/gopro-dashboard.py \
  2026-04-23-run-a.mp4 \
  hud-work/out/2026-04-23-run-a-hud.mp4 \
  --font /System/Library/Fonts/Supplemental/Arial.ttf \
  --gpx 2026-04-23-run-data.fit \
  --use-fit-only \
  --video-time-end file-created \
  --layout xml \
  --layout-xml tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape.xml \
  --units-distance km
```

> 注：这里的 `file-created` 是否合适，要看你这批素材的文件时间语义。

---

## 7. 视频时间怎么理解

对你这批手机视频，当前更合理的理解是：

- 手机原始文件名时间：更像**开始录制时间**
- MP4 容器里的 `creation_time`：更像**录制结束 / 文件写完时间**

所以做手动对齐时，可以这样思考：

### 方法 A：最稳
直接保留原始文件名时间，按文件名做开始时间参考。

### 方法 B：次优
如果文件已重命名，就用：

```text
结束时间 - 视频时长 = 推定开始时间
```

### 方法 C：最后再人工微调
如果某段口播、动作、路口位置对不上，再做少量偏移修正。

---

## 8. 非脚本化方案最容易踩的坑

### 1. 一上来就全量渲染
先做 1 个片段测试，不要一口气把全部视频都跑掉。

### 2. 时间没确认就直接渲染
先确认视频时间语义，否则 HUD 数值会“看着合理，但其实是错位的”。

### 3. 指标加太多
第一版真的没必要加地图、海拔、功率、步幅。

### 4. 让 HUD 压住字幕或人脸
HUD 不是主角，口播还是主角。

---

## 9. 如果你不想手动拼命令
那就不要继续用这篇。

直接看：

- `tools/hud/README.md`

那篇专门讲：

- 环境准备
- 依赖准备
- 脚本怎么跑
- 批量渲染怎么做
- dry run 怎么看
