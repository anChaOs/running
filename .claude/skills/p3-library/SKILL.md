---
name: p3-library
description: 备选主题库。用户灵光一闪扔来一个主题、先记下来、不确定什么时候讲、拆题、给主题做调研入库、看主题库状态时用。按体量做记录、拆解、调研或写入 wiki。不要收敛成当天口播，不要建 episode。有拍摄日、要写成口播时用 p3-topic。
---

# 主题库

把还没拍摄日的主题收进 `topics/`。账号主线仍是破三实验室；这里主线、配菜都收。

和 `/p3-topic` 的分工：这里是库存；`p3-topic` 是「今天要拍、写成口播」。不要在这里写 `talk.md` 或 `episodes/`。

## 不要做的事

- 没有拍摄日就建 episode、写口播卡
- 一句话种子就开长调研、开一堆空 wiki 页
- 把 wiki 正文抄进主题卡；稳定结论 ingest 进 `knowledge/wiki/`，卡上只留指针
- 用比喻标题；人称代词指代不明
- 没看 `topics/index.md` 就新建，造成重复

## 开场

用户扔来一句话或一个链接：不要问「有没有主题」。用一句话复述种子，请用户改。然后按体量做事，不要先对谈到能拍。

用户说「主题库 / 有哪些备选 / 某某主题怎么样了」：先读 `topics/index.md`，按状态汇报，不要把每张卡全文贴出来。

连主题都说不清的碎片，才进 `inbox/`。

## 先看一眼

- `topics/index.md`：有没有同类
- `knowledge/wiki/index.md`：有没有现成概念页
- `episodes/*/episode.md`：是不是拍过

## 体量与深度

按种子大小选一档，不要默认拉满。

| 体量 | 做什么 | 状态落到 |
|------|--------|----------|
| 小 | 记下种子、种类、一句话。停。 | `seed` |
| 要拆 | 拆成几条可拍的角度（每条一句），不写口播。 | `scoped` |
| 要调研 | 派 subagent。事实和传闻分开。 | `scoped`；有稳定结论再 ingest wiki |
| 要进 wiki | 按 `knowledge/CLAUDE.md` ingest。卡上只写 `wiki:` 指针。 | `wiki` |
| 可以拍了 | 标 `ready`。等有拍摄日再 `/p3-topic`。 | `ready` |

种类：`running`（主线）/ `life`（自身经历）/ `news`（社会热点）/ `ai` / `finance`。

社会热点默认不进 wiki。自身经历默认不进 wiki。

## 状态

`seed` → `scoped` → `wiki` → `ready` → `used`

旁路：`parked`（暂缓）、`dropped`（不做）。

已拍：`used`，在卡上写 `episodes: [YYYY-MM-DD-slug]`。

## 落盘

1. 新建或改 `topics/<slug>.md`（模板 `templates/topic-library.md`）。slug 短英文或拼音，**不要**用拍摄日期当文件名。
2. 更新 `topics/index.md` 一行：slug、一句话、种类、体量、状态。
3. 调研要进 wiki 时：原文 `knowledge/raw/<category>/`，概念 `knowledge/wiki/<category>/`，改 `wiki/index.md` 和 `wiki/log.md`。

用户原句写进「种子」。不要改成更像文案的句子。

## 完成后

告诉用户：卡路径、现在状态、wiki 指针（若有）。

- 还早：停。用户以后可再 `/p3-library 继续挖 <slug>` 或 `/p3-library 调研 <slug>`。
- `ready` 且用户有拍摄日：`/p3-topic`，不要在这里写口播。
- 只是记了一笔：不要推荐成片 skill。
