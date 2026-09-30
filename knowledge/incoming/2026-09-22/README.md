# incoming 2026-09-22

grok 沙箱交件的检疫区。**不要把这里的 wiki 直接拷进 `knowledge/wiki/`。**

## 这批是什么

| 目录 | 来源 | 性质 |
|------|------|------|
| `packs/*.zip` | `~/Downloads/out/` 原包 | 运输备份 |
| `physiology/` | 训练适应 / 能量代谢 / 伤病恢复 | 文献笔记交件（已核实 DOI，不是论文 PDF） |
| `up-01-跑步理论/` … `up-06-训练方式/` | B 站 山雨小月、云健身-仰望尾迹云 字幕调研 | 口播主张 + 文献挂点交件 |

每个解压目录下的 `out/` 是 grok 产物：`raw/`、`wiki/`、`INDEX_ROWS.md`、`LOG.md`、`SKIPPED.md`。

## 正式归属

| 交件 | 进哪里 |
|------|--------|
| 来源 md | `knowledge/raw/running/physiology/`、`knowledge/raw/running/bili-up/` |
| 合并后的概念 | `knowledge/wiki/running/`（扁平，同题一页） |
| 本批次记录 | `knowledge/wiki/log.md` |

## 合并规则（摘要）

1. 同题只留一页；两路来源写进同一页的 `sources` 与正文分层（【文献】/【口播-山雨】/【口播-云健身】/【第三方】）。
2. 薄页（非诊疗边界、吸收率与449 等）并进邻页，不单开。
3. 调研计划、收口说明、原始字幕 dump、未读勾选表不进 wiki（见各包 `SKIPPED.md`）。
4. 已有页就改，不重建：[[有氧能力提高]]、[[耐力赛能量补充]]、[[高驰负荷三个指标]]、[[快慢肌比例与马拉松]]、[[open-questions]]、[[柏林马拉松]]。

## 清理

wiki 验收后：可删各 `*/out/wiki` 与本 README 所述正文副本，或整目录只留 `packs/`。wiki 的 `sources` 指向 `raw/running/...`，不依赖 `incoming/` 路径。
