# Scripts 使用说明

这个目录的渲染入口是两个脚本。`gopro_dashboard_wrap.py` 和 `weather.py` 是内部依赖，不要直接当 CLI 跑。

如果你先想看 HUD 的作用、布局思路、以及**不依赖本目录自动化脚本**时怎么手动做，请先看：

- `knowledge/production/跑步视频HUD图层制作-概念与非脚本方案.md`

---

## 先准备环境

在跑这两个脚本前，至少先准备好：

- Python 3.10+
- `ffmpeg`
- `.venv` 里的 `gopro-overlay`

最小安装方式：

```bash
python -m venv .venv
./.venv/bin/python -m pip install gopro-overlay
```

macOS 如果后面遇到图形依赖问题，可补：

```bash
brew install cairo pkg-config
```

HUD 全文（中文键、拉丁数字/单位、配速、时长、日期、跑鞋等）使用 **同一偏粗字体族**（贴近旧 Noto Sans Black 运动感，避免扁平 UI 细 Bold）：

- **全平台生产默认：Source Han Sans SC Heavy**（`tools/hud/fonts/SourceHanSansSC-Heavy.otf`，Adobe，≈ Black 字重；Mac / Linux 同一文件，渲染一致）
- 捆绑回退：Noto Sans SC VF wght=900（同目录）
- 系统回退（仅当捆绑缺失）：macOS Hiragino Sans GB W6 / PingFang SC Semibold；Linux Noto Sans CJK SC Bold
- 覆盖：环境变量 `HUD_FONT_PATH` / `HUD_FONT_INDEX` / `HUD_FONT_WGHT`

字色纯白、无描边。`gopro_dashboard_wrap.py` 统一加载（含 TTC index / VF 轴），忽略仅拉丁的 `--font`。

温度单位写 `°` / `°C` 分写，不要写 `℃`（部分字体缺 U+2103 会变成方框）。

## 1. `probe_video_times.py`

用途：

- 读取 MP4 的时间信息
- 帮你判断视频开始时间 / 结束时间
- 给 FIT 对齐提供依据

### 基本用法

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4
```

### 一次检查多个视频

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4 \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-b.mp4 \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-c.mp4
```

### 输出内容

它会给出这些信息：

- 视频时长
- 文件系统创建时间（`stat created`）
- 文件系统修改时间（`stat modified`）
- `ffprobe` 读到的 `creation_time`
- 根据“结束时间 - 视频时长”反推的开始时间

### JSON 输出

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  --json \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4
```

### 时区

默认按 `+08:00` 输出。
如果你要换时区：

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  --timezone +00:00 \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4
```

### 什么时候先跑它

建议在正式渲染 HUD 前先跑一次，确认：

- 这批 MP4 的“结束时间”推断是否合理
- 反推出来的开始时间是否接近你手机原始文件名时间

---

## 2. `render_running_hud.py`

用途：

- 批量给跑步视频生成 HUD
- 自动把 FIT 和 MP4 组合起来
- 自动套用现成模板

默认模板：

```text
tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-safe.xml
```

说明：默认就是**平台安全地图版**，也就是“带地图，但不放右上角”，避免和常见平台右上角水印打架。

非地图版模板：

```text
tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape.xml
```

旧的右上角地图版模板（保留，仅供特殊场景手动使用）：

```text
tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-variant.xml
```

### 最常用的跑法（透明图层，推荐）

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --overlay-only \
  --preview \
  -sn Cumulus \
  -sk 642
```

这条命令会：

- 在 `media-dir` 中寻找 `*-run-data.fit`
- 自动处理 `*-run-*.mp4`（不处理 `open` / `close`）
- 渲透明 HUD 层
- 再按**原片同档**（编码 / 码率 / 分辨率，不降码）叠成可看的预览

```text
hud-renders/YYYY-MM-DD-run-a-hud-alpha.mov      # ProRes 4444 透明层
hud-renders/YYYY-MM-DD-run-a-hud-preview.mp4    # 跟原片同档的审片文件
```

默认编码是 **ProRes 4444**（剪映专业版能认 alpha）。文件会比较大。若体积太大，可改：

```bash
# PNG-in-MOV，透明区域多时通常更小
--overlay-only --overlay-profile png

# QuickTime Animation，体积更小，剪映兼容性不如 ProRes
--overlay-only --overlay-profile qtrle
```

不加 `--overlay-only` 时，仍会把 HUD 直接烤进 `*-hud.mp4`（旧行为）。FIT 对齐逻辑两种模式相同：`--use-fit-only --video-time-end file-modified`。

剪映里怎么叠图层、怎么转场，见 `knowledge/production/剪映剪辑工作流.md`。

### 只处理某一个视频片段

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --clips 2026-04-23-run-a.mp4
```

### 一次处理多个指定片段

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --clips 2026-04-23-run-a.mp4 2026-04-23-run-b.mp4 2026-04-23-run-c.mp4
```

### 指定 FIT 文件

如果素材目录里不止一个 FIT，或者你想强制指定：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --fit ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-data.fit
```

### 天气

生产流程用 `--weather-city shanghai`：只用 FIT 的时间窗，坐标走上海城市场点，**不发送 FIT GPS**。也可以先跑 `tools/hud/weather.py --out weather-hourly.json`，再 `--weather-json`。

仍可用 FIT GPS 拉 [Open-Meteo](https://open-meteo.com/)（气温、体感、相对湿度），写进右下时间区块，不再显示 GPS：

```text
06:06:13
2026-04-23
13°C · 27°C
89%
```

湿度单独最后一行，只有百分号。气温和体感同一行，中间是淡一点的 `·`，没有中文标签。这会把经纬度（四位小数）发给 Open-Meteo 的 archive，失败再走 forecast。

没有 GPS、拉取失败、或加 `--no-weather` 时，整块天气从模板里拿掉，只留时间和日期。已经备好小时数据时用 `--weather-json path.json`。JSON 默认写在素材目录 `weather-hourly.json`。

设计稿在 `tools/hud/hud-layout-preview.html`，改布局先看预览，再改 XML。

### 跑鞋名称 / 跑鞋累计里程

跑鞋在左下配速块下方。可以传两个参数：

- `-sn` / `--shoe-name`：跑鞋名称，默认是 `Secret Shoe`
- `-sk` / `--shoe-total-km-after-run`：这次跑完之后，这双鞋的累计里程（单位 km）；默认等于本次跑步总里程。查账本见 `training/logs/shoes.md`。

开跑前 = `-sk` − **整场** FIT 总距离。当前鞋里程 = 开跑前 + 这一帧的 FIT `distance`。不要用单段视频窗口的最大距离当整场跑量，否则每段都会在片尾顶到 `-sk`。

例子：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  -sn Cumulus \
  -sk 642
```

> 说明：当前这份 FIT 里没有现成的跑鞋累计里程字段，所以如果你不传 `-sk`，脚本会退化为“这双鞋从 0 km 开始，当前累计里程 = 本次跑步里程”。

### 快速启用地图版

如果你只是想切到地图 HUD，不想手写 template 路径，可以直接加：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --map
```

`--map` 现在只是显式表达“我要用默认的安全地图版”；如果你没有传 `--template`，其实默认也是这个模板。若你同时显式传了 `--template`，那就以你显式传入的 template 为准。

### 使用地图 variant

如果你确实需要旧的右上角完整路线图 variant（注意：很多平台右上角会有水印，不推荐作为默认方案）：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --template tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-variant.xml
```

如果要同时显示跑鞋信息：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --template tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-variant.xml \
  -sn Cumulus \
  -sk 642
```

### 先看命令，不实际执行

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --overlay-only \
  --dry-run
```

这个模式很适合先检查：

- 它会处理哪些视频
- 它会输出到哪里
- 它最终调用的 `gopro-dashboard.py` 命令长什么样

### 输出目录自定义

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --output-dir ~/Movies/running-content/2026-04-23-first-video/hud-renders/custom-out
```

### 视频结束时间模式

这个脚本的关键点是：

它会把某个**文件时间**当作**视频结束时间**，再结合视频 `duration` 反推出开始时间，然后再去和 FIT 对齐。

可选值：

- `file-created`
- `file-modified`

默认是：

```bash
--video-end-time-mode file-modified
```

如果你确认这批素材里：

- 文件修改时间更像“视频结束时间”

就可以切换：

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --video-end-time-mode file-created
```

为什么默认改成 `file-modified`：  
在 macOS 上，`gopro-dashboard` 的 `file-created` 实际用的是 `ctime`（inode change time），这经常不是你想要的拍摄结束时间；而对你这批素材，`mtime` 更可靠。

### 完整示例

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --fit ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-data.fit \
  --clips 2026-04-23-run-a.mp4 2026-04-23-run-b.mp4 2026-04-23-run-c.mp4 \
  --video-end-time-mode file-created
```

---

## 推荐使用顺序

最推荐的流程：

### 第一步：先探测时间

```bash
.venv/bin/python tools/hud/probe_video_times.py \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4 \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-b.mp4 \
  ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-c.mp4
```

确认视频时间推断没问题。

### 第二步：先 dry run

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --overlay-only \
  --dry-run
```

确认命令和输出目录没问题。

### 第三步：正式渲染透明图层

```bash
.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir ~/Movies/running-content/2026-04-23-first-video \
  --overlay-only \
  -sn Cumulus \
  -sk 642
```

---

## 前提条件

运行 `render_running_hud.py` 之前，需要这些条件成立：

- 仓库里的 `.venv` 已安装 `gopro-overlay`
- 系统里有 `ffmpeg`
- 模板文件存在：

```text
tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-safe.xml
```

脚本默认还会使用：

- 字体：捆绑 `Source Han Sans SC Heavy`（Mac+Linux 默认）
- 配置目录：`/tmp/gopro-overlay-config`
- 缓存目录：`/tmp/gopro-overlay-cache`

---

## 遇到问题先看哪里

### 1. 时间对不齐
先跑：

```bash
.venv/bin/python tools/hud/probe_video_times.py <你的mp4>
```

检查：

- `ffprobe creation_time`
- `stat created`
- 反推开始时间

### 2. HUD 没生成
先跑：

```bash
.venv/bin/python tools/hud/render_running_hud.py --media-dir <素材目录> --dry-run
```

### 3. 字体报错
如果默认字体不可用，可以改：

```bash
--font tools/hud/fonts/SourceHanSansSC-Heavy.otf   # 默认已是此面；或设 HUD_FONT_PATH
```

### 4. FIT 找不到
显式指定：

```bash
--fit /path/to/your.fit
```

---

## 查看帮助

```bash
.venv/bin/python tools/hud/probe_video_times.py --help
.venv/bin/python tools/hud/render_running_hud.py --help
```
