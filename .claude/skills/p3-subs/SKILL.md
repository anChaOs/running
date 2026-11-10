---
name: p3-subs
description: 字幕支路：faster-whisper large-v3-turbo 转写，忠于原句；人改字后 force_align → check_subs，确认后 subs: done；再写简介、抖音文案与 B 站/YouTube 标签进 plan.md。可与响度并行。默认只调 tools/subs 脚本。用户说字幕、转写、whisper、对口型、改字幕时用。没有成片先走 p3-assemble。
---

# 字幕（忠于原句）

识别稿只提供时间和草稿。**校正不是润色。** 字必须跟嘴里说的走；切条只断开，不改字。切条/对齐/质检算法在 `tools/subs/`；本 skill 管编排、人改字门、切条易错扫、简介/抖音文案/标签。

**读源码门槛：** 默认只调脚本看退出码。只有改算法、排错、或解释「为什么这么切」时才打开 `.py`。

## 流水线

1. 转写 + 初稿：`tools/subs/draft_subs.py`（词级时间；专名表当提示）。词级缓存和原始初稿留在媒体目录 `asr/`，不要覆盖
2. **校正**：只做下面「可以做」，绝不做「不能做」；交稿前做同音字扫描
3. **切条**：由 `draft_subs` 产出；agent **不重跑切条算法**。字一个都不改，**不对口型**
4. **自检切条（必做，交用户前）**：对照「切条易错」逐条扫，只改切分、不改嘴里说的字
5. 写 `subtitles.txt`，立刻停，等人手抽听改字
6. 用户说改好了之后：**只改时间、不改字**。`force_align.py` → `check_subs.py` → 硬失败行给人听 → **用户确认**后才写 `subs: done`，再生成媒体目录 SRT

## 校正：可以做

1. **明显识别错误**。例如专有说法被听错：月跑量、破三、10×1km、配速、心率；同音错字；口播卡能核对的名字。没听清就留 ASR 原文或标「听不清」，不要猜。
2. **繁体改简体。** `draft_subs.py` 已用 opencc 转简体；交稿前仍扫一遍繁体形。不要为此换 tiny/small。
3. **同音字扫描。** 交稿前按意思过一遍同音、近音字：寄/计、帧/针、托管/脱管、处于/属于、的/得/地、在/再、做/作、象/像。专名按本期 `episode.md` 的专名表写，大小写、空格跟表一致。

## 校正：绝不能做

1. **换一种表达。** 不要把口语改成更顺、更短、更书面的说法。不要用 `talk.md` / `script.md` 重写。
2. **压缩语句信息。** 指代、限定、程度、口头禅只要是说出来的，都要留。包括但不限于：「这点」「一些」「什么」「完全」「其实」「倒是」「大概」「左右」「足够的」。
3. **自己加括号注释。** agent 不要往字幕里加没说出口的（…）补充；要解释写进简介。
   **但用户手改时加的括号是屏幕注释，必须原样保留**（如「去打魔兽世界（私服）」「行（忘记说啥了）」）：回写媒体目录的 SRT、重切条、force_align 时都不许删。`check_subs.py` 报「括号」时先看是不是用户写的；是就保留。

不确定是不是错字，就保留原句。缺一句宁可空着等人手补，也不要为了通顺而改写。

### 反例

| 错误做法 | 错在哪 |
| --- | --- |
| 跑中随口报的配速、体感，整句删掉 | 信息被丢掉 |
| 长口语收成书面短句 | 指代和原表达被压缩 |
| 「完全」「什么」「其实」「大概」被润掉 | 口头禅也是原句 |

正确做法：原句留下；要断开就只改切分，不改字。

## 前置

需要 `YYYY-MM-DD-run-final.mp4`。没有则先 `/p3-assemble`。**不要等响度。** 转写听成片一条，时间就是成片轴。只改字不重转写。

依赖（一次）：`.venv/bin/pip install -r tools/subs/requirements.txt`。Apple Silicon 上 pip 直接装，CPU 跑。模型首次运行自动从 ModelScope 拉到 `~/Movies/running-content/.models/faster-whisper-large-v3-turbo/`（约 1.6 GB），不连 Hugging Face。

专名表：`episode.md` 里写一行 `专名：Personal Agent、HUD、……`。只当识别提示纠拼写，不能拿来改用词。`p3-topic` 建期时就该写好；转写时脚本自动读。

制作期成片固定 `YYYY-MM-DD-run-final.mp4`。仓库只留 `subtitles.txt`；外挂 SRT 写到媒体目录，不提交。烧字 ASS 在 `p3-burn`。

## 不要做的事

- 不要用 `talk.md` / `script.md` 估时间，也不要用它们改口播用词
- 不要在字幕校准前写简介，也不要用 `talk.md` 写简介
- 不要自造第二套切条/对齐规则；也不要为跑流程去 Read `tools/subs/` 源码（改算法 / 排错 / 解释切法除外）
- 不要把一段识别的起止按字数均分给几条字幕，也不要手填等步长的时间。对不上的条留给 `force_align.py` 报出来，人听了再定
- 不要用 tiny / small；只用 large-v3-turbo
- 不要在这里烧字

## 转写 + 初稿

`--audio` 直接给成片 mp4 即可。不传 `--prompt` 时自动读 `--txt` 同目录 `episode.md` 的「专名：」一行。**先把专名表写进 `episode.md` 再转写**；临时不要提示用 `--prompt ""`。

```bash
.venv/bin/python tools/subs/draft_subs.py \
  --audio ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  --txt episodes/YYYY-MM-DD-slug/subtitles.txt
```

转写后脚本会按专名表统一英文专名大小写/空格并打印清单；中文同音字仍按上面「同音字扫描」人工过。

产物：`asr/*.words.json`、`asr/*.draft.srt`（不要覆盖）、`subtitles.txt`。txt 已存在时脚本拒绝覆盖；要重来加 `--force`。

## 写字幕稿

只写 `episodes/YYYY-MM-DD-slug/subtitles.txt`。这是仓库里唯一的字幕稿。外挂 SRT 在对口型确认后生成；烧字 ASS 在 `p3-burn`。

- **单行**，一条字幕不要写成两行显示。横屏底栏还有 HUD，两行会抢位置
- 时间覆盖这些字对应的识别片段，不要为了「一个完整意思」把后面的话并进来

## 切条易错（交用户前必扫）

这是 **agent 人工职责**（脚本漏网或语义判断）。对照下面逐条改切分，不改嘴里说的字。改完切分后若已对过口型，再跑 `force_align`。

1. **不要把量词/后缀甩到下一行。** 「18-19」+「度了」→「18-19度了」；「2055」+「几」→「2055几」。单位、概数尾巴（度/几/公里/分/秒/% 等）跟它所修饰的数字同一条。
2. **优先短语边界。** 「太能冲了刷新了自己的PB」→ 两条：「太能冲了」/「刷新了自己的PB」。一句里两个完整谓语，宁可拆开。
3. **代词贴下一句主语。** 「之后的表现吧我 / 昨天…」错；对的是「看一下之后的表现吧」/「我昨天在看直播的时候」。
4. **语义单元别拆开。** 「精神 / 图腾吧」应并成「精神图腾吧」；双音节词组、专名、固定搭配同一条。
5. **用户点名重切后：** 改 txt 切分 → `force_align.py` → `check_subs.py` → `txt_to_subs.py --media-dir auto`。成片仍叫 run-final 时，脚本另拷 `YYYY-MM-DD-run-final.srt` 供 IINA。
6. **冷开场 prepend：** 以 `p3-assemble`「冷开场」为准。改 `subtitles.txt`（body +offset，或重抽 wav 再 `force_align`），文首补冷开场几条，再生成媒体 SRT。

txt 一行一条，时间是成片轴：

```text
0:00:00.00–0:00:02.44  大家好，我是安超
```

原始识别留在 `asr/*.words.json` 和 `asr/*.draft.srt`，不要覆盖。

## 停下来，等人手改字

自检切条做完、写完 `subtitles.txt` 之后 **立刻停**。不要对口型、不要烧字幕、不要写简介。第一稿时间只是识别的词级时间，不是口型。

```bash
open -a TextEdit episodes/YYYY-MM-DD-slug/subtitles.txt
```

- 这一轮用户**抽听核对、改错字**即可；优先改 `subtitles.txt`，时间不要动。保持单行。

没说改好之前，`assets.md` 写 `subs: waiting-review`。

## 改好字之后：对口型

用户说「改好了」之后：

1. **对口型**（只改时间；口播用词不改）：

   ```bash
   .venv/bin/python tools/subs/force_align.py \
     --txt episodes/YYYY-MM-DD-slug/subtitles.txt \
     --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav
   ```

   - 对齐前若发现切条问题，先按「切条易错」改切分，再对齐。
   - 脚本列出的 `interp` / `unanchored` 必须对着成片听，手改 txt 时间。
   - **质检门：**

     ```bash
     .venv/bin/python tools/subs/check_subs.py \
       --subs episodes/YYYY-MM-DD-slug/subtitles.txt \
       --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav
     ```

     **机器过门 ≠ 可以写 `subs: done`**：硬失败行必须给人听。漏盖若是路人说话或删掉的磕巴，人听过确认后在回复里说明。用户写的括号注释保留。
   - 对完扫一遍：单行；用词跟口播；没有被改写成另一种说法。
   - preview 时长变了（重渲 HUD），对着新成片重抽 wav、重跑这一步。

`check_subs.py` 机器过门之后，把硬失败行列给人；**用户确认「改好了 / 可以了」之后**，`assets.md` 才改成 `subs: done`，`episode.md` 的 `status` 改为 `edited`。agent 不得自行写 `subs: done`。

然后生成外挂（对齐会改时间，不要提前生成）：

```bash
.venv/bin/python tools/subs/txt_to_subs.py \
  --txt episodes/YYYY-MM-DD-slug/subtitles.txt --media-dir auto
```

更新媒体目录的 `subtitles.srt`。成片仍是 `YYYY-MM-DD-run-final.mp4` 时，脚本另拷同名 `.srt`，IINA 会自动挂。改名并移进 `upload/` 后，外挂仍是 `subtitles.srt`，不会变成标题同名。

然后才写简介：读校准后的 `subtitles.txt`，短句总结本期实际说了什么，写入该期 `plan.md` 的简介栏。不要按 `talk.md` / 选题卡写，不要推理，不要「这期不是 xxx」。拍前 plan 里若已有简介占位，用字幕摘要覆盖摘要那一段。已发布的旧期不要回改。简介第一行固定是 `个人视频制作来自：https://github.com/anChaOs/running`，然后才是摘要。大多数期没有「参考」，只写摘要，不要留空标题。口播里明确引用了论文、视频、数据时，才在摘要后另起「参考」：只写出处，不写实验结果。论文写作者、年份和 DOI。视频优先用当前平台的地址：B 站简介用 B 站链接，YouTube 简介用 YouTube 链接；YouTube 没有那条，就贴 B 站链接。没念到的不列。摘要两个平台相同，有参考时参考按平台分开。

**抖音作品描述**写入该期 `plan.md`「抖音」栏：
- **极致压缩**：两三短句说清本期在干嘛即可；不要 GitHub 行、不要分段长摘要、不要「参考」。
- **话题（最多 5 个）**：写成「建议话题」清单（不要可粘贴的 `#xxx` 整行）。尽量贴合国内抖音跑步圈热门标签，再按本期换贴题词。禁止把「破三实验室」等频道名当话题。宁缺毋滥，**不超过 5 个**。

**标签**写入该期 `plan.md`「## 标签」栏（与简介、抖音同一拍；拍前若无占位则新建整节）。仍读校准后的 `subtitles.txt`，不要按 `talk.md` / 选题卡硬套，也不要抄旧期默认串。已发布旧期不要回改。

格式与早期期（如 `2026-09-20-watch-load-three`）一致，写成：

- 节标题：`## 标签`
- 其下「B 站（5–8 个，不要堆）：」+ 一个 `text` 代码块，内容形如：`#跑步 #马拉松 #跑步日常 …`（空格分隔、带 `#`）
- 再「YouTube 标签：」+ 一个 `text` 代码块，内容形如：`跑步, 马拉松, 跑步日常, …`（逗号分隔、不带 `#`）

规则：
- **B 站**：**5–8** 个；空格分隔、带 `#`（如上）。投稿时 `/p3-bilibili` 会去掉 `#` 再逗号拼给 `--tag`。
- **YouTube**：**5–8** 个；**逗号分隔**、不带 `#`。
- 两边都要优先**重点、热点**（跑步圈常搜、常点的词），再按本期字幕补 1–3 个贴题词；**宁精勿冷门**，不要堆小众专名、冷门缩写或一期一过的梗。
- 禁止把「破三实验室」等**频道名**当标签；「破三」这类主题词可用。
- 抖音仍 ≤5；B 站 / YouTube **不受抖音 5 条上限**，但也不要超过 8。

## 完成后

分两段说，不要把「等人改」和「对口型」混在一次里。

**刚写完稿（`waiting-review`）**

立刻停。不要对口型、不要烧字幕、不要写简介。说明切条已自检。

> 切条已按易错规则扫过。这一轮抽听核对、改错字即可。优先动 `episodes/YYYY-MM-DD-slug/subtitles.txt`。时间先别动。改好了直接发：
>
> `改好了`

**用户说改好了**

对口型、质检；用户确认后 `txt_to_subs.py --media-dir auto` 更新媒体 SRT。简介 / 抖音文案 / 标签写入 `plan.md`。IINA 审片（不要推荐 ffplay）。**不要自己执行这条命令**：发给用户，用户同意或自己开：

```bash
iina --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

> 下一步：响度齐了走 `/p3-burn`。还要 60–90 秒短视频才提 `/p3-jianying`。
