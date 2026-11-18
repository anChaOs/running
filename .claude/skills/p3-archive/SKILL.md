---
name: p3-archive
description: 把满 7 天的跑步素材从 ~/Movies/running-content/ 原样归档到 WD My Passport。用户说归档、搬盘、腾空间、Passport、满 7 天时用。按 YYYYMM/YYYY-MM-DD-slug/ 存放，不打压缩包。核对文件数和逐文件大小后再删本地。不要动盘里其它目录。不要在成片流程里自行搬盘。
---

# 归档素材

把本地媒体目录里**满 7 天**的期，整夹原样拷到移动硬盘，核过再删本地。仓库 `episodes/` 不动。这不是成片阶段，用户没说归档 / 腾空间就不要跑。

```text
~/Movies/running-content/YYYY-MM-DD-slug/
  → /Volumes/My Passport/running-content/YYYYMM/YYYY-MM-DD-slug/
```

月目录是 `YYYYMM`（`202604`），不是 `2026/04`，也不是 `2026-04`。

## 前置

1. Passport 已挂上，且**可写**。`mount` 不应带 `read-only`。不可写时先停：macOS 自带 NTFS 只读；本机用 TT NTFS Native。日志不干净时驱动会只读挂上，不要格式化，不要用系统 `mount_ntfs -o rw`。
2. 列出 `~/Movies/running-content/YYYY-MM-DD-*`。期日 `<= 今天 − 7 天` 才归档。用户点名某几期则只做那几期。
3. 跳过 `.models`、跳过不满 7 天的期、跳过已经在硬盘对应路径且核对过的期。

## 不要做的事

- 不要打 zip / 7z / tar。视频已是 HEVC，再压几乎不省空间，归档盘上也要能直接回看、重做
- 不要动 Passport 上 `running-content/` 以外的目录
- 不要归档仓库里的 `episodes/`、`talk.md`、外挂 SRT 源稿
- 不要在核对完成前删本地
- 不要覆盖硬盘上已有且体积更大的同名目录，除非用户明确要重拷
- 不要用 `rm -rf "$path"` 这种变量删目录；核对通过后用**字面量绝对路径**逐期删

## 步骤

### 1. 盘点

报给用户：将归档哪些期、每期大约多大、硬盘是否可写、本机还留哪些（不满 7 天）。用户没反对再拷。

### 2. 拷贝

```bash
export COPYFILE_DISABLE=1
mkdir -p "/Volumes/My Passport/running-content/YYYYMM"
rsync -a --no-owner --no-group --exclude '.DS_Store' --exclude '._*' \
  ~/Movies/running-content/YYYY-MM-DD-slug \
  "/Volumes/My Passport/running-content/YYYYMM/"
```

一次多期时按期 `rsync`，不要把多期内容摊进同一个月目录。拷得久时：**已经拷完的期先核、先删本地**，不要等全部结束才腾空间。

### 3. 核对

对每一期：源和目标去掉 `.DS_Store` / `._*` 之后，相对路径集合相同，且每个文件 `st_size` 相同。缺文件、多文件、体积不对，这一期不要删本地，补拷后再核。

### 4. 删本地

只删核对通过的那一期媒体目录。本机空闲变化报给用户。

## 完成

- 硬盘上有 `running-content/YYYYMM/YYYY-MM-DD-slug/`，文件数和体积与归档前本地一致
- 本地对应期已删
- 不满 7 天的期和 `.models` 仍在 `~/Movies/running-content/`

## 完成后

列出：归档了哪些、硬盘路径、本机还留哪些、本机空闲。没有强制下一步。正在做当前期成片就回到那一期的 `/p3-xxx`。
