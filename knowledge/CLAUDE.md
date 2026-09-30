# knowledge schema（瘦身 LLM wiki）

跑步自媒体的长期知识库。不是 RAG：摄入时编译进 wiki，查询先读 wiki，不每次从原文重拼。

## 三层

| 路径 | 谁写 | 作用 |
|------|------|------|
| `knowledge/raw/` | 人策展，LLM 只读 | 原文、截图转写、课程摘录、官方说明。不改。 |
| `knowledge/wiki/` | LLM 维护 | 概念页、问题页、来源摘要。交叉链接、目录、日志。 |
| `knowledge/production/` | 人写 | 出片 SOP。先不编进 wiki。改操作以 `.claude/skills/` 为准。 |

人负责丢来源、提问、定哪一页重要。LLM 负责摘要、改相关页、补链接、记日志。人很少手写 wiki 正文。

## 目录

```text
knowledge/
  CLAUDE.md              # 本 schema
  incoming/YYYY-MM-DD/   # 外部交件检疫区（zip、grok out/）；合并进 raw/wiki 后可清理
  raw/<category>/        # 只读来源；running/ 下可按来源谱系分子目录
  wiki/
    index.md             # 总目录，查询先读
    log.md               # 只追加
    <category>/          # 目前有 running/；以后可加 races/、equipment/ 等
  production/            # 出片 SOP，人写
```

`incoming/` 只放待合并原件，**不要把里面的 wiki 直接拷进 `wiki/`**。zip 与交件原件进 `incoming/YYYY-MM-DD/packs/` 或对应批次目录。wiki 的 `sources` 指向 `raw/`，不依赖 `incoming/` 路径。

`raw/running/` 谱系（新批次按来源建子目录，旧文件仍在 `running/` 根下不必搬家）：

| 目录 | 内容 |
|------|------|
| `raw/running/physiology/` | 文献笔记、综述摘录（策展，不是论文 PDF） |
| `raw/running/bili-up/` | B 站口播定稿/摘录（山雨小月、云健身等） |
| `raw/running/*.md` | 零散来源（App 转写等） |

新种类：在 `raw/` 和 `wiki/` 下建同名目录，并在 `wiki/index.md` 加一节。不要把所有东西塞进 `running/`。

作者会聊、因而可能进 wiki 的种类：

| 种类 | 目录 | 进 wiki 的 |
|------|------|------------|
| 跑步 | `running/` | 理论、历史、指标、装备、赛事 |
| AI | `ai/` | 可复用的概念、工具、判断 |
| 金融投资理财 | `finance/` | 可复用的概念、框架；不是当日行情 |

不进 wiki：自身经历（写 `episodes/` / `training/`）、社会热点（过期快；只有沉淀成概念才 ingest）。

## 页面

文件名用中文主题，短、能拿来 `[[wikilink]]`。

文首 YAML：

```yaml
---
type: concept | questions | source-summary
category: running
title: 短标题
updated: YYYY-MM-DD
sources: []
related: []
---
```

- `concept`：一个概念或一套指标
- `questions`：待验证问题
- `source-summary`：一篇来源的摘要（可选；来源本身放 `raw/`）

正文用 `[[页名]]` 链到 wiki 里已有的页。事实 / 个人体验 / 推测分开。引用过来源。

## 三种操作

**ingest**（选题调研、新来源、用户截图、外部 zip 交件）

1. 先读 `wiki/index.md`，有现成页就改，不要重复开篇。
2. 外部整包交件先进 `incoming/YYYY-MM-DD/`，不要直接进 wiki。
3. 原文进 `raw/<category>/`（按来源谱系分子目录），不改原文。
4. 写或改 wiki 页；同题只留一页；相关页补链接。来源分层写在正文（【文献】【口播】…）。
5. 更新 `wiki/index.md` 一行说明。
6. 在 `wiki/log.md` 末尾追加一条。

**query**

先读 `wiki/index.md`，再打开相关页。wiki 没有的再去查网或 MCP。新的稳定结论可以 ingest 回去。

**lint**（有空再做）

断链、两页打架、过期数字、只有结论没有来源、index 漏了页。

## 不要

- 把选题卡、口播卡、训练日志写进 wiki
- 改 `raw/`
- 用 wiki 覆盖 `production/` 里的操作参数
- 一次 ingest 开一堆空页
- 把 `incoming/` 交件树当成 wiki
- 按 zip 编号在 `wiki/` 建子目录
