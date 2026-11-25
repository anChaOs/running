---
name: p3-kb
description: 跑步自媒体知识库（knowledge/wiki/）的维护与检索工作流。用户要把新资料、论文摘要、视频笔记或训练复盘结论沉淀进 wiki（ingest），按概念或别名检索已有知识（query），或对知识库做体检修链（lint）时使用。不写单期口播，不建 episode。
---

# 知识库维护（p3-kb）

围绕 `knowledge/` 三层结构（`raw/` 只读来源、`wiki/` LLM 维护概念页、`production/` 人写 SOP）执行 **ingest / query / lint**，遵循 `knowledge/CLAUDE.md` 与模板 `templates/wiki-page.md`。

## 不要做的事

- 修改 `knowledge/raw/` 里的任何文件（只读）
- 把单期选题卡、口播稿、日记、过期热点或纯个人流水账写进 `knowledge/wiki/`
- 用 wiki 覆盖 `knowledge/production/` 里的拍摄、HUD 或剪辑参数
- 在 `sources` 里写 `wiki/...` 或 `incoming/...` 路径（内部互链放 `related`，本地来源先入 `raw/`，外部可直接填权威 `http(s)` URL）
- 一次 ingest 开一堆空页或薄页；优先并入已有概念页

## 模式路由

按用户意图选择对应子流程：

| 意图 | 模式 | 做什么 |
|---|---|---|
| 沉淀新文章、论文、口播笔记、截图转写或外部交件 | `ingest` | 查重 → 原文入 `raw/` → 写/改 `wiki/` → 更新 `index.md` 与 `log.md` → 跑 `kb_lint.py` |
| 查某个概念、中英文术语/别名、证据边界或某位来源的观点 | `query` | 先读 `wiki/index.md` → 按标题或 `aliases` 定位概念页 → 区分事实/体验/推测作答 |
| 知识库体检、查断链、补别名、修 frontmatter 或拆大页 | `lint` | 跑 `.venv/bin/python tools/kb_lint.py` → 汇报 error/warning → 经确认后修复 |

## 1. ingest（沉淀入库）

1. 先读 `knowledge/wiki/index.md`，核对是否已有现成概念页或 `aliases` 命中；有现成页就直接改写，不要重复开篇。
2. 外部整包交件（如 zip）先进 `knowledge/incoming/YYYY-MM-DD/` 检疫，验收合并后再清理；不要把外部 wiki 直接拷进 `knowledge/wiki/`。
3. 原始材料放进 `knowledge/raw/<category>/`（如 `raw/running/physiology/`、`raw/running/bili-up/`），保存后不再改动。
4. 新建或更新 `knowledge/wiki/<category>/<概念名>.md`：
   - 新建页使用 `templates/wiki-page.md`，补全 `type`、`category`、`title`、`aliases`（中英文简称/俗称）、`updated`、`sources`（指向 `raw/...` 或权威 `http(s)` URL）、`related`（指向其他 wiki 页名或别名）。
   - 正文区分事实 / 个人体验 / 推测，来源按层级标注（如 `【文献】`、`【口播】`），冲突观点并列不硬揉。
   - 正文用 `[[页名]]` 链到已有页，并给相关页补反向链接。
   - 保持原子粒度（单页尽量控制在 15 KB 以内；长专题拆成主概念 + 子题页）。
5. 同步更新 `knowledge/wiki/index.md`（一句话摘要）并在 `knowledge/wiki/log.md` 末尾追加一条记录。
6. 运行 `.venv/bin/python tools/kb_lint.py`，确保新增/改动无 error。

## 2. query（检索问答）

1. 先读 `knowledge/wiki/index.md` 定位候选概念页；若按英文缩写或俗称未直接命中标题，再检索 `knowledge/wiki/` 里的 `aliases` 字段与正文。
2. 打开命中的概念页作答，明确标出结论来源层级与适用边界；wiki 没有的内容再查外网或 MCP，如有稳定结论可提示用户是否 `ingest` 回库。

## 3. lint（体检与修复）

1. 运行：
   ```bash
   .venv/bin/python tools/kb_lint.py
   ```
2. 按严重级别向用户汇报：
   - **Errors（必修）**：缺失/非法 frontmatter、`index.md` 漏页或悬空链接、`[[wikilink]]` / `related` 断链、`sources` 指向 `wiki/` 或不存在的文件。
   - **Warnings（建议处理）**：超长页（默认 >15 KB）、概念页缺少 `sources`、别名冲突、`log.md` 日期滞后、未清理的 `incoming/` 残留。
3. 给出修复方案，经用户确认后执行修改，并重跑 `kb_lint.py` 复验。

## 完成后

告知用户：
- 改动的文件路径与 `kb_lint.py` 检查结果（error / warning 数）；
- 下一步建议（例如：继续 `/p3-library` 把新概念做成备选选题、或 `/p3-topic` 结合近期训练写成口播），并附一条可直接复制的提示词。
