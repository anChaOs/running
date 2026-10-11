#!/usr/bin/env python3
"""字幕质检门：对着成片音频查出入点、漏盖、切条。不改任何文件。

硬失败行照列给人看；是否过门按比例（对不上的条不进分母）：
  早收      出点比这句说完早 > 0.3s；可核对条中 ≤ 3%
  漏盖      有正词人声却没字幕、连续 >= 0.5s 的段；累计时长 ≤ 成片时长的 1%
  挂静音    说完后字幕还挂在静音上 > 1.0s；可核对条中 ≤ 3%
超任一比例 → 退出码 1，不能写 subs: done。
提醒（逐条看，能改就改）：
  晚进 > 0.3s、短于 1s、超过 7 字/秒、单字条、停在「的/一个/了…」且紧接下一条、
  重叠、\\N 或多行、括号注释
另外列出噪声大、识别不可靠的时段，要人耳复听。

用法：
  check_subs.py --subs episodes/X/subtitles.txt --audio asr/X-run-final.wav
  （也收 .srt；词级识别缓存与 force_align.py 共用）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subs_core as sc  # noqa: E402

EARLY_OUT = 0.3
UNCOVERED = 0.5
OVER_SILENCE = 1.0
# 过门比例（对不上的条不进分母；漏盖按累计时长 / 成片时长）
MAX_EARLY_OUT_PCT = 3.0
MAX_OVER_SILENCE_PCT = 3.0
MAX_UNCOVERED_PCT = 1.0
LATE_IN = 0.3
MAX_CPS = 7.0
END_EXTEND = 0.3
HANG_END = ("的", "一个", "一些", "了", "就", "比较", "和", "跟", "在", "把", "被", "给", "对", "很", "非常", "这个", "那个", "是")
HANG_HEAD = ("的", "了", "里", "中的", "们", "着", "过")
BRACKETS = re.compile(r"[（(【\[].*?[）)】\]]")


def speech_overlap(a: float, b: float, vad) -> float:
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y in vad)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subs", required=True, help="subtitles.txt 或 .srt")
    ap.add_argument("--audio", required=True, help="成片 16k 单声道 wav")
    ap.add_argument("--model-dir", default=str(sc.DEFAULT_MODEL_DIR))
    ap.add_argument("--words-cache", help="默认 <wav>.words.json（与 force_align 共用）")
    ap.add_argument("--prompt", help="专名表，需与 force_align 用的一致才能复用缓存")
    ap.add_argument("--no-guided", action="store_true", help="对不上的条不再短窗重听（更快，核对条数变少）")
    ap.add_argument("--align-report", help="force_align 的报告（默认 <wav>.align.json）；字一致就复用它的短窗重听结果，省时间")
    ap.add_argument("--json", help="把全部结果写成 JSON")
    ap.add_argument("--max-rows", type=int, default=60, help="每类最多打印多少行")
    args = ap.parse_args()

    subs = Path(args.subs).expanduser()
    wav = Path(args.audio).expanduser()
    model_dir = Path(args.model_dir).expanduser()
    cache = Path(args.words_cache).expanduser() if args.words_cache else sc.default_cache(wav)

    cues = sc.load_any(subs)
    audio = sc.load_audio(wav)
    dur = len(audio) / sc.SR
    vad = sc.vad_segments(audio)
    words = sc.cached_words(wav, model_dir, cache, args.prompt)
    asr = sc.words_to_chars(words)
    spans = sc.align_chars([c.text.replace("\\N", "") for c in cues], asr)
    for sp in spans:
        if sc.anchored(sp):
            sp.source = "global"
    rep_path = Path(args.align_report).expanduser() if args.align_report else sc.default_report(wav)
    reused = 0
    if rep_path.is_file():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        if [r["text"] for r in rep] == [c.text for c in cues]:
            for sp, r in zip(spans, rep):
                # 只复用真正对上的（guided）；interp 是估的，不能拿来核对
                if sp.source != "global" and r["source"] == "guided" and r["speech"][0] is not None:
                    sp.ss, sp.se, sp.ratio, sp.source = r["speech"][0], r["speech"][1], r["ratio"], "guided"
                    reused += 1
            args.no_guided = True
    if not args.no_guided and any(sp.source != "global" for sp in spans):
        import force_align  # noqa: PLC0415

        force_align.guided_pass(cues, spans, audio, sc.get_model(model_dir), vad)

    hard: list[dict] = []
    warn: list[dict] = []
    onsets, offsets = [], []
    unchecked = 0

    def add(lst, kind, c, i, detail=""):
        lst.append({"kind": kind, "i": i + 1, "start": c.start, "end": c.end, "text": c.text, "detail": detail})

    for i, (c, sp) in enumerate(zip(cues, spans)):
        n = len(sc.norm(c.text))
        d = c.end - c.start
        # 文字 / 切条类提醒
        if "\\N" in c.text or "\n" in c.text:
            add(warn, "多行", c, i)
        if BRACKETS.search(c.text):
            add(warn, "括号注释", c, i, BRACKETS.search(c.text).group(0))
        if d < 1.0:
            add(warn, "短于1s", c, i, f"{d:.2f}s")
        if d > 0 and n / d > MAX_CPS:
            add(warn, "太快", c, i, f"{n / d:.1f}字/秒")
        if n == 1:
            add(warn, "单字条", c, i)
        if i + 1 < len(cues):
            nx = cues[i + 1]
            if nx.start < c.end - 0.005:
                add(warn, "重叠", c, i, f"与下一条重叠 {c.end - nx.start:.2f}s")
            t = sc.norm(c.text)
            if nx.start - c.end < 0.3 and (t.endswith(HANG_END) or sc.norm(nx.text).startswith(HANG_HEAD)):
                add(warn, "词组拆开", c, i, f"→ {nx.text}")
        # 时间类
        if not sc.anchored(sp):
            unchecked += 1
            continue
        ss, se = sp.ss, sp.se
        cands = [a for a, b in vad if ss - 0.35 <= a <= ss + 0.15]
        if cands:
            ss = min(cands, key=lambda a: abs(a - ss))
        elif sc.island_at(ss, vad, tol=0.0) is None or (
            (spans[i - 1].se if i > 0 and spans[i - 1].se is not None else None) is not None and abs(ss - (spans[i - 1].se if i > 0 and spans[i - 1].se is not None else None)) < 0.05
        ):
            # 识别的词起点粘在上一个词尾 / 落在静音里：挪到后面最近的人声岛开头
            nxt_isl = [a for a, b in vad if ss < a <= min(ss + 1.2, se - 0.1)]
            if nxt_isl:
                ss = nxt_isl[0]
        isl = sc.island_at(se, vad, tol=0.1)
        if isl and isl[1] - se <= END_EXTEND:
            # 岛尾若已是下一条的字（连续说话），不算本条没说完
            nxt_sp = next((spans[q] for q in range(i + 1, min(i + 3, len(spans))) if sc.anchored(spans[q])), None)
            cap = max(se, nxt_sp.ss) if nxt_sp is not None and nxt_sp.ss < isl[1] else isl[1]
            se = max(se, min(isl[1], cap))
        on, off = c.start - ss, c.end - se
        onsets.append(on)
        offsets.append(off)
        if off < -EARLY_OUT:
            add(hard, "早收", c, i, f"说完在 {sc.fmt_clock(se)}，早 {-off:.2f}s")
        if off > OVER_SILENCE and speech_overlap(se, c.end, vad) < 0.2:
            add(hard, "挂静音", c, i, f"说完在 {sc.fmt_clock(se)}，多挂 {off:.2f}s")
        if on > LATE_IN:
            add(warn, "晚进", c, i, f"开口在 {sc.fmt_clock(ss)}，晚 {on:.2f}s")

    # 漏盖：正词 ∩ VAD 人声 − 字幕覆盖
    word_iv = sc.merge_intervals(
        [(w.s, w.e) for w in words if sc.norm(w.w) and not set(sc.norm(w.w)) <= sc.FILLERS], gap=0.15
    )
    speech_iv = []
    for a, b in word_iv:
        for x, y in vad:
            lo, hi = max(a, x), min(b, y)
            if hi > lo:
                speech_iv.append((lo, hi))
    speech_iv = sc.merge_intervals(speech_iv, gap=0.15)
    cover = sc.merge_intervals([(c.start, c.end) for c in cues])
    uncovered = []
    for a, b in speech_iv:
        segs = [(a, b)]
        for x, y in cover:
            nxt = []
            for p, q in segs:
                if y <= p or x >= q:
                    nxt.append((p, q))
                else:
                    if x > p:
                        nxt.append((p, x))
                    if y < q:
                        nxt.append((y, q))
            segs = nxt
        uncovered += segs
    uncovered = sc.merge_intervals(uncovered, gap=0.2)
    for a, b in uncovered:
        if b - a >= UNCOVERED:
            said = "".join(w.w for w in words if w.e > a and w.s < b).strip()
            hard.append({"kind": "漏盖", "i": None, "start": a, "end": b, "text": said, "detail": f"{b - a:.2f}s 无字幕"})

    # 低置信时段：识别字大多对不上定稿，或识别置信度低
    used = set()
    for sp in spans:
        used.update(sp.asr_idx)
    low = []
    win = 15.0
    t = 0.0
    while t < dur:
        idx = [k for k, ch in enumerate(asr) if t <= ch.s < t + win]
        if len(idx) >= 8:
            match = sum(k in used for k in idx) / len(idx)
            prob = sum(asr[k].p for k in idx) / len(idx)
            if match < 0.6 or prob < 0.5:
                low.append((t, t + win, match, prob))
        t += win
    low_m = []
    for a, b, m, p in low:
        if low_m and a <= low_m[-1][1]:
            low_m[-1] = (low_m[-1][0], b, min(low_m[-1][2], m), min(low_m[-1][3], p))
        else:
            low_m.append((a, b, m, p))

    def pct(xs, cond):
        return 100.0 * sum(1 for x in xs if cond(x)) / len(xs) if xs else 0.0

    def med(xs):
        s = sorted(xs)
        return s[len(s) // 2] if s else 0.0

    checked = len(onsets)
    hard_early = sum(h["kind"] == "早收" for h in hard)
    hard_unc = sum(h["kind"] == "漏盖" for h in hard)
    hard_hang = sum(h["kind"] == "挂静音" for h in hard)
    hard_unc_s = sum(h["end"] - h["start"] for h in hard if h["kind"] == "漏盖")
    early_pct = 100.0 * hard_early / checked if checked else 0.0
    hang_pct = 100.0 * hard_hang / checked if checked else 0.0
    unc_pct = 100.0 * hard_unc_s / dur if dur else 0.0
    fail_early = early_pct > MAX_EARLY_OUT_PCT
    fail_hang = hang_pct > MAX_OVER_SILENCE_PCT
    fail_unc = unc_pct > MAX_UNCOVERED_PCT
    # 一条都核对不上时没法过门
    fail_none = checked == 0 and len(cues) > 0
    failed = fail_early or fail_hang or fail_unc or fail_none

    summary = {
        "cues": len(cues), "checked": checked, "unchecked": unchecked,
        "audio_s": round(dur, 2),
        "hard_early_out": hard_early,
        "hard_uncovered": hard_unc,
        "hard_over_silence": hard_hang,
        "uncovered_speech_s": round(sum(b - a for a, b in uncovered), 2),
        "hard_uncovered_s": round(hard_unc_s, 2),
        "early_out_pct_of_checked": round(early_pct, 2),
        "over_silence_pct_of_checked": round(hang_pct, 2),
        "uncovered_pct_of_audio": round(unc_pct, 2),
        "max_early_out_pct": MAX_EARLY_OUT_PCT,
        "max_over_silence_pct": MAX_OVER_SILENCE_PCT,
        "max_uncovered_pct": MAX_UNCOVERED_PCT,
        "gate_failed": failed,
        "onset_median": round(med(onsets), 3), "offset_median": round(med(offsets), 3),
        "abs_onset_median": round(med([abs(x) for x in onsets]), 3),
        "abs_offset_median": round(med([abs(x) for x in offsets]), 3),
        "early_out_gt_0.2_pct": round(pct(offsets, lambda x: x < -0.2), 1),
        "early_out_gt_0.5_pct": round(pct(offsets, lambda x: x < -0.5), 1),
        "early_out_gt_1.0_pct": round(pct(offsets, lambda x: x < -1.0), 1),
        "late_in_gt_0.3_pct": round(pct(onsets, lambda x: x > 0.3), 1),
        "warn_counts": {},
    }
    for w in warn:
        summary["warn_counts"][w["kind"]] = summary["warn_counts"].get(w["kind"], 0) + 1

    def table(title, rows):
        print(f"\n## {title}（{len(rows)}）")
        if not rows:
            return
        print("| 类型 | # | 时间 | 字幕 | 说明 |\n| --- | --- | --- | --- | --- |")
        for r in sorted(rows, key=lambda r: r["start"])[: args.max_rows]:
            num = r["i"] if r["i"] else "-"
            print(f"| {r['kind']} | {num} | {sc.fmt_clock(r['start'])}–{sc.fmt_clock(r['end'])} | {r['text']} | {r['detail']} |")
        if len(rows) > args.max_rows:
            print(f"| … | | | 另有 {len(rows) - args.max_rows} 条，见 --json | |")

    def mark(ok):
        return "✓" if ok else "✗"

    print(f"# check_subs：{subs.name}")
    print(
        f"{summary['cues']} 条，可核对 {summary['checked']}，对不上 {summary['unchecked']}。"
        f"硬失败行：早收 {hard_early} / 漏盖 {hard_unc}（≥0.5s 累计 {hard_unc_s:.2f}s）"
        f" / 挂静音 {hard_hang}。"
    )
    print(
        f"过门比例：早收 {early_pct:.2f}% / ≤{MAX_EARLY_OUT_PCT:g}% {mark(not fail_early)}；"
        f"漏盖 {unc_pct:.2f}% 成片 / ≤{MAX_UNCOVERED_PCT:g}% {mark(not fail_unc)}；"
        f"挂静音 {hang_pct:.2f}% / ≤{MAX_OVER_SILENCE_PCT:g}% {mark(not fail_hang)}"
        + ("；无可核对条 ✗" if fail_none else "")
        + "。"
    )
    print(
        f"入点中位 {summary['onset_median']:+.2f}s，出点中位 {summary['offset_median']:+.2f}s；"
        f"早收 >0.2s {summary['early_out_gt_0.2_pct']}%，>0.5s {summary['early_out_gt_0.5_pct']}%，>1s {summary['early_out_gt_1.0_pct']}%；"
        f"晚进 >0.3s {summary['late_in_gt_0.3_pct']}%。提醒：{summary['warn_counts']}"
    )
    table("硬失败（逐条列出，供人听）", hard)
    table("提醒", warn)
    print(f"\n## 噪声大 / 识别不可靠，要人耳复听（{len(low_m)}）")
    for a, b, m, p in low_m:
        print(f"- {sc.fmt_clock(a)}–{sc.fmt_clock(b)}  识别与定稿吻合 {m:.0%}，识别置信 {p:.2f}")

    if args.json:
        Path(args.json).expanduser().write_text(
            json.dumps({"summary": summary, "hard": hard, "warn": warn,
                        "low_confidence": [{"start": a, "end": b, "match": m, "prob": p} for a, b, m, p in low_m]},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    print("\n结果：" + ("不通过（过门比例超标）" if failed else "通过"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
