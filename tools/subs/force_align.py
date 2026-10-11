#!/usr/bin/env python3
"""把人手改好的 subtitles.txt 强制对齐到成片音频。只改时间，不改字。

1. faster-whisper large-v3-turbo 整条转写拿词级时间（缓存到 wav 旁边 *.words.json）
2. 定稿文字和识别字序列按字对齐，只用连续对上的字做锚点
3. 对不上的条：在前后锚点之间切短窗，用这几条定稿文字当提示重听一次
4. 还对不上：短窗内按人声时长比例分（标 interp，要人听）；窗太长就保留原时间（标 unanchored）
5. Silero VAD 咬点：入点贴开口（略早），出点盖住说完，句间留白，最短约 1 秒

不做整段均分，不出等步长的阶梯。对不上的条一律列出来。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subs_core as sc  # noqa: E402

LEAD = 0.10        # 入点比开口早一点
SNAP_IN = 0.35     # 开口前这么近有人声岛起点，就贴上去
SNAP_FWD = 1.20    # 起点落在静音里，往后找人声岛开头的最远距离
HOLD = 0.20        # 说完后再挂一会儿
EXTEND_OUT = 0.50  # 说完后这么近还在同一人声岛里，出点跟到岛尾
GAP = 0.08         # 两条之间最小空隙
MIN_DUR = 1.00
MAX_TAIL = 0.90    # 出点最多比说完晚这么多（check_subs 硬线是 1.0）
GUIDED_MAX_WIN = 90.0
GUIDED_CHUNK = 28.0
INTERP_MAX_WIN = 10.0


def _guided_round(cues, spans, audio, model, tried):
    n = len(cues)
    i = 0
    fixed = 0
    while i < n:
        if sc.anchored(spans[i]):
            i += 1
            continue
        j = i
        while j < n and not sc.anchored(spans[j]):
            j += 1
        # [i, j) 对不上：窗口取前后锚点之间
        prev_end = spans[i - 1].se if i > 0 else max(0.0, cues[i].start - 5)
        next_start = spans[j].ss if j < n else cues[j - 1].end + 5
        lo = max(0.0, prev_end - 0.3)
        hi = min(len(audio) / sc.SR, next_start + 0.3)
        if hi - lo < 0.3 or hi - lo > GUIDED_MAX_WIN:
            i = j
            continue
        # whisper 一次只看 30 秒：窗太长先听前一段，下一轮再往后推
        hi_eff = min(hi, lo + GUIDED_CHUNK)
        key = (i, j, round(lo, 1), round(hi_eff, 1))
        if key in tried:  # 同一个窗上一轮已经听过、没进展
            i = j
            continue
        tried.add(key)
        texts = [c.text for c in cues[i:j]]
        clip = audio[int(lo * sc.SR):int(hi_eff * sc.SR)]
        # 先用这几条原文当提示；提示有时会让开头被吞，再不带提示听一次补
        for prompt in ("，".join(texts)[-200:], None):
            todo = [k for k in range(i, j) if not sc.anchored(spans[k])]
            if not todo:
                break
            words = sc.transcribe_words(model, clip, prompt=prompt, offset=lo, vad_filter=False, beam_size=2)
            sub = sc.align_chars(texts, sc.words_to_chars(words))
            for k, sp in enumerate(sub):
                if i + k in todo and sc.anchored(sp) and lo - 0.2 <= sp.ss and sp.se <= hi_eff + 0.2:
                    sp.source = "guided"
                    spans[i + k] = sp
                    fixed += 1
        # 锚点必须单调：和前后对上的条冲突就作废
        for k in range(i, j):
            sp = spans[k]
            if sp.source != "guided":
                continue
            prev = next((spans[q] for q in range(k - 1, -1, -1) if sc.anchored(spans[q])), None)
            nxt = next((spans[q] for q in range(k + 1, n) if sc.anchored(spans[q])), None)
            if (prev and sp.ss < prev.se - 0.3) or (nxt and sp.se > nxt.ss + 0.3):
                spans[k] = sc.Span(n=sp.n)
                fixed -= 1
        i = j
    return fixed


def guided_pass(cues, spans, audio, model, vad=None, rounds: int = 4):
    """对不上的连续几条：在前后锚点之间切短窗重听。一轮补上一些锚点后窗会变小，最多跑几轮。"""
    total = 0
    tried: set = set()
    for _ in range(rounds):
        got = _guided_round(cues, spans, audio, model, tried)
        total += got
        if got <= 0:
            break
    return total


def interp_pass(cues, spans, vad, audio_dur):
    """仍对不上：前后锚点之间的短窗，按人声时长、按字数比例分。只在短窗里做。"""
    n = len(cues)
    i = 0
    while i < n:
        if sc.anchored(spans[i]):
            i += 1
            continue
        j = i
        while j < n and not sc.anchored(spans[j]):
            j += 1
        lo = spans[i - 1].se if i > 0 else None
        hi = spans[j].ss if j < n else None
        if lo is None or hi is None or hi - lo > INTERP_MAX_WIN or hi <= lo:
            for k in range(i, j):
                spans[k].source = "unanchored"
            i = j
            continue
        # 窗内人声区间
        speech = [(max(a, lo), min(b, hi)) for a, b in vad if b > lo and a < hi]
        speech = [(a, b) for a, b in speech if b > a] or [(lo, hi)]
        total = sum(b - a for a, b in speech)
        lens = [max(len(sc.norm(c.text)), 1) for c in cues[i:j]]
        tot_chars = sum(lens)

        def at(frac):
            target = frac * total
            acc = 0.0
            for a, b in speech:
                if acc + (b - a) >= target:
                    return a + (target - acc)
                acc += b - a
            return speech[-1][1]

        acc = 0
        for k, L in zip(range(i, j), lens):
            sp = spans[k]
            sp.ss = at(acc / tot_chars)
            acc += L
            sp.se = at(acc / tot_chars)
            sp.source = "interp"
        i = j


def place(cues, spans, vad, audio_dur):
    """人声范围 → 字幕出入点。"""
    n = len(cues)
    ok = [sp.source != "unanchored" and sp.ss is not None for sp in spans]
    raw_ss = [sp.ss if ok[i] else cues[i].start for i, sp in enumerate(spans)]
    st = [0.0] * n
    en = [0.0] * n
    se_ref = [0.0] * n
    for i, (c, sp) in enumerate(zip(cues, spans)):
        if not ok[i]:
            st[i], en[i], se_ref[i] = c.start, c.end, c.end
            continue
        ss, se = sp.ss, sp.se
        # 入点：开口前不远有人声岛起点就贴上（不越过上一条的说完）
        floor = spans[i - 1].se if i > 0 and ok[i - 1] else 0.0
        cands = [a for a, b in vad if ss - SNAP_IN <= a <= ss + 0.15 and a >= floor]
        if cands:
            ss = min(cands, key=lambda a: abs(a - ss))
        elif sc.island_at(ss, vad, tol=0.0) is None or (
            (spans[i - 1].se if i > 0 and spans[i - 1].se is not None else None) is not None and abs(ss - (spans[i - 1].se if i > 0 and spans[i - 1].se is not None else None)) < 0.05
        ):
            # 识别的词起点粘在上一个词尾 / 落在静音里：挪到后面最近的人声岛开头
            nxt_isl = [a for a, b in vad if ss < a <= min(ss + SNAP_FWD, se - 0.1)]
            if nxt_isl:
                ss = nxt_isl[0]
        # 出点：只往后延，不往前缩；延到同一人声岛尾，但不越过下一条开口
        nxt_ss = raw_ss[i + 1] if i + 1 < n else audio_dur
        isl = sc.island_at(se, vad, tol=0.15)
        if isl and isl[1] - se <= EXTEND_OUT:
            se = max(se, isl[1])
        st[i] = max(0.0, ss - LEAD)
        en[i] = se + HOLD
        se_ref[i] = se

    for i in range(1, n):
        if st[i] < st[i - 1] + 0.05:
            st[i] = st[i - 1] + 0.05

    for i in range(n):
        nxt = st[i + 1] if i + 1 < n else audio_dur
        if en[i] > nxt - GAP:
            if se_ref[i] <= nxt - GAP:
                en[i] = nxt - GAP
            elif i + 1 < n and se_ref[i] + GAP - st[i + 1] <= 0.3:
                # 本条还没说完下一条就要开口：差得不多，下一条稍让
                en[i] = se_ref[i]
                st[i + 1] = en[i] + GAP
            else:
                en[i] = nxt - GAP
        if ok[i]:
            en[i] = min(en[i], se_ref[i] + MAX_TAIL)
        if en[i] - st[i] < MIN_DUR:  # 最短时长：先往后补，再往前补
            nxt = st[i + 1] if i + 1 < n else audio_dur
            en[i] = max(en[i], min(st[i] + MIN_DUR, nxt - GAP))
        if en[i] - st[i] < MIN_DUR:
            prev = en[i - 1] if i > 0 else 0.0
            st[i] = min(st[i], max(en[i] - MIN_DUR, prev + GAP))
    # 收尾：绝不重叠
    for i in range(n - 1):
        if en[i] > st[i + 1] - GAP:
            en[i] = st[i + 1] - GAP
        if en[i] <= st[i]:
            en[i] = st[i] + 0.2
            st[i + 1] = max(st[i + 1], en[i] + GAP)
    return [sc.Cue(round(a, 2), round(b, 2), c.text) for a, b, c in zip(st, en, cues)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--txt", required=True, help="episodes/YYYY-MM-DD-slug/subtitles.txt（人手改好的字）")
    ap.add_argument("--audio", required=True, help="成片抽的 16k 单声道 wav，如 asr/YYYY-MM-DD-run-final.wav")
    ap.add_argument("--out", help="写到这里；默认覆盖 --txt")
    ap.add_argument("--model-dir", default=str(sc.DEFAULT_MODEL_DIR))
    ap.add_argument("--words-cache", help="默认 <wav>.words.json")
    ap.add_argument("--prompt", help="专名表（只用来纠拼写），如 \"Personal Agent、Grok Bot\"")
    ap.add_argument("--report", help="对齐报告 JSON（默认 <wav>.align.json，放媒体目录 asr/，check_subs 会复用）")
    ap.add_argument("--no-guided", action="store_true", help="跳过短窗重听")
    args = ap.parse_args()

    t0 = time.time()
    txt = Path(args.txt).expanduser()
    wav = Path(args.audio).expanduser()
    out = Path(args.out).expanduser() if args.out else txt
    model_dir = Path(args.model_dir).expanduser()
    cache = Path(args.words_cache).expanduser() if args.words_cache else sc.default_cache(wav)

    header, cues = sc.load_txt(txt)
    audio = sc.load_audio(wav)
    dur = len(audio) / sc.SR
    vad = sc.vad_segments(audio)
    words = sc.cached_words(wav, model_dir, cache, args.prompt)
    spans = sc.align_chars([c.text for c in cues], sc.words_to_chars(words))
    for sp in spans:
        if sc.anchored(sp):
            sp.source = "global"
    n_global = sum(sp.source == "global" for sp in spans)

    n_guided = 0
    if not args.no_guided and n_global < len(cues):
        print(f"[align] 整条对上 {n_global}/{len(cues)}，其余短窗重听…", file=sys.stderr)
        n_guided = guided_pass(cues, spans, audio, sc.get_model(model_dir), vad)
    interp_pass(cues, spans, vad, dur)
    new = place(cues, spans, vad, dur)

    if not any(h.startswith("# 字幕") for h in header):
        header = ["# 字幕（单行短条；时间是成片轴）"] + header
    header = [h for h in header if "对齐" not in h and "手改保留" not in h]
    header.append("# 时间由 tools/subs/force_align.py 强制对齐（字未改）。")
    sc.write_txt(out, header, new)

    rows = []
    for i, (c, sp, nc) in enumerate(zip(cues, spans, new), 1):
        rows.append({
            "i": i, "text": c.text, "source": sp.source, "ratio": round(sp.ratio, 2),
            "old": [c.start, c.end], "new": [nc.start, nc.end],
            "speech": [round(sp.ss, 2) if sp.ss is not None else None, round(sp.se, 2) if sp.se is not None else None],
        })
    report = Path(args.report).expanduser() if args.report else sc.default_report(wav)
    report.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")

    interp = [r for r in rows if r["source"] == "interp"]
    unanch = [r for r in rows if r["source"] == "unanchored"]
    print(f"对齐 {len(cues)} 条：整条 {n_global}，短窗重听 {n_guided}，短窗按比例 {len(interp)}，保留原时间 {len(unanch)}。用时 {time.time() - t0:.0f}s")
    if interp or unanch:
        print("\n要人听的条（interp = 短窗内按比例分；unanchored = 对不上，保留原时间）：")
        for r in interp + unanch:
            print(f"  #{r['i']:>4} {sc.fmt_clock(r['new'][0])}  {r['source']:<10} {r['text']}")
    print(f"\n写入 {out}\n报告 {report}\n下一步：tools/subs/check_subs.py 质检，再 txt_to_subs.py 回写 SRT。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
