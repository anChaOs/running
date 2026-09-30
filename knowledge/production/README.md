# knowledge/production

出片 SOP，不是跑步理论。

| 文档 | 说明 |
|------|------|
| `成片skills.md` | 按需加载的 skill 表；入口 `p3-episode` |
| `跑步视频制作工作流.md` | 选题到导出的清单 |
| `素材与命名.md` | 仓库外目录和 `open/run-*/close` 约定 |
| `跑步视频HUD图层制作-概念与非脚本方案.md` | HUD 为什么存在；手动方案。**当前默认已是带地图的 map-safe 模板，时间模式是 `file-modified`，右下是时间/天气不是 GPS**，文中「不做地图 / file-created」是早期 v1 手写边界 |
| `剪映剪辑工作流.md` | 剪映从零操作。教程按 9:16 竖屏写；HUD 渲染是 1920×1080 横屏，进剪映前自行决定裁切 |

自动化渲染看 `tools/hud/`。收素材看 `tools/ingest/`。全长成片看 `tools/assemble/`。命令写在对应 skill 里，不要在这里复制。
