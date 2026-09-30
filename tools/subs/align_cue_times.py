#!/usr/bin/env python3
"""只改字幕时间：识别段按字对齐，再用 VAD 咬出入点。不改字。

入点跟开口，出点跟说完。句间停顿留白，不把下一条贴上去。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path


CUE_RE = re.compile(r"^(\d+:\d{2}:\d{2}\.\d{2})[–-](\d+:\d{2}:\d{2}\.\d{2})\s+(.*)$")
VAD_RE = re.compile(r"Speech segment \d+: start = ([0-9.]+), end = ([0-9.]+)")
PUNCT = re.compile(r"[\s,，。.!！？?、；;：:·\-—_（）()【】\[\]“”\"']+")
DEFAULT_VAD_MODEL = Path.home() / "Movies/running-content/.models/ggml-silero-v5.1.2.bin"
MIN_CUE = 0.36
# 两条字幕之间：VAD 空洞超过这个就留白
PAUSE_BETWEEN = 0.25
# 识别段被拉得很长时，只在这种长停顿处收回出点；句内换气不断条
FAT_SILENCE = 0.80
HOLD = 0.15
LEAD = 0.04
FIRST_LEAD = 0.16
MIN_GAP = 0.08
PAD_END = 0.12
VAD_MERGE = 0.15
CHARS_PER_SEC = 2.0
BUDGET_PAD = 0.60


def parse_txt_time(t: str) -> float:
    h, m, rest = t.split(":")
    s, cs = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0


def fmt(t: float) -> str:
    if t < 0:
        t = 0.0
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def norm(text: str) -> str:
    return PUNCT.sub("", text).lower()


def load_cues(path: Path) -> list[tuple[float, float, str]]:
    cues = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = CUE_RE.match(line)
        if not m:
            raise SystemExit(f"unparsed: {raw!r}")
        cues.append((parse_txt_time(m.group(1)), parse_txt_time(m.group(2)), m.group(3).strip()))
    return cues


def load_asr_chars(json_path: Path) -> list[tuple[float, float, str]]:
    data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    chars: list[tuple[float, float, str]] = []
    for seg in data.get("transcription") or []:
        text = norm(seg.get("text") or "")
        if not text:
            continue
        t0 = float(seg["offsets"]["from"]) / 1000.0
        t1 = float(seg["offsets"]["to"]) / 1000.0
        n = len(text)
        for i, ch in enumerate(text):
            a = t0 + (t1 - t0) * i / n
            b = t0 + (t1 - t0) * (i + 1) / n
            chars.append((a, b, ch))
    return chars


def vad_speech(wav: Path, model: Path) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [
            "whisper-vad-speech-segments",
            "--vad-model",
            str(model),
            "--file",
            str(wav),
            "--no-prints",
            "--threads",
            "8",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    segs = []
    for line in proc.stdout.splitlines():
        m = VAD_RE.search(line)
        if not m:
            continue
        a, b = float(m.group(1)) / 100.0, float(m.group(2)) / 100.0
        if b > a:
            segs.append((a, b))
    merged: list[tuple[float, float]] = []
    for a, b in segs:
        if merged and a <= merged[-1][1] + VAD_MERGE:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def speech_budget(text: str) -> float:
    """边跑边说偏慢。只用来收回被 Whisper 拉长的段，不是 3.2 秒硬切。"""
    n = max(len(norm(text)), 1)
    return max(1.20, n / CHARS_PER_SEC + BUDGET_PAD)


def covering(t: float, speech: list[tuple[float, float]], *, tol: float = 0.08) -> tuple[float, float] | None:
    for a, b in speech:
        if a - tol <= t <= b + tol:
            return a, b
    return None


def next_start(t: float, speech: list[tuple[float, float]]) -> float | None:
    for a, _b in speech:
        if a >= t - 0.02:
            return a
    return None


def prev_end(t: float, speech: list[tuple[float, float]]) -> float | None:
    last = None
    for _a, b in speech:
        if b <= t + 0.02:
            last = b
    return last


def cluster_end_after(start: float, speech: list[tuple[float, float]], *, pause: float) -> float | None:
    """从 start 所在/之后的人声，一直到空洞 >= pause。"""
    last = None
    end = None
    for a, b in speech:
        if b <= start - 0.02:
            continue
        if last is None:
            last = b
            end = b
            continue
        if a - last >= pause:
            break
        last = b
        end = b
    return end


def snap_to_speech(
    start: float,
    end: float,
    speech: list[tuple[float, float]],
    text: str,
    *,
    first: bool,
) -> tuple[float, float]:
    if not speech:
        return start, max(end, start + 0.12)

    asr_end = end
    cs = covering(start, speech)
    if cs:
        _a, b = cs
        remain = b - start
        ns = next_start(b + 0.02, speech)
        hole = (ns - b) if ns is not None else 0.0
        # 识别段开头常贴在上一句尾巴或思考停顿前，字幕会过早出现
        jump = (
            ns is not None
            and ns < asr_end - 0.2
            and hole >= PAUSE_BETWEEN
            and ns - start < 4.0
            and (remain < 0.28 or (remain < 0.55 and hole >= FAT_SILENCE))
        )
        if jump and ns is not None:
            start = ns
        else:
            start = max(start, cs[0])
    else:
        ns = next_start(start, speech)
        if ns is not None:
            dist = ns - start
            if first and dist < 2.5:
                start = max(0.0, ns - FIRST_LEAD)
            elif dist < 2.0:
                start = ns

    # 出点跟识别走：人声里不要按 VAD 碎段提前切掉；静音里才收回
    ce = covering(end, speech, tol=0.12)
    if ce:
        snapped_end = max(end, start + 0.12)
    else:
        pe = prev_end(end, speech)
        snapped_end = pe if pe is not None and pe > start + 0.12 else end

    budget = speech_budget(text)
    if snapped_end - start > budget:
        cend = cluster_end_after(start, speech, pause=FAT_SILENCE)
        if cend is not None and cend > start + max(1.0, budget * 0.4):
            snapped_end = min(snapped_end, cend)
        else:
            cut = start + budget
            ce_cut = covering(cut, speech, tol=0.12)
            if ce_cut:
                snapped_end = min(snapped_end, ce_cut[1], max(cut, start + 0.12))
            else:
                pe = prev_end(cut, speech)
                if pe is not None and pe > start + 0.12:
                    snapped_end = pe
                else:
                    snapped_end = min(snapped_end, cut)

    return start, max(snapped_end, start + 0.12)


def apply_sentence_gaps(
    cues: list[tuple[float, float, str]],
    speech: list[tuple[float, float]],
    clip_dur: float,
) -> list[tuple[float, float, str]]:
    """两句之间有人声停顿就留白；连续说才允许贴近。"""
    if not cues:
        return cues
    starts = [s for s, _e, _t in cues]
    ends = [e for _s, e, _t in cues]
    texts = [t for _s, _e, t in cues]

    for i in range(len(cues) - 1):
        s0, e0 = starts[i], ends[i]
        s1, e1 = starts[i + 1], ends[i + 1]
        # 只处理落在两条之间的停顿，不按当前 VAD 碎段把出点往前砍
        cs_e = covering(e0, speech)
        hole_start = cs_e[1] if cs_e else e0
        ns_after = next_start(hole_start + 0.02, speech)
        if ns_after is None:
            hole = 0.0
            speech_start = s1
        else:
            hole = ns_after - hole_start
            speech_start = ns_after
        between = s1 + 0.05 >= hole_start
        if hole >= PAUSE_BETWEEN and between:
            new_e0 = min(e0, hole_start + HOLD)
            new_s1 = max(s1, speech_start - LEAD)
            if new_s1 < new_e0 + MIN_GAP:
                new_s1 = new_e0 + MIN_GAP
            new_e0 = max(s0 + 0.12, new_e0)
            if e1 - new_s1 < 0.12:
                new_s1 = min(new_s1, max(s1, e1 - 0.12))
            ends[i] = new_e0
            starts[i + 1] = new_s1
        elif s1 < e0:
            ends[i] = min(e0, s1)
            starts[i + 1] = max(s1, ends[i])
        elif s1 < e0 + MIN_GAP:
            steal = MIN_GAP - (s1 - e0)
            if e0 - s0 - steal >= MIN_CUE:
                ends[i] = e0 - steal
            # 没空可偷就贴着，不强行推迟下一句入口

    fixed: list[tuple[float, float, str]] = []
    for i, text in enumerate(texts):
        start, end = starts[i], ends[i]
        start = max(0.0, start)
        if fixed and start < fixed[-1][1]:
            start = fixed[-1][1]
        nxt = starts[i + 1] if i + 1 < len(starts) else clip_dur
        # 最短时长不要填进下一句前面的停顿
        gap_limit = nxt - MIN_GAP if i + 1 < len(starts) else clip_dur
        if end < start + MIN_CUE:
            end = min(max(gap_limit, start + 0.12), start + MIN_CUE)
        end = min(end, nxt, clip_dur)
        if i + 1 < len(starts) and end > nxt - MIN_GAP and nxt - start > MIN_GAP:
            end = max(start + 0.12, nxt - MIN_GAP)
        if end <= start:
            end = min(clip_dur, start + 0.2)
        if fixed and fixed[-1][1] > start:
            ps, _pe, pt = fixed[-1]
            fixed[-1] = (ps, start, pt)
        fixed.append((start, min(end, clip_dur), text))
    return fixed


def align_clip(
    cues: list[tuple[float, float, str]],
    asr_chars: list[tuple[float, float, str]],
    speech: list[tuple[float, float]],
    clip_dur: float,
) -> list[tuple[float, float, str]]:
    asr_str = "".join(ch for _a, _b, ch in asr_chars)
    cue_str = "".join(norm(text) for _s, _e, text in cues)
    if not asr_chars or not cue_str:
        return [(max(0.0, s), min(clip_dur, e), t) for s, e, t in cues]

    matcher = SequenceMatcher(a=asr_str, b=cue_str, autojunk=False)
    # cue 字符下标 -> asr 字符下标
    cue_to_asr = [-1] * len(cue_str)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"equal", "replace"}:
            span = min(i2 - i1, j2 - j1)
            for k in range(span):
                cue_to_asr[j1 + k] = i1 + k
        # insert: 新字没有 asr 对上，后面用邻近填

    last = -1
    for i, v in enumerate(cue_to_asr):
        if v >= 0:
            last = v
        elif last >= 0:
            cue_to_asr[i] = last
    nxt = -1
    for i in range(len(cue_to_asr) - 1, -1, -1):
        if cue_to_asr[i] >= 0:
            nxt = cue_to_asr[i]
        elif nxt >= 0:
            cue_to_asr[i] = nxt

    out: list[tuple[float, float, str]] = []
    cursor = 0
    for start0, end0, text in cues:
        n = len(norm(text)) or 1
        idxs = [cue_to_asr[cursor + k] for k in range(n) if cursor + k < len(cue_to_asr)]
        cursor += n
        idxs = [i for i in idxs if 0 <= i < len(asr_chars)]
        if idxs:
            start = asr_chars[idxs[0]][0]
            end = asr_chars[idxs[-1]][1]
        else:
            start, end = start0, end0
        start, end = snap_to_speech(start, end, speech, text, first=not out)
        start = max(0.0, start)
        end = min(clip_dur, end + PAD_END)
        out.append((start, end, text))

    return apply_sentence_gaps(out, speech, clip_dur)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--txt", required=True)
    parser.add_argument("--asr-dir", required=True)
    parser.add_argument("--clips", required=True, help="open,run-a,run-b,close wav stems")
    parser.add_argument("--offsets", required=True, help="comma seconds, same order as clips")
    parser.add_argument("--durs", required=True, help="comma seconds, same order as clips")
    parser.add_argument("--vad-model", default=str(DEFAULT_VAD_MODEL))
    args = parser.parse_args()

    txt = Path(args.txt).expanduser()
    asr_dir = Path(args.asr_dir).expanduser()
    stems = [p.strip() for p in args.clips.split(",") if p.strip()]
    offsets = [float(x) for x in args.offsets.split(",")]
    durs = [float(x) for x in args.durs.split(",")]
    vad_model = Path(args.vad_model).expanduser()
    if len(stems) != len(offsets) or len(stems) != len(durs):
        raise SystemExit("clips/offsets/durs length mismatch")

    cues = load_cues(txt)
    bounds = []
    for i, off in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else off + durs[i]
        bounds.append((off, end, stems[i], durs[i]))

    grouped: dict[str, list[tuple[float, float, str]]] = {s: [] for s in stems}
    for start, end, text in cues:
        mid = (start + end) / 2
        placed = False
        for off, limit, stem, _d in bounds:
            if off - 0.01 <= mid < limit:
                grouped[stem].append((start - off, end - off, text))
                placed = True
                break
        if not placed:
            grouped[stems[-1]].append((start - offsets[-1], end - offsets[-1], text))

    lines = [
        "# 字幕（单行短条；时间是成片轴，已对口型）",
        "# 字已定稿。",
        "",
    ]
    for i, (stem, off, dur) in enumerate(zip(stems, offsets, durs, strict=False)):
        local = grouped[stem]
        if not local:
            continue
        asr_chars = load_asr_chars(asr_dir / f"{stem}.json")
        wav = asr_dir / f"{stem}.wav"
        speech = vad_speech(wav, vad_model) if wav.is_file() else []
        aligned = align_clip(local, asr_chars, speech, dur)
        limit = offsets[i + 1] if i + 1 < len(offsets) else off + dur
        for start, end, text in aligned:
            abs_a = off + start
            abs_b = off + end
            if abs_a < off:
                abs_a = off
            if abs_b > limit:
                abs_b = limit
            if abs_b <= abs_a + 0.08:
                continue
            lines.append(f"{fmt(abs_a)}–{fmt(abs_b)}  {text}")

    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    timed = [ln for ln in lines if ln[:1].isdigit()]
    print(f"Wrote {txt} cues={len(timed)}")
    abut = 0
    gaps: list[float] = []
    prev_e = None
    for ln in timed:
        a, _b = ln.split("  ", 1)
        s, e = a.split("–")
        s, e = parse_txt_time(s), parse_txt_time(e)
        if prev_e is not None:
            g = s - prev_e
            if g < 0.05:
                abut += 1
            else:
                gaps.append(g)
        prev_e = e
    print(
        f"abut={abut} with_gap={len(gaps)}"
        + (f" gap_min={min(gaps):.2f} gap_p50={sorted(gaps)[len(gaps) // 2]:.2f}" if gaps else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
