# wiki log

只追加，不改旧条。

## 2026-09-19

- 建瘦身 LLM wiki：`raw/` + `wiki/` + `knowledge/CLAUDE.md`。`production/` 仍人写、不编入 wiki。
- 迁入既有笔记：[[快慢肌比例与马拉松]]、[[有氧能力提高]]、[[耐力赛能量补充]]、[[open-questions]]。
- ingest 高驰 App「了解」原文 → [[高驰负荷三个指标]]。

## 2026-09-22

- ingest 2026 柏林马拉松调研的耐久部分 → [[柏林马拉松]]。当年精英名单、萨维退赛、何杰/张德顺出场只放 `topics/berlin-marathon.md`。
- 删除未读文献调研骨架（训练适应 / 能量代谢 / 伤病恢复）及其 raw，并撤掉挂到其他跑步页和 [[open-questions]] 的链接。调研计划不进 wiki。

## 2026-09-23

- incoming 七包 zip（三支柱文献 + B 站山雨/云健身六主题）进 `knowledge/incoming/2026-09-22/`，来源进 `raw/running/{physiology,bili-up}/`。63 个交件概念页激进合并为 13 个新页并改写 4 个旧页：[[有氧能力提高]]、[[耐力赛能量补充]]、[[高驰负荷三个指标]]、[[快慢肌比例与马拉松]]、[[open-questions]]；新建 [[训练强度分布]]、[[高强度间歇训练]]、[[跑步经济性与力量]]、[[跑姿步频与姿势跑法]]、[[Fatmax与脂肪氧化]]、[[碳水周期化与train-low]]、[[日常能量与吸收]]、[[相对能量缺乏与骨应力]]、[[跑步相关损伤与负荷]]、[[肌腱病连续体与复跑]]、[[过度训练与恢复]]、[[停训与复训]]、[[夏训保量]]。薄页（非诊疗边界、吸收率与449、马克操两名等）并入邻页；UP 主张与文献在正文分层标注。

## 2026-09-30

- ingest 云健身 BV16suu6JEaG《把乳酸阈相关的基础知识讲清楚》（2026-08-08）。whisper 校正稿进 `raw/running/bili-up/云健身-BV16suu6JEaG-乳酸阈.md`，概念页 [[乳酸阈]]。[[有氧能力提高]] 的「1 小时配速」和 [[训练强度分布]] 的山雨三区改为指向该页，不并成同一个点。这期口播没有讲停跑。
- 核对停训摘要：Mujika & Padilla 2000 Part I/II、Coyle 1984、Houston 1979，原文摘录进 `raw/running/physiology/detraining-abstracts-2026-09-30.md`，改写 [[停训与复训]]。「大约一周心肺还可忽略」改回山雨口播；Mujika 摘要写的是不足 4 周时最大摄氧量和血容量已经快速下降。再训练只保留 Houston 的 15 天对 15 天。
- [[停训与复训]] 按心脏泵血、氧气运输、线粒体数量、氧气利用四行重排已核对的天数。第 3–4 天仍无单独百分比。
- 核对 Helgerud 2007、MacInnis & Gibala 2017 摘要，写入 [[高强度间歇训练]]。总功相同时，高有氧强度间歇更多提高最大摄氧量和每搏输出；线粒体信号也更取决于强度。强度对血容量和毛细血管的证据较少。
- 听写云健身 BV1mg4y1f7Y7《有氧运动能力的底层逻辑》。公开字幕接口要登录，校正稿进 `raw/running/bili-up/云健身-BV1mg4y1f7Y7-有氧底层逻辑.md`，写入 [[有氧能力提高]]。中央每搏输出：70%–75% 最大摄氧量持续；外周线粒体、毛细血管、氧化酶：100% 最大摄氧量间歇。与山雨「间歇最利心脏」并列，不合并。

## 2026-10-28

- 新增 [[VO2max]]（备选选题知识说明，非口播稿；应跑步自媒体/安超）。

## 2026-11-25

- 清理 [[VO2max]] `sources` 中的内部 `wiki/` 路径并补充 `aliases`；新增 `tools/kb_lint.py` 校验通过（0 error）。
- 为 `wiki/running/` 下其余 20 页批量补充 `aliases` 中英文简称与俗称，经 `tools/kb_lint.py` 校验无别名冲突。
- 核对高温与热适应文献摘要（Ely 2007、Mantzios 2022、Nybo 2014、Périard 2021、Racinais 2015、Sawka 2007、Tyler 2016/2024），原文摘录进 `raw/running/physiology/heat-stress-abstracts-2026-11-25.md`，新建概念页 [[温度与热应激]] 并与 [[夏训保量]] 双向互链。
- 批量调研并入库 4 个新概念页（均先核对 PubMed/PMC 原始摘要写入 `raw/running/physiology/`）：
  - [[碳板鞋与跑鞋力学]]（`aft-shoes-abstracts-2026-11-25.md`：Hoogkamer 2018、Healey & Hoogkamer 2022、Tenforde 2023、Malisoux 2015、Joubert 2023）
  - [[高原训练与高住低训]]（`altitude-training-abstracts-2026-11-25.md`：Levine & Stray-Gundersen 1997、Siebenmann 2012、Saugy 2016/2017、Porcari 2016、Garvican-Lewis 2016、Stellingwerff 2019、Chapman 2014）
  - [[体重与马拉松配速]]（`weight-performance-abstracts-2026-11-25.md`：Cureton 1978、Hoogkamer 2016、Garthe 2011、Hall 2011）
  - [[赛前减量]]（`tapering-abstracts-2026-11-25.md`：Bosquet 2007、Mujika & Padilla 2003、Smyth & Lawlor 2021、Campbell & Turner 2018）
- 同步更新 `index.md` 与 [[跑步经济性与力量]]、[[日常能量与吸收]]、[[相对能量缺乏与骨应力]]、[[训练强度分布]] 的双向 `related` 互链。

## 2026-11-26

- 按原始文献摘要标准补齐 3 个既有概念页缺口（新增 3 份 `raw/running/physiology/*-2026-11-26.md` 核对稿，不改旧 `raw/`）：
  - [[训练强度分布]]：补齐 Seiler 2010（80/20 课次口径 vs 时间口径）、Muñoz et al. 2014（业余 10 km 极化 RCT）、Bull et al. 2020（WHO 2020 指南 150–300′ 中等 / 75–150′ 高强度）。
  - [[乳酸阈]]：补齐 Robergs et al. 2004（2004 酸中毒翻案）、Brooks 2018（乳酸穿梭）、Faude et al. 2009（25 种 LT 概念三分框架）、McGehee et al. 2005（30′ 场地测 SEE 0.21 m/s、8.0 bpm），并更新索引摘要。
  - [[停训与复训]]：补齐 Coyle et al. 1986（血浆容量 −12% 致 SV 降与心率虚高）、Madsen et al. 1993（VO₂max 不变但力竭时间 −21% 与 RER 升高）、Billat et al. 2000（30s/30s 短间歇 VO₂max 时间与复训软组织边界），并补充与 [[赛前减量]]、[[肌腱病连续体与复跑]] 的互链。

## 2026-11-27

- 新建并深度扩充概念页 [[赛前断碳与冲碳]]（原始摘要核对稿 `raw/running/physiology/carb-loading-abstracts-2026-11-27.md`，覆盖 23 篇 PubMed/PMC 权威文献）：整合三大国际权威共识（ACSM/AND/DC 2016、ISSN 2017、IAAF 2019 共识与长跑专项综述）、三代冲碳协议演进（Bergström 1967、Sherman 1981、Bussau 2002、Fairchild 2002）、亚细胞与分子机制（Ørtenblad 2013 肌原纤维内糖原-Ca²⁺、Hingst 2018 AMPK/GS）、肝糖原与果糖协同（Gonzalez 2016）、3–5 天维持窗（Goforth 1997、Arnall 2007）、离心肌损伤（Costill 1990、Solem 2025 meta）、低 FODMAP 胃肠策略（Lis 2018）及 90% 实地知行脱节（Sampson 2024）；同步更新 `index.md` 及双向 `related` 互链。

