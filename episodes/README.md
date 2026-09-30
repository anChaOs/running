# episodes

一期跑步视频一个文件夹。目录名与本地素材目录对齐：`YYYY-MM-DD-slug`。

成片按需走 `.claude/skills/`，入口 `p3-episode`。每期至少有 `episode.md`。有则再放：

| 文件 | 来源 |
|------|------|
| `plan.md` | 单期拍摄 / 发布计划 |
| `talk.md` | 当天边跑边说提纲 |
| `script.md` | 完整脚本、标题、字幕 |
| `assets.md` | 素材索引，指向仓库外大文件 |

`episode.md` 的 `status`：`idea` → `planned` → `shot` → `hud` → `edited` → `published`。

大文件在 `~/Movies/running-content/YYYY-MM-DD-slug/`，不要拷进本目录。

未来排期写在 `calendar/`，不要把单期手册再拆回 `calendar/` / 口播 / 脚本三个平行文件夹。
