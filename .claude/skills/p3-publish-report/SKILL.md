---
name: p3-publish-report
description: 发布报告。published 且复盘日志拷完后立刻做，只出一张可打开的单屏 HTML。不要等用户说「给我报告」或「给我task的报告」。用户要报告时也只用本 skill。不写双链、不合 PR、不清临时。
---

# 发布报告

`p3-publish` 写完 `published`、试过合 episode PR、复盘拷完之后立刻做。不要等用户要报告。只交这一张 HTML。不要另写 Markdown，不要在聊天里再铺一张表。

未 `published` 或复盘还没拷：停，先走 `/p3-publish`。本 skill 不写链接、不合 PR、不删文件。

## 不要做的事

- 不要编秒。没有据就写「约」或「缺日志」
- 不要把旁路核对片算进官方成片
- 不要加开场段、使用说明、时区说明
- 不要让整页滚动

## 证据

时间一律 Asia/Shanghai。优先 `logs/timeline.txt` 和 `logs/failures.md`（媒体目录或已拷上的复盘）。缺了或不完整，再用文件 birth/mtime、ffmpeg 日志、git commit。日志时间与成片 mtime 不一致时，用文件/编码时间，在该格写「日志后写」。

各 stage 当时应已把开始、结束、耗时、成功或失败写入 `logs/timeline.txt`，失败另记 `logs/failures.md`（`p3-episode`）。没写就标缺日志，不要回补编造。

墙钟是起止时刻之差，不是表里耗时相加。制作段到最终导出为止，发布段从打包到 published/PR。

## 写到哪

只写文本 HTML。浏览路径若已是长期目录的链接，写一处。两处 `INDEX.md` 补一行 `publish-report.html`。

- 长期：`/cursor/stores/store-96d3cec6-b662-4113-b5c5-90eebd57a3c8/running-retrospect/<YYYY-MM-DD-slug>/publish-report.html`
- 浏览：`/workspace/running-retrospect/<YYYY-MM-DD-slug>/publish-report.html`

聊天里只给路径。清临时清单仍由 `/p3-publish` 列，等人确认。

## 页面

一屏看完。白底黑字，无卡片、阴影、图标。整页不滚动；阶段行放不下时只滚阶段表。按骨架填实，不要加节。空单元格写成「缺日志」，不要留骨架里的占位。

1. 一行：标题、`published`、episode PR 链接。已合写 hash 和时间，未合写未合
2. YouTube、Bilibili、抖音。抖音空着写「空」，不挡
3. 官方审片预览对官方成片（同一条时间轴上的两次编码）：墙钟、片长、codec/profile、编码含（字幕 / 响度 / 封面或叠层，有或无）、大小。页上写明不是同一次编码。旁路审片（例如带叠层的核对片）另起一行。单段 HUD preview 不是这两行
4. 阶段表，列名只能是 `开始 | 步骤 | 耗时 | 结果`。覆盖 scaffold、ingest、鞋、封面、HUD（重做或睡眠中断发生过就各一行）、assemble/预览、字幕、最终导出、打包、B 站、YouTube、published/PR。失败的尝试留在表里，结果写「失败」
5. 墙钟：制作段 vs 发布段
6. 坑。没有写无
7. 还欠：抖音短链、清临时确认、未合的工具 PR、字幕等。没有写无

```html
<!DOCTYPE html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>标题</title>
<style>
  html, body { margin: 0; height: 100%; }
  body {
    box-sizing: border-box;
    height: 100vh;
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    overflow: hidden;
    color: #111;
    background: #fff;
    font: 12px/1.3 ui-sans-serif, system-ui, sans-serif;
  }
  h1 { margin: 0; font-size: 14px; font-weight: 600; }
  p, table { margin: 0; }
  a { color: inherit; }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: 1px 8px 1px 0; text-align: left; vertical-align: top; font-weight: 400; }
  th { border-bottom: 1px solid #111; }
  td { border-bottom: 1px solid #e6e6e6; }
  .stages { flex: 1; min-height: 0; overflow: auto; }
</style>
<h1>标题 · published · PR 链接 · hash · 时间</h1>
<p><a href="">YouTube</a> · <a href="">Bilibili</a> · 抖音 空</p>
<p>预览和成片不是同一次编码</p>
<table>
  <tr><th>文件</th><th>墙钟</th><th>片长</th><th>codec/profile</th><th>编码含</th><th>大小</th></tr>
  <tr><td>官方审片预览</td><td></td><td></td><td></td><td></td><td></td></tr>
  <tr><td>官方成片</td><td></td><td></td><td></td><td></td><td></td></tr>
</table>
<div class="stages">
<table>
  <tr><th>开始</th><th>步骤</th><th>耗时</th><th>结果</th></tr>
</table>
</div>
<p>墙钟 制作 … · 发布 …</p>
<p>坑 …</p>
<p>还欠 …</p>
</html>
```
