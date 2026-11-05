---
name: p3-bilibili
description: 用 biliup-rs 把本期 upload/ 成片自动投到 B 站（标题/简介/4×3 封面/分区/标签）。用户说 B 站上传、biliup、投 B 站、自动发 B 站时用。独立于 p3-publish：本 skill 只负责投稿拿 BV；写双链 / published / 合 PR / 清临时仍走 p3-publish。
---

# B 站自动投稿（biliup）

官方开放平台个人号走不通；用 **biliup-rs** + 扫码 cookie 投稿。本 skill **只上传**，不写 `published`、不合 PR、不清临时。

## 不要做的事

- 不要缺成片 / 缺封面 / cookie 失效时硬传
- 不要用 16:9 当投稿封面（接口只收一张时必须用 **4×3**）
- 不要再推荐官方个人开放平台 / 企业入驻当默认投稿路径（死路）
- 投稿成功后若要用创作中心 / member API 改封面：接口常回 **-400**，失败就请用户在创作中心手换，不要死磕自动化

## 前置

1. 本期已 `upload: ready`（`p3-burn` 后）：媒体目录有 `upload/`  
   - 标题名烧字成片 `.mp4`（已 MOVE 进 `upload/`，根目录无第二份）  
   - `cover-4x3-1920x1440.jpg`（另两张可并存，**投稿只用这张**）  
   - 可选 `subtitles.srt`（biliup 本次不挂外挂；创作中心可后补）
2. `plan.md` 已有标题 +「### B 站」简介
3. Mac 上已装 `biliup`（`~/.local/bin/biliup`，PATH 含该目录）
4. Cookie：`~/Movies/running-content/.biliup/cookies.json`  
   - 没有或 `renew`/`upload` 报登录失效 → 先登录（见下）

## 登录（仅失效时）

在 Mac 上：

```bash
mkdir -p ~/Movies/running-content/.biliup
cd ~/Movies/running-content/.biliup
biliup -u ./cookies.json login
```

扫 B 站 App 二维码；成功后 cookie 落在上述路径。日常投稿前可：

```bash
biliup -u ~/Movies/running-content/.biliup/cookies.json renew
```

## 投稿参数（默认）

| 项 | 来源 / 默认 |
| --- | --- |
| 成片 | `~/Movies/running-content/YYYY-MM-DD-slug/upload/<标题>.mp4` |
| 封面 | 同目录 `cover-4x3-1920x1440.jpg`（**唯一**投稿封面） |
| 标题 | `plan.md`「发这个」那一行 |
| 简介 | `plan.md`「### B 站」正文（可先写入临时文件再 `--desc`） |
| 分区 `--tid` | `238`（运动） |
| 标签 `--tag` | 从当期 `plan.md`「## 标签」里 **B 站** 那栏抄（由 `/p3-subs` 按字幕写好）；去掉 `#`、改逗号分隔给 CLI；**不要**在本 skill 写死一套默认标签 |
| 版权 | `--copyright 1`（自制） |
| 线路 `-l` | 优先 `bda2`；证书/超时/SSL 再换 `bldsa` / `tx` / `qn` |
| Cookie | `-u ~/Movies/running-content/.biliup/cookies.json`（全局选项，放在子命令前） |

## 命令模板

把占位换成当期真实路径与文案。简介含换行时用文件，避免 shell 吞行：

```bash
export PATH="$HOME/.local/bin:$PATH"
COOKIE="$HOME/Movies/running-content/.biliup/cookies.json"
MEDIA="$HOME/Movies/running-content/YYYY-MM-DD-slug/upload"
DESC_FILE="$(mktemp)"
# 将 plan.md「### B 站」正文写入 "$DESC_FILE"

biliup -u "$COOKIE" upload \
  -l bda2 \
  --copyright 1 \
  --tid 238 \
  --tag "〈plan.md 标签，逗号分隔〉" \
  --title "〈标题〉" \
  --desc "$(cat "$DESC_FILE")" \
  --cover "$MEDIA/cover-4x3-1920x1440.jpg" \
  "$MEDIA/〈标题〉.mp4"
```

成片约 2G 时常要十几分钟；放后台并盯日志。成功日志里会有 `bvid`（如 `BV…`）和 `aid`。

失败：

- SSL / 线路错误 → 换 `-l` 重试（同一成片可再传；勿重复成功稿）
- cookie 失效 → `login` / `renew` 后再传
- 客户端提交失效 → biliup 常自动改走 APP；仍失败再查版本（`biliup -V`）

## 成功后

1. 把 `https://www.bilibili.com/video/BV…` 写入该期 `episode.md`「发布」栏「Bilibili：」（YouTube 仍空则 **不要** 改 `published`）
2. 推当期 episode 分支；**不要**因只有 B 站链就合 PR
3. 告诉用户 BV；下一步：

> B 站已投稿：`https://www.bilibili.com/video/BV…`（审核中则如实说）。  
> YouTube 仍空着时 `status` 保持 `edited`。双链齐了再 `/p3-publish`。  
> 若还要自动传 YouTube，走 `/p3-youtube`（**不是**本 skill，也不经 `p3-publish`）。

## 翻车记录

- 投稿接口通常只收 **一张**封面：必须传 `cover-4x3-1920x1440.jpg`，不要传 16:9
- `bda2` 遇证书过期时可换线；曾用 `bda2` 约 1.9MB/s 传完 ~2.3G
- 官方开放平台「个人开发者」未开，不要再试企业入驻链路当默认
- 投稿后用创作中心 / member API 改封面常 **-400**；手换更稳
- biliup 不替代 `p3-publish`：清临时 / squash 仍要双链 + 人确认 KEEP/DELETE
