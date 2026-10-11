#!/usr/bin/env python3
"""成片音频 → 字幕初稿（单行短条）。给人改字用，时间只是草稿。

faster-whisper large-v3-turbo 词级时间（专名表当提示，只纠拼写）。
切条顺序：先在标点和词间停顿（落在词组边界上）切，再按长度切；孤字并到邻条。
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

MAX_CHARS = 16      # 一行上限；宁可稍过也不拆词
HARD_CHARS = 20
MAX_DUR = 4.5
MIN_DUR = 1.0
PAUSE = 0.30        # 词间停顿超过这个算候选切口
STRONG = re.compile(r"[。！？!?…]$")
WEAK = re.compile(r"[，,、；;：:]$")
HANG_END = ("的", "一个", "一些", "了", "就", "比较", "和", "跟", "在", "把", "被", "给", "对", "很", "非常", "是")
HANG_HEAD = ("的", "了", "里", "们", "着", "过", "中的", "呢", "吧", "啊", "嘛", "呀")
# 这些词开头的下一条更自然：切在它们前面加分，停在它们上面减分
OPENERS = ("但是", "但", "所以", "然后", "因为", "而且", "也", "就是", "那", "并且", "或者", "比如", "甚至", "包括", "当然")
PUNCT_ONLY = re.compile(r"^[，,。.！？!?、；;：:…\-—]+$")


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


def score_cut(ws, k) -> float:
    """在 ws[k] 之后切的得分：越高越像词组边界。"""
    w = clean_word(ws[k].w)
    nxt = clean_word(ws[k + 1].w) if k + 1 < len(ws) else ""
    pause = (ws[k + 1].s - ws[k].e) if k + 1 < len(ws) else 1.0
    s = 0.0
    if STRONG.search(w):
        s += 3
    elif WEAK.search(w):
        s += 2
    s += min(pause, 1.0) * 3
    bare = sc.norm(w)
    if bare.endswith(HANG_END) or sc.norm(nxt).startswith(HANG_HEAD):
        s -= 4
    if bare in OPENERS:
        s -= 3
    if sc.norm(nxt) in OPENERS:
        s += 1.5
    return s


def split_words(words) -> list[list]:
    cues: list[list] = []
    buf: list = []
    for i, w in enumerate(words):
        if buf and (w.s - buf[-1].e) > 1.2:   # 长停顿一定断
            cues.append(buf)
            buf = []
        buf.append(w)
        n = nchars(buf)
        dur = buf[-1].e - buf[0].s
        end_here = STRONG.search(clean_word(w.w)) and n >= 6
        if end_here:
            cues.append(buf)
            buf = []
            continue
        if n > MAX_CHARS or dur > MAX_DUR:
            # 在 buf 里找最好的切口（至少留 4 字）
            best, best_s = None, -9.0
            for k in range(len(buf) - 1):
                if nchars(buf[: k + 1]) < 4:
                    continue
                sc_ = score_cut(buf, k)
                if sc_ > best_s:
                    best, best_s = k, sc_
            if best is not None and (best_s > -1 or n > HARD_CHARS):
                cues.append(buf[: best + 1])
                buf = buf[best + 1:]
    if buf:
        cues.append(buf)
    # 孤字 / 太短：并到邻条（停顿短的那边），并后不超过 HARD_CHARS
    merged: list[list] = []
    for c in cues:
        if merged and (nchars(c) <= 2 or nchars(merged[-1]) <= 2) and nchars(merged[-1]) + nchars(c) <= HARD_CHARS \
                and c[0].s - merged[-1][-1].e < 0.6:
            merged[-1] = merged[-1] + c
        else:
            merged.append(c)
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio", required=True, help="asr/YYYY-MM-DD-run-final.wav（16k 单声道）")
    ap.add_argument("--txt", required=True, help="episodes/YYYY-MM-DD-slug/subtitles.txt")
    ap.add_argument("--prompt", help="专名表，来自 episode.md「专名」一行；只用来纠拼写")
    ap.add_argument("--model-dir", default=str(sc.DEFAULT_MODEL_DIR))
    ap.add_argument("--words-cache")
    ap.add_argument("--force", action="store_true", help="txt 已存在也覆盖（默认拒绝，防止冲掉人手改的字）")
    args = ap.parse_args()

    wav = Path(args.audio).expanduser()
    txt = Path(args.txt).expanduser()
    if txt.exists() and not args.force:
        raise SystemExit(f"{txt} 已存在。人手改过的字不要被初稿冲掉；确实要重来加 --force。")
    cache = Path(args.words_cache).expanduser() if args.words_cache else sc.default_cache(wav)
    words = sc.cached_words(wav, Path(args.model_dir).expanduser(), cache, args.prompt)
    groups = split_words(to_tokens(words))
    cues = []
    for g in groups:
        t = text_of(g)
        if not t:
            continue
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
