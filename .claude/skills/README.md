# 成片 skills

本仓的 Agent skill，统一前缀 **`p3-`**（破三实验室）。每个子目录一个阶段，入口文件是 `SKILL.md`（YAML `name` / `description` + 正文），大段子阶段参考表放在各自 `references/` 下**按需加载**，不要一次读完全部。

总表见 `knowledge/production/成片skills.md`；成片总序与全局协议真源在 **`p3-episode`**。

## 两条总规则

1. **通用，不绑某一期。** 正文只用 `YYYY-MM-DD` / `slug` / `<HUD 名>` / `<跑完后累计 km>` 占位，不写死往期日期、`-sk`、封面句或 BV 号。对用户说话时把占位换成当前期真实值。
2. **做完必须推荐下一步。** 每个 skill 结束之后，立刻告诉用户：产物路径、下一个 `/p3-xxx`、一条填好当前期信息的可复制提示词。

## 目录

```text
.claude/skills/
  README.md
  p3-library         备选主题库（还没拍摄日）
  p3-topic           选题对谈 → 按拍摄分段的可念口播
  p3-episode         成片总调度、总序与全局协议真源
  p3-scaffold        建 episodes/YYYY-MM-DD-slug 与初始 logs/
  p3-ingest          VID_ / 高驰 FIT → open/run-*/close + 句间刀入表
  p3-shoes           training/logs/shoes.md，算出 -sn / -sk
  p3-hud             记录 HUD 规格；冻结后 --prep-alpha 画透明层
  p3-cover           真人抠图 + 创意底 + 三比例封面（与 HUD 并行）
  p3-assemble        按 logs/program.json 写审片播放清单（不编预览片）
  p3-subs            转写→人改→对齐→人工确认→写 plan.md 简介与标签（references/ 按需加载）
  p3-qc              审片或最终片抽帧核对
  p3-bilibili        可选：biliup 自动投 B 站（独立拿 BV）
  p3-youtube         可选：GCS（默认）/ Drive → Cloud Run Job 上传 YouTube（触发后可合盖）
  p3-publish         发布收尾：写双链 / published / 合 PR / 复盘同步 Drive / 清临时（references/ 按需加载）
  p3-publish-report  published 后立刻出单屏 HTML 报告并一并同步 Drive
  p3-jianying        60–90 秒剪映短视频，不走全长脚本
  p3-archive         满 7 天的本地素材搬到 Passport running-content/YYYYMM/
```

## 产物总序（简表，详见 `p3-episode`）

```text
p3-library / p3-topic / p3-scaffold
  → p3-ingest（锁原片↔FIT，句间刀入表）→ p3-shoes → p3-hud 记录 ∥ p3-cover
  → 冷开场 / 贴图 / 插入入表 → p3-assemble（写 review-preview.edl）
  → p3-subs（转写，冻结时间表，waiting-review 停）
  → 并行：用户校对字幕 ∥ --prep-alpha（8 核 -j 6）∥ --measure-only
  → 用户确认字幕（subs: confirmed）→ final_export.py --confirmed → p3-qc（final-qc done 后等「可以发了」）
  → pack_upload.py → （可选）p3-bilibili ∥ p3-youtube
  → p3-publish（双链齐 → published → 合 episode PR）→ p3-publish-report（HTML + 同步 Google Drive）→ 清临时确认
  → p3-archive（满 7 天）
```

任意一步都可以停。最终导出唯一入口是 `tools/assemble/final_export.py --confirmed`（不单独烧字、不对成片补跑响度）。
