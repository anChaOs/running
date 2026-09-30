# /goal 提示词：跑步视频 HUD v2

持续优化仓库默认 HUD，直到下面「完成标准」全部满足。未全部满足就不要停：改模板 → 渲短样 → 抽帧目视 → 对照清单 → 再改。

## 目标

把 `tools/hud/templates/gopro-dashboard-overlay-running-hud-landscape-map-safe.xml` 做成 1920×1080 边跑边说主模板：

- 不挡路面主体（消失点、下三分之一路面）
- 不挡字幕
- 边距统一、左右对齐
- 有重点（配速），有侧腰（心率/步频/进度/地图）
- 进度条好看、能读出「跑了多少 / 这场多长」

样本一律用：

```text
~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4
~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-data.fit
```

对照旧成片（不要学它的右上角地图）：

```text
~/Movies/running-content/2026-04-27-breaking-2/hud-renders/2026-04-27-run-b-hud.mp4
```

详细设计见 `knowledge/production/HUD-v2-目标.md`。

## 硬约束

- 只改 HUD 视觉：XML 模板，必要时同步 `tools/hud/hud-layout-preview.html` 和 `tools/hud/README.md`。
- 不改 FIT 时间对齐。
- 不给 `open` / `close` 加 HUD。
- 不恢复右上角地图，右上平台水印区必须空。
- 不增加海拔、卡路里、功率。
- 这一轮按 16:9 横屏，不要为 9:16 中裁牺牲横屏布局。
- 渲染命令：`.venv/bin/python tools/hud/render_running_hud.py`

## 网格

- 边距 40px，模块间距 16px。
- 字幕带 `y=920–1080` 全宽留空。
- 水印区右上约 `240×88` 留空。
- 顶栏：`y=40, h=64`，左 40，右缘停在水印左侧；放当前 km + 进度条 + 本场总 km。
- 左侧腰：顶栏下方 `x=40, w=220`，高度随内容。配速最大，其下心率/步频。不要伸进字幕带，不要压在画面下三分之一路面上。
- 右侧腰：顶栏下方、水印下方，宽 220，与左侧腰顶对齐，放地图。
- 鞋名 / 日期 / 时钟：弱信息，塞进顶栏右侧或左模块底部，13–14px，禁止再占 250 空盒。

## 进度条

- 一条胶囊轨道，高 8–10px。
- 填充和轨道对比清楚，有圆点或短滑块。
- 左当前距离、右本场总距离；不要两端再堆一套大数字。
- 总距离继续由脚本从 FIT 写进 `max`。

## 每一轮怎么做

1. 改 XML（需要时改 preview HTML）。
2. 用 2–5 秒短样渲染，不要整段 `run-a`：

```bash
mkdir -p /tmp/hud-v2-sample
ffmpeg -y -ss 00:00:20 -t 3 -i ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-a.mp4 \
  -c copy /tmp/hud-v2-sample/2026-04-23-run-a.mp4
cp ~/Movies/running-content/2026-04-23-first-video/2026-04-23-run-data.fit \
  /tmp/hud-v2-sample/2026-04-23-run-data.fit

.venv/bin/python tools/hud/render_running_hud.py \
  --media-dir /tmp/hud-v2-sample \
  --output-dir /tmp/hud-v2-sample/out \
  --clips 2026-04-23-run-a.mp4
```

短样的 FIT 对齐可能不准，只看布局，不看配速是否等于真实值。

3. 抽 1–2 帧用 Read 看图，不要只看 XML。

```bash
ffmpeg -y -ss 00:00:01 -i /tmp/hud-v2-sample/out/2026-04-23-run-a-hud.mp4 \
  -frames:v 1 /tmp/hud-v2-sample/frame.jpg
```

4. 对照完成标准。任何一条失败：写失败原因，改模板，从第 1 步再来。
5. 全部通过后再在真实 `run-a` 上 `--clips 2026-04-23-run-a.mp4` 渲一版确认（可后台跑）。

## 完成标准（全部必须目视通过）

1. 路面消失点附近没有不透明大块。
2. `y=920–1080` 没有 HUD。
3. 右上水印区没有 HUD、没有 `ROUTE` 字样。
4. 左右模块顶对齐；左右外边距都是 40。
5. 配速是画面里最大的数据；鞋里程明显更弱。
6. 进度条在树荫和亮地面上都能看出填充和当前点。
7. 没有 250×250 空盒。
8. 左下 / 右下不再各占一块压在路上。

## 停下来的条件

只有完成标准 1–8 全部通过才结束。不要用「差不多」「先这样」收工。若 gopro-overlay XML 做不到滑块或某项对齐，在回复里写清限制，并给出最接近的方案，然后继续把能做的做到清单通过。
