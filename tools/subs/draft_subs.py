#!/usr/bin/env python3
"""成片音频 → 字幕初稿（单行短条）。给人改字用，时间只是草稿。

faster-whisper large-v3-turbo 词级时间（专名表当提示，只纠拼写）。
切条顺序：停顿第一优先级——≥1.2s 必断，≥0.5s 自然断；强标点可断；≤2 字短条并到停顿更短的一侧；再确定性合并「数字+单位/概数尾巴」和少量固定搭配。
繁体统一转简体。不删字、不改写；校正交给人和 p3-subs 的规则。

产物：
  <wav>.words.json        词级识别缓存（force_align / check_subs 共用）
  <wav 同名>.draft.srt    原始初稿，不要覆盖
  --txt 指定的 subtitles.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subs_core as sc  # noqa: E402

HARD_CHARS = 20     # merge_short / merge_cut_fixes 合并上限
MIN_DUR = 1.0
NATURAL = 0.50      # 词间停顿 ≥ 这个且前面已够 MIN_SIDE 字：直接断（停顿第一优先级）
MIN_SIDE = 4        # 自然停顿切断时左侧至少留的字数
STRONG = re.compile(r"[。！？!?…]$")
PUNCT_ONLY = re.compile(r"^[，,。.！？!?、；;：:…\-—]+$")
# 数字后的单位 / 概数尾巴：不要拆到下一行（芝马期实踩：18-19|度了、2055|几）
UNIT_TAIL_HEAD = re.compile(
    r"^(度了|度|几|公里|千米|公斤|千克|米|分|秒|%|％|℃|°c|左右|多|来|倍)"
)
# 极少数固定搭配：上一 cue 收尾 + 下一 cue 起头 应并（保守，宁少勿滥）
COLLOC_PAIRS = (
    ("精神", "图腾"),
)


def clean_word(w: str) -> str:
    return sc.to_simplified(w).strip()


def to_tokens(words):
    """识别词（中文常是单字）→ 分词后的词组单元，只允许在词组边界切。"""
    import jieba  # noqa: PLC0415

    jieba.setLogLevel(60)
    chars: list[tuple[str, float, float, float]] = []
    for w in words:
        t = sc.to_simplified(w.w)
        n = max(len(t.strip()), 1)
        k = 0
        for ch in t:
            if ch.isspace():
                chars.append((" ", w.s, w.s, w.p))
                continue
            a = w.s + (w.e - w.s) * k / n
            b = w.s + (w.e - w.s) * (k + 1) / n
            chars.append((ch, a, b, w.p))
            k += 1
    text = "".join(c[0] for c in chars)
    toks = []
    pos = 0
    for piece in jieba.lcut(text, HMM=True):
        seg = chars[pos:pos + len(piece)]
        pos += len(piece)
        if not piece.strip():
            continue
        if PUNCT_ONLY.match(piece) and toks:
            toks[-1].w += piece  # 标点挂到前一个词上，当切口信号
            continue
        lead = " " if pos - len(piece) > 0 and chars[pos - len(piece) - 1][0] == " " and re.match(r"[A-Za-z0-9]", piece) else ""
        real = [c for c in seg if not c[0].isspace()]
        toks.append(sc.Word(real[0][1], real[-1][2], lead + piece, min(c[3] for c in real)))
    # 连着的英文词（Personal Agent、Grok Bot）当一个单元，不在中间切
    merged = []
    for t in toks:
        if merged and re.match(r"^\s?[A-Za-z0-9][A-Za-z0-9.\-]*$", t.w) and re.search(r"[A-Za-z0-9]$", merged[-1].w) \
                and t.s - merged[-1].e < 0.3:
            merged[-1] = sc.Word(merged[-1].s, t.e, merged[-1].w + (t.w if t.w.startswith(" ") else " " + t.w), min(merged[-1].p, t.p))
        else:
            merged.append(t)
    return merged


def text_of(ws) -> str:
    out = "".join(w.w for w in ws)
    out = re.sub(r"[，,。！？!?、；;：:…]+", " ", out)
    out = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def nchars(ws) -> int:
    return len(sc.norm("".join(w.w for w in ws)))


def _forbidden(ws, k) -> bool:
    """硬约束：数字+单位不拆；英文专名（连续英文词）不拆。"""
    a, b = sc.norm(clean_word(ws[k].w)), sc.norm(clean_word(ws[k + 1].w))
    if re.search(r"\d$", a) and UNIT_TAIL_HEAD.match(b):
        return True
    if re.search(r"[A-Za-z]$", a) and re.match(r"^[A-Za-z]", b):
        return True
    return False


def split_words(words) -> list[list]:
    cues: list[list] = []
    buf: list = []
    for w in words:
        if buf:
            gap = w.s - buf[-1].e
            # 长停顿一定断；自然停顿（≥NATURAL）且前面已够一句 → 也断
            if gap > 1.2 or (gap >= NATURAL and nchars(buf) >= MIN_SIDE and not _forbidden(buf + [w], len(buf) - 1)):
                cues.append(buf)
                buf = []
        buf.append(w)
        n = nchars(buf)
        if STRONG.search(clean_word(w.w)) and n >= 6:
            cues.append(buf)
            buf = []
            continue
    if buf:
        cues.append(buf)
    return merge_cut_fixes(merge_short(cues))


def merge_short(cues: list[list]) -> list[list]:
    """≤2 字的短条并到停顿更短的那一边（不是总并回上一条）：
    「开表了 ⟨0.6s⟩ OK ⟨0.15s⟩ 我们」→ OK 归下一条。两边停顿都 ≥0.6s 就留着。"""
    out = [list(c) for c in cues]
    i = 0
    while i < len(out):
        c = out[i]
        if nchars(c) > 2 or len(out) == 1:
            i += 1
            continue
        gp = c[0].s - out[i - 1][-1].e if i > 0 else 9.0
        gn = out[i + 1][0].s - c[-1].e if i + 1 < len(out) else 9.0
        opts = []
        if i > 0 and gp < 0.6 and nchars(out[i - 1]) + nchars(c) <= HARD_CHARS:
            opts.append((gp, -1))
        if i + 1 < len(out) and gn < 0.6 and nchars(out[i + 1]) + nchars(c) <= HARD_CHARS:
            opts.append((gn, 1))
        if not opts:
            i += 1
            continue
        _, d = min(opts)
        if d == 1:
            out[i + 1] = c + out[i + 1]
            del out[i]
        else:
            out[i - 1] = out[i - 1] + c
            del out[i]
            i -= 1
    return out


def _ends_with_number(text: str) -> bool:
    t = re.sub(r"[，,。！？!?、；;：:\s…]+$", "", sc.to_simplified(text).strip())
    return bool(re.search(r"\d$", t))


def _starts_with_unit_tail(text: str) -> bool:
    return bool(UNIT_TAIL_HEAD.match(sc.norm(text)))


def _colloc_join(a: str, b: str) -> bool:
    a_n, b_n = sc.norm(a), sc.norm(b)
    return any(a_n.endswith(left) and b_n.startswith(right) for left, right in COLLOC_PAIRS)


def merge_cut_fixes(groups: list[list]) -> list[list]:
    """初稿切完后再并一轮：数字+单位/概数尾巴；少量固定搭配。只并切分、不改字。"""
    if not groups:
        return groups
    out: list[list] = [groups[0]]
    for g in groups[1:]:
        prev = out[-1]
        a, b = text_of(prev), text_of(g)
        join = False
        if _ends_with_number(a) and _starts_with_unit_tail(b):
            join = True
        elif _colloc_join(a, b):
            join = True
        # 数字+单位允许略超 HARD_CHARS；搭配也给一点余量
        limit = HARD_CHARS + (4 if join else 0)
        if join and nchars(prev) + nchars(g) <= limit:
            out[-1] = prev + g
        else:
            out.append(g)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio", required=True, help="asr/YYYY-MM-DD-run-final.wav（16k 单声道）；也可直接给成片 .mp4，自动抽到 asr/")
    ap.add_argument("--txt", required=True, help="episodes/YYYY-MM-DD-slug/subtitles.txt")
    ap.add_argument("--prompt", help="专名表；不传就读 --txt 同目录 episode.md 的「专名：」一行；--prompt \"\" 不用提示")
    ap.add_argument("--model-dir", default=str(sc.DEFAULT_MODEL_DIR))
    ap.add_argument("--words-cache")
    ap.add_argument("--force", action="store_true", help="txt 已存在也覆盖（默认拒绝，防止冲掉人手改的字）")
    args = ap.parse_args()

    txt = Path(args.txt).expanduser()
    if txt.exists() and not args.force:
        raise SystemExit(f"{txt} 已存在。人手改过的字不要被初稿冲掉；确实要重来加 --force。")
    wav = sc.ensure_wav(Path(args.audio).expanduser())
    prompt = sc.resolve_prompt(args.prompt, txt)
    cache = Path(args.words_cache).expanduser() if args.words_cache else sc.default_cache(wav)
    words = sc.cached_words(wav, Path(args.model_dir).expanduser(), cache, prompt)
    groups = split_words(to_tokens(words))
    cues = []
    term_fixes: list[tuple[str, str]] = []
    for g in groups:
        t = text_of(g)
        if not t:
            continue
        t, fx = sc.fix_terms(t, prompt)
        term_fixes += fx
        a, b = g[0].s, g[-1].e
        if b - a < MIN_DUR:
            b = a + MIN_DUR
        cues.append(sc.Cue(round(a, 2), round(b, 2), t))
    for i in range(len(cues) - 1):
        if cues[i].end > cues[i + 1].start - 0.05:
            cues[i].end = max(cues[i].start + 0.3, cues[i + 1].start - 0.05)
    header = ["# 字幕初稿（单行短条；时间是成片轴，草稿，未对口型）", "# 这一轮只改字。改好后跑 force_align.py 对时间。"]
    txt.parent.mkdir(parents=True, exist_ok=True)
    sc.write_txt(txt, header, cues)
    draft = wav.with_suffix(".draft.srt")
    sc.write_srt(draft, cues)
    print(f"cues={len(cues)}\n写入 {txt}\n原始初稿 {draft}（不要覆盖）")
    if term_fixes:
        from collections import Counter
        print("专名拼写统一（按 episode.md 专名表，只改大小写/空格）：" +
              "；".join(f"{a}→{b}×{n}" for (a, b), n in Counter(term_fixes).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
