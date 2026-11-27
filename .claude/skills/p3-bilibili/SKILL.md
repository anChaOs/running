---
name: p3-bilibili
description: 用 tools/publish/bilibili_upload.py 把本期 upload/ 成片双封面投到 B 站（16:9 cover + 4:3 cover43）。biliup 单封面 4:3 只作备选。用户说 B 站上传、biliup、投 B 站、自动发 B 站时用。独立于 p3-publish：本 skill 只负责投稿拿 BV；双链齐后走 p3-publish。
---

# B 站自动投稿

默认用 `tools/publish/bilibili_upload.py` 走 Web UPOS，一次提交两张封面：`cover` 是 `cover-16x9-1920x1080.jpg`，`cover43` 是 `cover-4x3-1920x1440.jpg`。Cookie 仍是 biliup 扫码得到的 `cookies.json`（CSRF 用 `bili_jct`）。

biliup 单封面留作备选：只传 4:3。Web `add/v3` 不可用、或 UPOS 线路证书失败且换线仍不行时再用。

本 skill **只上传**，不写 `published`、不合 PR、不拷复盘日志、不清临时。

## 不要做的事

- 缺成片、缺 16:9 或 4:3 任一张封面、简介超过 2000 个 Unicode 码位、标题超过 80 个码位、标签超过 10 个或单条超过 20 个码位、cookie 缺失或 `expires` 已过期时，不要硬传
- biliup 备选只收一张封面，用 `cover-4x3-1920x1440.jpg`。16:9 只在默认脚本里当 `cover`
- 不要再推荐官方个人开放平台 / 企业入驻当投稿路径（死路）
- 不要用 biliup `--extra-fields '{"cover43":...}'` 当双封面方案。客户端提交会退回 APP，APP 不透传 `cover43`
- `--dry-run` 只打印检查。脚本这时不改 `logs/timeline.txt`，也不改 `logs/todo.md`

## 前置

1. 本期已 `upload: ready`（最终导出并打包后）：媒体目录有 `upload/`
   - 标题名烧字成片 `.mp4`（已 MOVE 进 `upload/`，根目录无第二份）
   - `cover-16x9-1920x1080.jpg` 与 `cover-4x3-1920x1440.jpg`（两张都要）
   - 可选 `subtitles.srt`（本脚本不挂外挂；创作中心可后补）
2. `plan.md` 已有「## 标题」、「### B 站」简介、「## 标签」里的 B 站标签。脚本按 Unicode 码位计数：简介超过 2000、标题超过 80、标签超过 10 个或单条超过 20，就停，不投稿。
3. `logs/todo.md` 里 `pack-upload: done`。没 done 时脚本拒绝投稿。
4. Cookie：`~/Movies/running-content/.biliup/cookies.json`
   - 没有或接口报登录失效 → 先登录（见下）

## 登录（仅失效时）

在 Mac 上：

```bash
mkdir -p ~/Movies/running-content/.biliup
cd ~/Movies/running-content/.biliup
biliup -u ./cookies.json login
```

扫 B 站 App 二维码；成功后 cookie 落在上述路径。登录不改 `logs/todo.md`。日常投稿前可：

```bash
biliup -u ~/Movies/running-content/.biliup/cookies.json renew
```

## 投稿参数（默认）

| 项 | 来源 / 默认 |
| --- | --- |
| 成片 | `~/Movies/running-content/YYYY-MM-DD-slug/upload/` 里唯一的 `.mp4` |
| 16:9 封面 | 同目录 `cover-16x9-1920x1080.jpg` → 提交字段 `cover` |
| 4:3 封面 | 同目录 `cover-4x3-1920x1440.jpg` → 提交字段 `cover43` |
| 标题 | `episodes/<slug>/plan.md`「## 标题」。Unicode 码位 ≤ 80 |
| 简介 | 同文件「### B 站」正文。Unicode 码位 ≤ 2000 |
| 分区 `tid` | `238`（运动） |
| 并发 `--limit` | `6` |
| 标签 | 「## 标签」下 B 站那一段（代码块或「B 站：」同一行）。去掉 `#`，逗号分隔。最多 10 个，单条 ≤ 20 个码位。不要用 YouTube 那一段，也不要写死一套默认标签 |
| 版权 | `copyright=1`（自制） |
| 线路 `-l` | 本机优先 `bda2` / `tx`；云端 `us-west1` 用 `ws`（备选 `qn`）；证书/超时再换线 |
| Cookie | `~/Movies/running-content/.biliup/cookies.json` |
| 稿件 | `https://member.bilibili.com/x/vu/web/add/v3?csrf=<bili_jct>` |

脚本自己从 `--media-dir` 的目录名找到 `episodes/<slug>/plan.md`。不在仓库根目录跑时，这个定位仍然有效。

## 云端异步投稿（GCS + Cloud Run Job，可合盖断网）

需要与 `/p3-youtube` 共用同一份 `gs://<bucket>/staging/<slug>/video.mp4`、传完 GCS 即合盖断网时，使用 `tools/publish/bilibili_cloud.py`（一次部署见 `tools/publish/cloud_bili/deploy.sh`，默认 `us-west1` + `ws` 线路）：

```bash
# 1. 触发云端投稿（若 YouTube 已把 video.mp4 传进 GCS staging，自动跳过视频重传）
.venv/bin/python tools/publish/bilibili_cloud.py upload \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug

# 2. 稍后取回 BV 号与链接并标 bilibili: done
.venv/bin/python tools/publish/bilibili_cloud.py result \
  --media-dir ~/Movies/running-content/YYYY-MM-DD-slug

# 3. 本机 cookies.json renew/重新扫码后同步到 Secret Manager
.venv/bin/python tools/publish/bilibili_cloud.py sync-cookies
```

## 命令模板

先 dry-run，再正式传。正式上传前脚本记 `start bilibili-upload`；成功记 `end`（note 里是 BV 和链接），打印 BV 和链接，再 `todo_list.py mark bilibili done`。失败记 `fail bilibili-upload`，不标 done。todo 写入失败时 BV 已经打印，时间表也已经是 `END`；再跑同一命令会拒绝，避免再投一稿。

```bash
MEDIA="$HOME/Movies/running-content/YYYY-MM-DD-slug"

.venv/bin/python tools/publish/bilibili_upload.py \
  --media-dir "$MEDIA" \
  --dry-run

.venv/bin/python tools/publish/bilibili_upload.py \
  --media-dir "$MEDIA" \
  -l bda2 \
  --limit 6
```

成片约 2G 时常要十几分钟。成功输出一行 `BV…` 和 `https://www.bilibili.com/video/BV…`。未标 `bilibili: done` 前不要写 `episode.md`。

失败：

- SSL / 线路错误 → 换 `-l` 重试（`bldsa`、`tx`、`qn`）。同一成片在失败后可再传。`--retries` 是单次分片或合并失败后的额外次数，默认 3，不含第一次
- `logs/todo.md` 里 `bilibili` 已是 done，或 `logs/timeline.txt` 已有 `END bilibili-upload` 时，脚本拒绝再传，避免同一期再投稿一份
- cookie 失效 → `login` / `renew` 后再传
- Web `add/v3` 仍失败 → 改走下面的 biliup 单封面备选，封面改用 4:3

## biliup 单封面（备选）

只在默认脚本走不通时用。封面只用 4:3。投稿前先数简介字数：

```bash
.venv/bin/python tools/publish/pack_upload.py --check-desc /tmp/bilibili-desc.txt
```

`--check-desc` 通过且 `pack-upload: done` 才能传。biliup 没有仓库挂钩：投稿前用 `tools/log_timeline.py` 记 `start bilibili-upload`，成功 `end` 并 `todo_list.py mark bilibili done`，失败 `fail`（不标 done）。

```bash
export PATH="$HOME/.local/bin:$PATH"
COOKIE="$HOME/Movies/running-content/.biliup/cookies.json"
MEDIA="$HOME/Movies/running-content/YYYY-MM-DD-slug/upload"
DESC_FILE="$(mktemp)"
# 将 plan.md「### B 站」正文写入 "$DESC_FILE"

biliup -u "$COOKIE" upload \
  -l bda2 \
  --limit 6 \
  --copyright 1 \
  --tid 238 \
  --tag "〈plan.md 标签，逗号分隔〉" \
  --title "〈标题〉" \
  --desc "$(cat "$DESC_FILE")" \
  --cover "$MEDIA/cover-4x3-1920x1440.jpg" \
  "$MEDIA/〈标题〉.mp4"
```

## 成功后

1. 把 `https://www.bilibili.com/video/BV…` 写入该期 `episode.md`「发布」栏「Bilibili：」（YouTube 仍空则 **不要** 改 `published`）
2. 推当期 episode 分支；**不要**因只有 B 站链就合 PR
3. 告诉用户 BV；下一步：

> B 站已投稿：`https://www.bilibili.com/video/BV…`（审核中则如实说）。  
> YouTube 仍空着时 `status` 保持 `edited`。双链齐了再 `/p3-publish`。  
> 若还要自动传 YouTube，走 `/p3-youtube`（**不是**本 skill，也不经 `p3-publish`）。

## 翻车记录

- 投稿接口若只收一张封面（biliup / APP），必须传 `cover-4x3-1920x1440.jpg`，不要传 16:9
- 双封面要在 `web/add/v3` 提交时带上 `cover` 和 `cover43`。投稿成功后再用创作中心改封面，接口常回 **-400**
- `bda2` 遇证书过期时换 `-l`；曾用 `bda2` 约 1.9MB/s 传完 ~2.3G
- 官方开放平台「个人开发者」未开，不要再试企业入驻链路当默认
- biliup 不替代 `p3-publish`：清临时 / squash 仍要双链 + 人确认 KEEP/DELETE
