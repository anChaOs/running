---
name: p3-subs
description: 用 faster-whisper large-v3-turbo 对着成片转写口播（词级时间，专名表只纠拼写），只纠明显错字和显著卡顿，再按标点和词间停顿切成单行短条 SRT。忠于原句，不改写、不压缩。写完先停，等人手改字。改好后用 force_align.py 强制对齐时间，check_subs.py 机器过门后仍须人听硬失败行，用户确认才写 subs: done。对口型完成后才按字幕写简介。从 2026-10-29 起最终成片默认烧 ASS；校对期仍外挂 SRT。用户说字幕、转写、whisper、对口型、改字幕时用。不要用 talk.md 估时，不要整段均分时间，禁用 tiny/small。没有成片先走 p3-assemble。
---

# 字幕（忠于原句）

识别稿只提供时间和草稿。**校正不是润色。** 字必须跟嘴里说的走；切条只断开，不改字。

发布默认**烧进成片**（从 2026-10-29 Fatmax 期起）：定稿 force_align 后生成 `subtitles.ass`，由 `p3-assemble --ass` 烧入最终片。校对期（waiting-review）仍外挂 SRT 给人改字/审片。平台可另挂 `subtitles.srt`（B 站创作中心只收 SRT）。单行、字数、停顿和词组边界见「写 SRT / txt」；脚本参数见「转写 + 初稿」。不要把字幕轨 mux 进 mp4（平台转码会丢掉）。

## 流水线

1. 转写 + 初稿：`tools/subs/draft_subs.py`（词级时间；专名表当提示）。词级缓存和原始初稿留在媒体目录 `asr/`，不要覆盖
2. **校正**：只做下面「可以做」，绝不做「不能做」；交稿前做同音字扫描
3. **切条**：脚本按下方「转写 + 初稿」的规则切好。字一个都不改，**不对口型**
4. **自检切条（必做，交用户前）**：agent 必须对照下方「切条易错」**逐条**扫初稿（代词归属、双谓语、语义单元、量词/后缀孤儿等），只改切分、不改嘴里说的字；能并的并回去，该拆的拆开。用户到手后**只需抽听核对**，不要把第一轮切条扫漏推给用户。
5. 写 `subtitles.srt` + `subtitles.txt`，立刻停，等人手抽听改字
6. 用户说改好了之后：**只改时间、不改字**。`force_align.py` 强制对齐 → `check_subs.py` 机器过门 → 列出硬失败行给人听 → **用户确认「改好了 / 可以了」之后**才写 `subs: done`、回写 SRT。外挂拷到成片旁边。比例过门本身不够。

## 校正：可以做

1. **明显识别错误**。例如专有说法被听错：月跑量、破三、10×1km、配速、心率；同音错字；口播卡能核对的名字。没听清就留 ASR 原文或标「听不清」，不要猜。
2. **显著卡顿的语气词**。只删明显磕巴，例如连续重复的「那个那个」「就是就是」「嗯——嗯」。
3. **繁体改简体。** whisper 的中文词表简繁混用，可能整段出繁体（訓練、失敗、會長）。`draft_subs.py` 已用 opencc 转简体；交稿前仍扫一遍 `別內專發經後這們為業裏裡麼亞` 这类繁体形。不要为此换 tiny/small。
4. **同音字扫描。** 交稿前按意思过一遍同音、近音字：寄/计、帧/针、托管/脱管、处于/属于、的/得/地、在/再、做/作、象/像。专名按本期 `episode.md` 的专名表写，大小写、空格跟表一致。

## 校正：绝不能做

1. **换一种表达。** 不要把口语改成更顺、更短、更书面的说法。不要用 `talk.md` / `script.md` 重写。
2. **压缩语句信息。** 指代、限定、程度、口头禅只要是说出来的，都要留。包括但不限于：「这点」「一些」「什么」「完全」「其实」「倒是」「大概」「左右」「足够的」。
3. **自己加括号注释。** agent 不要往字幕里加没说出口的（…）补充；要解释写进简介。
   **但用户手改时加的括号是屏幕注释，必须原样保留**（如「去打魔兽世界（私服）」「行（忘记说啥了）」）：回写 SRT、重切条、force_align、同步外挂时都不许删、不许改成别的符号。`check_subs.py` 报「括号」时先看是不是用户写的；是就保留，回复里说明「括号为用户注释，已保留」。

不确定是不是错字，就保留原句。缺一句宁可空着等人手补，也不要为了通顺而改写。

### 反例

| 错误做法 | 错在哪 |
| --- | --- |
| 跑中随口报的配速、体感，整句删掉 | 信息被丢掉 |
| 长口语收成书面短句 | 指代和原表达被压缩 |
| 「完全」「什么」「其实」「大概」被润掉 | 口头禅也是原句 |

正确做法：原句留下，太长就在词边界切成两条。

## 前置

需要 `YYYY-MM-DD-run-final.mp4`。没有则先 `/p3-assemble`（**可先 `--no-loudness-fix` 出可对字幕版**；响度链放到本 skill 停在 waiting-review 之后，与用户校对并行，见 `p3-assemble`「流程顺序」）。转写听成片一条，时间就是成片轴。写完稿等人手改字，改好了再对口型。只改字不重转写。

依赖（一次）：`.venv/bin/pip install -r tools/subs/requirements.txt`。Apple Silicon 上 pip 直接装，CPU 跑。模型首次运行自动从 ModelScope 拉到 `~/Movies/running-content/.models/faster-whisper-large-v3-turbo/`（约 1.6 GB），不连 Hugging Face。Silero VAD 随 faster-whisper 包自带，不用另下。30 分钟成片在 8 核 CPU 上实测：整条转写约 4 分钟（结果缓存到 `asr/*.words.json`，三个脚本共用；换了 `--prompt` 或成片会重转），对齐时的短窗重听再约 5～9 分钟，质检复用缓存几秒钟。

专名表：`episode.md` 里写一行 `专名：Personal Agent、HUD、……`（本期口播会说到的产品名、人名、英文术语）。它只当识别提示纠拼写，不能拿来改用词。`p3-topic` 建期时就该写好（口播卡里的人名、品牌、术语），转写时脚本自动读，不用再手抄。

## 成片路径（制作期 vs 改名后）

- **制作期**：成片固定为 `YYYY-MM-DD-run-final.mp4`；工作字幕 `subtitles.txt` / `subtitles.srt`；对口型 wav 跟成片名。制作阶段可另拷 `YYYY-MM-DD-run-final.srt` 方便 IINA 同名挂载。
- **upload-ready 改名后**：只把成片原地改名为标题原文 + `.mp4`（如 `芝加哥马拉松 | 结果如何？.mp4`）。**外挂始终叫 `subtitles.srt`**，不要改成与标题同名的 `.srt`。
- 改名后若再对齐 / 审片：视频用标题名 `.mp4`，字幕显式 `--sub-file=subtitles.srt`（或 IINA 手动挂）。不要让工具去找「和成片名同名的 `.srt`」。

## 不要做的事

- 不要用 `talk.md` / `script.md` 估时间，也不要用它们改口播用词
- 不要在字幕校准前写简介，也不要用 `talk.md` 写简介
- 不要只靠 VAD 停顿切条；停顿只有落在词组边界上才是切口
- 不要把一段识别的起止按字数均分给几条字幕，也不要手填等步长的时间（如每条 0.99s、间隔 0.06s）。对不上的条留给 `force_align.py` 报出来，人听了再定
- 不要用 tiny / small；只用 large-v3-turbo

## 转写 + 初稿

`--audio` 直接给成片 mp4 即可：脚本自动抽 16 kHz 单声道到媒体目录 `asr/YYYY-MM-DD-run-final.wav`（已有且比成片新就复用）。三个脚本（draft / force_align / check）不传 `--prompt` 时都自动读 `--txt` 同目录 `episode.md` 的「专名：」一行，**同一份提示 → 同一个词级缓存**，后两步不会因为手抄专名差一个字而整条重转（约 4 分钟）。所以**先把专名表写进 `episode.md` 再转写**；临时不要提示用 `--prompt ""`。

```bash
.venv/bin/python tools/subs/draft_subs.py \
  --audio ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4 \
  --txt episodes/YYYY-MM-DD-slug/subtitles.txt
```

转写后脚本按专名表**只统一英文专名的大小写和空格**（coros→COROS、personal agent→Personal Agent、vo2 max→VO2max），并打印「专名拼写统一」清单；中文专名不做模糊替换，同音字仍按上面「同音字扫描」人工过。

产物：`asr/*.words.json`（词级缓存，对时和质检共用）、`asr/*.draft.srt`（原始初稿，不要覆盖）、`subtitles.txt`。txt 已存在时脚本拒绝覆盖，防止冲掉人改的字。

初稿切条：只在 jieba 分词的词边界上断，连着的英文词（Personal Agent）不拆。先在词间停顿处断（≥1.2s 必断，≥0.5s 自然断），再看标点；超长时在整句里找**最长的停顿**切，不要只把最后一个词或几个字拆走。停顿后面接「的 / 了」或前面停在「的 / 一个」上的不算切口。再按约 16 字、4.5 秒的上限在词边界切。≤2 字的短条并到停顿更短的一侧。数字+单位/概数尾巴会确定性合并，漏网的按「切条易错」人眼扫。

## 写 SRT / txt

写到 `episodes/YYYY-MM-DD-slug/`：

```text
subtitles.srt   # B 站 / YouTube 外挂
subtitles.txt   # 给人改的稿
```

- **单行**，一条字幕不要写成两行显示。横屏底栏还有 HUD，两行会抢位置
- 一行大约 8～16 个汉字；超过就在词边界拆成下一条，**拆开而不是改写成更短的句子**
- 一条大约 1～4 秒，读速不超过每秒 7 字；跟嘴走，不要一条挂十几秒
- 同一句可以连着几条，不必合成一条超长的。**停顿优先**，且必须在词组边界上：超长时在整句**最长的停顿**处切，不要只拆走最后一个词；停顿差不多长才看标点。短句首（OK / 今天 / 一种）前面停得比后面久，就放到下一条开头
- 单字条只留真正独立的词（「行」「好」）；其余并到邻条
- 时间覆盖这些字对应的识别片段，不要为了「一个完整意思」把后面的话并进来
- 词组、双音节词、英文专名都从词边界断开，例如不要切成「配 / 速」。下一行只剩「了」「的」「量」，或能和上一行末字拼成词，就是切错了。交稿前扫一遍切口。看的是有没有把一个词组拆开，不是看字数：
  - **该并**：下一条是在补完上一条的半句。上一条停在「的」「一个」「就」「比较」这类挂着下文的字上；下一条以「的」「了」「里」「中的」开头；或下一条只是上一条的宾语、补语、量词后面的名词，例如「停了 / 三天」「有一个 / 变化」「看了 / 他的视频」。量词/后缀孤儿、代词跨句、语义单元被拆等，见下方「切条易错」。
  - **不用并**：一两个字本身是完整的词，前后真有停顿，单独读也通，例如「所以」「然后」「这个」「行」；说了一半改口重说的，也各留一条。
  - 并完超过一行（约 16 字）或四五秒，就在别的词组边界重切，不要切回词中间。宁可一行稍过 16 字，也不把一个词拆开。
- SRT 没有位置信息，平台会贴底栏，可能压 HUD；公开前开 CC 看一眼

## 切条易错（交用户前必扫）

对照下面逐条改切分，不改嘴里说的字。改完切分后若已对过口型，再跑 `force_align`。

1. **不要把量词/后缀甩到下一行。** 「18-19」+「度了」→「18-19度了」；「2055」+「几」→「2055几」。单位、概数尾巴（度/几/公里/分/秒/% 等）跟它所修饰的数字同一条。脚本会确定性合并一部分，仍须人眼扫漏网。
2. **优先短语边界，不要只看字数。** 「太能冲了刷新了自己的PB」→ 两条：「太能冲了」/「刷新了自己的PB」。一句里两个完整谓语，宁可拆开。
3. **代词贴下一句主语。** 「之后的表现吧我 / 昨天…」错；对的是「看一下之后的表现吧」/「我昨天在看直播的时候」。「我」起新句时，不要挂在上一句尾巴上。
4. **语义单元别拆开。** 「精神 / 图腾吧」应并成「精神图腾吧」；双音节词组、专名、固定搭配同一条。
5. **用户点名重切后：** 改 txt 切分 → `force_align.py` → `check_subs.py` → 同步外挂：仓库与媒体目录的 `subtitles.srt`（上传用这个名）。制作审片阶段可另拷 `YYYY-MM-DD-run-final.srt` 方便 IINA 同名挂载；**不要**改成标题名。
6. **冷开场 prepend（成片前加 bumper）时：** 截取/硬切/备份等以 `p3-assemble`「冷开场」为准。字幕侧只记：prepend 后 body 全部 +offset（或从新成片重抽 wav 再 `force_align`），文首补上冷开场几条；同步仓库与媒体 `subtitles.srt`。

txt 一行一条，时间是成片轴：

```text
0:00:00.00–0:00:02.44  大家好，我是安超
```

原始识别留在 `asr/*.words.json` 和 `asr/*.draft.srt`，不要覆盖。

## 停下来，等人手改字

自检切条做完、写完 SRT/txt 之后 **立刻停**。不要对口型、不要烧字幕、不要写简介。第一稿时间只是识别的词级时间，不是口型。

把 txt 路径发给用户；用户在 Mac 上要看稿时用文本编辑打开（不要开播放器）：

```bash
open -a TextEdit episodes/YYYY-MM-DD-slug/subtitles.txt
```


- 切条已按「切条易错」自检过。这一轮用户**抽听核对、改错字**即可；优先改 `subtitles.txt`，时间不要动。保持单行、别写太长。

没说改好之前，`assets.md` 制作状态写 `subs: waiting-review`。

## 改好字之后：对口型

用户说「改好了」之后，先回写 SRT，再对口型。

1. 若动了 txt：

   ```bash
   .venv/bin/python tools/subs/txt_to_subs.py \
     --txt episodes/YYYY-MM-DD-slug/subtitles.txt --media-dir auto
   ```

   覆盖同目录 `subtitles.srt`；`--media-dir auto` 顺手拷到媒体目录 `subtitles.srt`，成片还叫 `run-final.mp4` 时再拷一份同名 `.srt`（改名后不拷，外挂始终是 `subtitles.srt`）
2. **对口型**（只改时间；口播用词不改）：
   - 对齐前先按「写 SRT / txt」的切口规则扫一遍，词组被拆成两条的先并回去。这是修切条，不是改嘴里说的字。
   - 强制对齐（定稿文字为准，脚本不改字）：

     ```bash
     .venv/bin/python tools/subs/force_align.py \
       --txt episodes/YYYY-MM-DD-slug/subtitles.txt \
       --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav
     ```

     做法：定稿文字按字对到词级识别上，只用连续对上的字当锚点；对不上的几条在前后锚点之间切短窗、用这几条原文当提示重听；还对不上，短窗（≤10s）内按人声时长比例分，标 `interp`；窗更长就保留原时间，标 `unanchored`。最后用 Silero VAD 咬点：入点贴开口、略早 0.1s（气口后的短人声「嗯」「那」不吸附）；出点盖住说完再挂约 0.2s，只往后延不往前缩；**出点盖住说完优先于不重叠**——冲突时推迟下一条入点，绝不砍上一条出点造成早收；共享人声岛按词级边界切开；句间留白约 0.22s；最短约 1 秒。
   - 脚本列出的 `interp` / `unanchored` 条必须对着成片听，手改 txt 时间。
   - **质检门**（硬失败行照列；过门按比例，对不上的条不进分母）：

     ```bash
     .venv/bin/python tools/subs/check_subs.py \
       --subs episodes/YYYY-MM-DD-slug/subtitles.txt \
       --audio ~/Movies/running-content/YYYY-MM-DD-slug/asr/YYYY-MM-DD-run-final.wav
     ```

     机器过门两层：① 比例——早收（出点比说完早 >0.3s）≤ 可核对条的 3%；漏盖（有正词人声却没字幕，连续 ≥0.5s）累计时长 ≤ 成片时长的 1%；挂静音（说完后还挂 >1s）≤ 可核对条的 3%。② 绝对硬门槛——严重早收（出点比说完早 >0.5s）条数必须为 0。超任一则退出码非 0（机器未过门）。**机器过门 ≠ 可以写 `subs: done`**：脚本仍逐条列出硬失败行，agent 必须给人听，确认前不要写 `subs: done`。对不上 / 噪声大的条不进比例分母，单独列出要人听。提醒：晚进 >0.3s、短于 1s、超过 7 字/秒、单字条、词组拆开、重叠、`\N`、括号（用户写的屏幕注释保留，agent 加的才删）。漏盖若是路人说话或删掉的磕巴，人听过确认后在回复里说明。
   - 对完扫一遍：单行；用词跟口播，没有被改写成另一种说法；没有 agent 自加的括号注释（用户写的括号原样还在）。
   - 规则不变：字出在嘴动时；**宁可早出，不能早收**；气口后的短人声（「那」「嗯」）不要钉成下一句入点；句间停顿留白。
   - 对着成片 `YYYY-MM-DD-run-final.mp4` 抽听，本地预览用 IINA；媒体目录放 `subtitles.srt`，制作阶段可另放同名 `YYYY-MM-DD-run-final.srt` 方便自动挂
   - 不要为对齐改字。只改 sidecar，不用重拼成片。preview 时长变了（重渲 HUD），对着新成片重抽 wav、重跑这一步。
   - 改完 txt 时间后跑 `txt_to_subs.py --media-dir auto` 回写 SRT 并同步媒体目录
3. 外挂拷到成片旁边（IINA 自动挂）：最后一次 `txt_to_subs.py ... --media-dir auto` 已经拷好，不用再手动 `cp`。
4. **烧字（最终片，从 2026-10-29 Fatmax 起默认）**：机器过门并把对齐后的 `subtitles.srt` 定稿后，从 SRT 生成 `episodes/.../subtitles.ass`，再跑 `assemble_episode.py --ass episodes/.../subtitles.ass`（保留响度链，不要 `--no-loudness-fix`）。无烧字成片先备份为 `YYYY-MM-DD-run-final-no-burn.mp4`。媒体目录同步 `subtitles.ass`；外挂 `subtitles.srt` / 制作期同名 `.srt` 仍保留供平台选用。可对字幕中间版（waiting-review）可以不烧；平台可另挂 SRT。

   **ASS Style（烧字默认，非 HUD）**
   - Font：`Source Han Sans SC Heavy`（文件 `SourceHanSansSC-Heavy.otf`；仓库有 `tools/hud/fonts/SourceHanSansSC-Heavy.otf` 可复用）
   - 1080p：`Fontsize=72`、`Outline=3`、`MarginV≈100`；单行底中，避开左栏 HUD
   - ASS `Fontname` 必须让 ffmpeg/libass **真选中** Heavy：Mac 把 otf **装入 `~/Library/Fonts`**（或配 FONTCONFIG）；**勿只靠 `fontsdir`**——CoreText 常落到 PingFang SC Regular，字重/字形不对
   - 校对期仍外挂 SRT；烧字是最终发布片默认，与 HUD 字体规则无关

`check_subs.py` 机器过门之后，把硬失败行和 `interp` / `unanchored` 条列给人听；**用户确认「改好了 / 可以了」之后**，`assets.md` 才改成 `subs: done`，`episode.md` 的 `status` 改为 `edited`。比例过门本身不够，agent 不得自行写 `subs: done`。烧字可在人听确认前后做，但最终发布片必须已烧。

然后才写简介：读校准后的 `subtitles.txt`，短句总结本期实际说了什么，写入该期 `plan.md` 的简介栏。不要按 `talk.md` / 选题卡写，不要推理，不要「这期不是 xxx」。拍前 plan 里若已有简介占位，用字幕摘要覆盖摘要那一段。已发布的旧期不要回改。简介第一行固定是 `个人视频制作来自：https://github.com/anChaOs/running`，然后才是摘要。大多数期没有「参考」，只写摘要，不要留空标题。口播里明确引用了论文、视频、数据时，才在摘要后另起「参考」：只写出处，不写实验结果。论文写作者、年份和 DOI。视频优先用当前平台的地址：B 站简介用 B 站链接，YouTube 简介用 YouTube 链接；YouTube 没有那条，就贴 B 站链接。没念到的不列。摘要两个平台相同，有参考时参考按平台分开。

**抖音作品描述（另栏，勿复用 B 站 / YouTube 长简介）** 同时写入该期 `plan.md` 的「抖音」栏：
- **极致压缩**：两三短句说清本期在干嘛即可；不要 GitHub 行、不要分段长摘要、不要「参考」。正文可整段粘贴。
- **话题（最多 5 个）**：在 `plan.md` 里写成「建议话题」清单（不含可粘贴的 `#xxx` 整行）。**尽量贴合国内抖音跑步圈热门标签**（如 跑步、马拉松、全马、半马、破三、跑步日常、跑步训练、配速、轻松跑、间歇跑、燃脂、乳酸阈），再按本期内容换进贴题词（赛事名、专名如 大迫杰、训练课型）。禁止把「破三实验室」等频道名当话题（系列名只用在标题里）。宁缺毋滥，**不超过 5 个**。
- **挂载方式**：用户在发布页点「#」/「话题」，搜词后从官方列表**点选**，变蓝才算挂上。整段复制 `#xxx` 常不变蓝（灰色＝未挂载）。已发作品可「更多 → 编辑作品」改话题。
- 标题与 B 站 / YouTube 同发；用户上传时从 `plan.md`「抖音」栏抄正文 + 手选话题。


## 完成后

分两段说，不要把「等人改」和「对口型」混在一次里。

**刚写完稿（`waiting-review`）**

立刻停。不要对口型、不要烧字幕、不要写简介。说明切条已自检。

> 切条已按易错规则扫过。这一轮抽听核对、改错字即可。优先动 `episodes/YYYY-MM-DD-slug/subtitles.txt`（换成当前期路径）。时间先别动。改好了直接发：
>
> `改好了`

**用户说改好了**

回写 SRT、对口型、拷到成片旁边，简介写入 `plan.md`。IINA 审片（不要推荐 ffplay）。**不要自己执行这条命令**：发给用户，用户同意或自己开：

```bash
iina --mpv-geometry=320x180-8+8 \
  ~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-final.mp4
```

小窗贴右上角。制作阶段若有同名 `YYYY-MM-DD-run-final.srt` 会自动挂；成片已按标题改名后，视频是标题名 `.mp4`，字幕仍用 `subtitles.srt`（`iina --mpv-sub-file=.../subtitles.srt` 或上传时手挂）。不要去找与标题同名的 `.srt`。

**先不要给发布流程。** 用户说「没问题了 / 可以发了」再给：从 `plan.md` 抄标题、封面句、简介。把生产成片 `YYYY-MM-DD-run-final.mp4` **原地改名**为标题原文 + `.mp4`。**只改成片名，不要改 SRT 文件名**；上传外挂始终用 `subtitles.srt`。**保留标题全部标点**，包括 `|`、`？`、空格等；**不要**把 `|` 换成 `-`，也不要另留一份 `run-final` 副本。上传成片 → 换封面 → 挂 `subtitles.srt`（B 站创作中心只收 SRT）→ 先不公开、开 CC → 再公开。不要替用户上传。`assets.md` 记 `upload: ready`；`episode.md` 的 `status` 仍为 `edited`，真正发完、两边链接齐了才改 `published`。

**抖音（第三平台，不挡 `published`）**
- 成片：用**已烧字幕**的标题名 `.mp4`（抖音不依赖外挂 SRT）。
- 文案：从 `plan.md`「抖音」栏抄正文，再按「建议话题」清单（≤5）在发布页点选变蓝；封面可用 `cover-1080x1440.jpg`（竖封面）或平台裁切。
- 用户发完后把分享短链（`https://v.douyin.com/…`）写入 `episode.md`「发布」栏「抖音：」。
- **抖音链接齐之后**：媒体目录**只保留一份成片**（标题名烧字幕 `.mp4`）；无字幕备份（`*-no-burn.mp4`，或芝马期这类仍叫 `YYYY-MM-DD-run-final.mp4` 的备份）进废纸篓。B 站 / YouTube 已发但抖音未发时，可暂留备份。


| 用途 | 文件 |
| --- | --- |
| 成片（上传用 = 生产成片） | 媒体目录里以标题命名的 `.mp4`（由 `YYYY-MM-DD-run-final.mp4` 原地改名） |
| 封面 | `cover-1920x1080.jpg` / `cover-4x3-1920x1440.jpg` / `cover-1080x1440.jpg` / `cover.jpg` |
| 外挂 | **`subtitles.srt`**（不要改成标题名；制作阶段可选保留 `YYYY-MM-DD-run-final.srt`） |

还要 60–90 秒短视频才提 `/p3-jianying`。两边链接齐之后，不要在这里另做一套，直接按「发布后清临时文件」。

### 发布后清临时文件

**真源在此。** 其它 skill / 文档只引用本节，不要另写一份保留/删除清单。

触发：用户说「发布完毕 / 发完了 / 已发布」之类，并且同时给了 **B 站 BV（或完整 B 站链接）** 和 **YouTube 链接**。顺序：

1. 写两边链接、`episode.md` 的 `status=published`
2. **立刻合并该期 episode PR 进 `main`**（squash；可删远程分支）；不要等用户再点合
3. 再按本节列清临时清单（体积）→ 用户确认 → 进废纸篓（禁止 `rm`）

媒体目录：`~/Movies/running-content/YYYY-MM-DD-slug/`。

#### 保留（KEEP）

| 保留 | 说明 |
| --- | --- |
| 原片 | `open-raw` / `run-*` / `close-raw`；若没有 `*-raw` 变体，则保留剪过的 `open` / `close` 当作原片 |
| 成片 | **仅一份**：以标题命名的最终烧字幕 `.mp4`；抖音发完后勿再留 `*-no-burn` / 额外 `run-final` |
| 字幕 | `subtitles.srt`（制作期可选的 `YYYY-MM-DD-run-final.srt` 可留）；烧字源 `subtitles.ass` 可留 |
| 封面 | `cover.jpg`、`cover-1920x1080.jpg`、`cover-4x3-1920x1440.jpg`、`cover-1080x1440.jpg` |
| 封面自拍原图 | 媒体目录里的自拍源照片（非 `cover-*.jpg`） |
| 数据 | FIT、`weather-hourly.json`、`stats-*.jpg` |

仓库 `episodes/` 里的字幕源稿、跑鞋账本一律不动。

#### 删除（DELETE）

缺了就跳过，不要报错停住：

| 删 | 说明 |
| --- | --- |
| `*-run-final-pre-*.mp4` | 拼片备份（冷开场前、修剪前等）；发布后不再需要回退 |
| `close-stats` 等渲染中间件 | 叠了数据的 close 中间件、其它可再生成的渲染产物 |
| 剪过的 `open` / `close` | **仅当**已有对应 `open-raw` / `close-raw` 时删；没有 `-raw` 则上面 KEEP 已要求保留 |
| `hud-renders/` | HUD preview / 透明层；可再跑 `p3-hud` |
| `asr/` | 转写中间产物 |
| `qc/` | 抽帧核对图 |
| `cover-candidates/` | 封面候选帧 |
| `cold-open/` | 冷开场中间件 |
| `*.bak`、`.DS_Store` | 备份后缀与系统垃圾 |

#### 流程（PROCESS）

1. **先列清单再动手。** 用 `du -sh` / `ls -lh` 列出拟删项与拟留项及体积，报给用户确认。用户没明确同意前不要删。
2. **进废纸篓，禁止 `rm`。** 在 macOS 上把确认要删的路径 **move 进废纸篓**（`mv … ~/.Trash/`，或已安装的 `trash` CLI）。不要用 `rm` / `rm -rf`。同名冲突时先改名再移入。
3. 清完把实际移入废纸篓的路径与腾出的体积报给用户。
4. 这里**不要**整夹归档或删掉整个媒体目录；满 7 天整夹搬走走 `p3-archive`。
