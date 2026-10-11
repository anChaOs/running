#!/usr/bin/env python3
"""字幕对时 / 质检共用：读写 subtitles.txt / SRT、faster-whisper 词级时间、Silero VAD、按字对齐。

只读音频和字幕文字，不改字。模型只从 ModelScope 拉，不连 huggingface.co。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

MODELSCOPE_REPO = "pengzhendong/faster-whisper-large-v3-turbo"
MODELSCOPE_URL = "https://www.modelscope.cn/models/{repo}/resolve/master/{name}"
MODEL_FILES = [
    "config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
    "model.bin",
]
DEFAULT_MODEL_DIR = Path.home() / "Movies/running-content/.models/faster-whisper-large-v3-turbo"
SR = 16000

CUE_RE = re.compile(r"^(\d+:\d{2}:\d{2}\.\d{2})[–-](\d+:\d{2}:\d{2}\.\d{2})\s+(.*)$")
SRT_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{3})")
PUNCT = re.compile(r"[\s,，。.!！？?、；;：:·…—_\-（）()【】\[\]{}《》<>“”\"'‘’/\\~～]+")
# 语气词：识别稿里有、定稿里常删，不当成「漏字幕」
FILLERS = set("呃嗯额啊哦噢唉诶欸哎嘛呀")


# ---------- 读写 ----------

@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_txt_time(t: str) -> float:
    h, m, rest = t.split(":")
    s, cs = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0


def fmt_txt_time(t: float) -> str:
    cs = int(round(max(t, 0.0) * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def fmt_srt_time(t: float) -> str:
    ms = int(round(max(t, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path: Path, cues: list[Cue]) -> None:
    path.write_text(
        "\n".join(f"{i}\n{fmt_srt_time(c.start)} --> {fmt_srt_time(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)),
        encoding="utf-8",
    )


def fmt_clock(t: float) -> str:
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def load_txt(path: Path) -> tuple[list[str], list[Cue]]:
    header: list[str] = []
    cues: list[Cue] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if not cues:
                header.append(line)
            continue
        m = CUE_RE.match(line)
        if not m:
            raise SystemExit(f"unparsed line in {path}: {raw!r}")
        cues.append(Cue(parse_txt_time(m.group(1)), parse_txt_time(m.group(2)), m.group(3).strip()))
    return header, cues


def write_txt(path: Path, header: list[str], cues: list[Cue]) -> None:
    lines = list(header)
    if lines:
        lines.append("")
    for c in cues:
        lines.append(f"{fmt_txt_time(c.start)}–{fmt_txt_time(c.end)}  {c.text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_srt(path: Path) -> list[Cue]:
    cues: list[Cue] = []
    for blk in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = [x for x in blk.strip().splitlines() if x.strip()]
        for i, ln in enumerate(lines):
            m = SRT_TIME.search(ln)
            if m:
                g = [int(x) for x in m.groups()]
                a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                cues.append(Cue(a, b, "\\N".join(lines[i + 1:])))
                break
    return cues


def load_any(path: Path) -> list[Cue]:
    if path.suffix.lower() == ".srt":
        return load_srt(path)
    return load_txt(path)[1]


# ---------- 文字归一 ----------

_cc = None


def to_simplified(text: str) -> str:
    global _cc
    if _cc is None:
        try:
            import opencc  # opencc-python-reimplemented

            _cc = opencc.OpenCC("t2s")
        except Exception:  # noqa: BLE001
            _cc = False
    return _cc.convert(text) if _cc else text


def norm(text: str) -> str:
    return PUNCT.sub("", to_simplified(text)).lower()


# ---------- 模型 ----------

def ensure_model(model_dir: Path) -> Path:
    """缺文件就从 ModelScope 下载（约 1.6 GB）。不碰 huggingface.co。"""
    model_dir.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        dst = model_dir / name
        if dst.is_file() and dst.stat().st_size > 0:
            continue
        url = MODELSCOPE_URL.format(repo=MODELSCOPE_REPO, name=name)
        print(f"[model] 下载 {url}", file=sys.stderr)
        tmp = dst.with_suffix(dst.suffix + ".part")
        with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        tmp.rename(dst)
    return model_dir


_model = None


def get_model(model_dir: Path, compute_type: str = "int8"):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        ensure_model(model_dir)
        _model = WhisperModel(str(model_dir), device="cpu", compute_type=compute_type)
    return _model


def load_audio(wav: Path):
    """读 16k 单声道 16-bit wav（成片抽出来的那条），返回 float32 numpy。"""
    import wave

    import numpy as np

    with wave.open(str(wav), "rb") as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(
                f"{wav} 不是 16k 单声道 16-bit wav。先：ffmpeg -y -i run-final.mp4 -vn -ac 1 -ar 16000 {wav}"
            )
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


# ---------- VAD ----------

def vad_segments(audio, min_silence_ms: int = 150) -> list[tuple[float, float]]:
    """faster-whisper 自带的 Silero VAD（onnx 随包，不用下载）。"""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    ts = get_speech_timestamps(
        audio,
        VadOptions(threshold=0.5, min_silence_duration_ms=min_silence_ms, speech_pad_ms=30, min_speech_duration_ms=100),
    )
    return [(t["start"] / SR, t["end"] / SR) for t in ts]


# ---------- 识别（词级时间） ----------

@dataclass
class Word:
    s: float
    e: float
    w: str
    p: float


def transcribe_words(model, audio, *, prompt: str | None = None, offset: float = 0.0, vad_filter: bool = True,
                     beam_size: int = 5) -> list[Word]:
    segs, _info = model.transcribe(
        audio,
        language="zh",
        beam_size=beam_size,
        word_timestamps=True,
        vad_filter=vad_filter,
        vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 300} if vad_filter else None,
        condition_on_previous_text=False,
        initial_prompt=prompt,
    )
    out: list[Word] = []
    for s in segs:
        for w in s.words or []:
            out.append(Word(w.start + offset, w.end + offset, w.word, w.probability))
    return out


def cached_words(wav: Path, model_dir: Path, cache: Path | None, prompt: str | None) -> list[Word]:
    st = wav.stat()
    key = hashlib.sha1(f"{wav.resolve()}|{st.st_size}|{int(st.st_mtime)}|{model_dir.name}|{prompt or ''}".encode()).hexdigest()
    if cache and cache.is_file():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("key") == key:
            return [Word(**w) for w in data["words"]]
    t0 = time.time()
    print(f"[asr] 整条转写（词级时间）：{wav.name}，30 分钟音频在 M 系列 CPU 上约几分钟…", file=sys.stderr)
    words = transcribe_words(get_model(model_dir), load_audio(wav), prompt=prompt)
    print(f"[asr] 完成，用时 {time.time() - t0:.0f}s，{len(words)} 个词", file=sys.stderr)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"key": key, "words": [w.__dict__ for w in words]}, ensure_ascii=False),
            encoding="utf-8",
        )
    return words


def default_cache(wav: Path) -> Path:
    return wav.with_suffix(".words.json")


def default_report(wav: Path) -> Path:
    return wav.with_suffix(".align.json")


# ---------- 按字对齐 ----------

@dataclass
class AsrChar:
    s: float
    e: float
    ch: str
    p: float


def words_to_chars(words: list[Word]) -> list[AsrChar]:
    out: list[AsrChar] = []
    for w in words:
        t = norm(w.w)
        if not t:
            continue
        n = len(t)
        # 一个词内部按字均分：中文词通常 1～3 字，误差在百毫秒内
        for i, ch in enumerate(t):
            a = w.s + (w.e - w.s) * i / n
            b = w.s + (w.e - w.s) * (i + 1) / n
            out.append(AsrChar(a, b, ch, w.p))
    return out


@dataclass
class Span:
    """一条字幕在音频里的人声范围。"""

    ss: float | None = None
    se: float | None = None
    ratio: float = 0.0
    n: int = 0
    source: str = "none"  # global / guided / interp / none
    m0: float | None = None  # 第一个对上的字的起点（未外推）
    m1: float | None = None  # 最后一个对上的字的终点（未外推）
    asr_idx: list[int] = field(default_factory=list)


def align_chars(cue_texts: list[str], asr: list[AsrChar]) -> list[Span]:
    """定稿文字 → 识别字序列。只用完全相同的字做锚点，不猜。"""
    cue_chars: list[str] = []
    owner: list[int] = []
    for i, t in enumerate(cue_texts):
        for ch in norm(t):
            cue_chars.append(ch)
            owner.append(i)
    a = "".join(cue_chars)
    b = "".join(c.ch for c in asr)
    mp: list[int | None] = [None] * len(a)
    if a and b:
        sm = SequenceMatcher(a=a, b=b, autojunk=False)
        for blk in sm.get_matching_blocks():
            # 单个孤字匹配容易是巧合（的、了），至少两字连着对上才算锚点；英文字母要求更长
            if blk.size < 2:
                continue
            for k in range(blk.size):
                mp[blk.a + k] = blk.b + k
    spans = [Span(n=len(norm(t))) for t in cue_texts]
    pos = 0
    for i, t in enumerate(cue_texts):
        n = len(norm(t))
        idx = list(range(pos, pos + n))
        pos += n
        hits = [(k - idx[0], mp[k]) for k in idx if mp[k] is not None]
        sp = spans[i]
        if not hits or n == 0:
            continue
        sp.ratio = len(hits) / n
        sp.asr_idx = [h[1] for h in hits]
        first_k, first_j = hits[0]
        last_k, last_j = hits[-1]
        per_char = 0.2
        ss = asr[first_j].s - first_k * per_char
        se = asr[last_j].e + (n - 1 - last_k) * per_char
        sp.ss, sp.se = ss, se
        sp.m0, sp.m1 = asr[first_j].s, asr[last_j].e
    # 首尾没对上的字是按每字 0.2s 外推的，不能推进相邻条已经对上的字里
    prev = None
    for sp in spans:
        if sp.ss is None:
            continue
        if prev is not None and prev.se > sp.ss:
            prev.se = max(prev.m1, min(prev.se, sp.m0))
            sp.ss = min(sp.m0, max(sp.ss, prev.se))
        prev = sp
    return spans


def anchored(sp: Span, *, min_ratio: float = 0.5) -> bool:
    if sp.ss is None or sp.se is None or sp.n == 0:
        return False
    if sp.ratio < min_ratio:
        return False
    # 跨度离谱（字被对到很远的地方）也不算
    if sp.se - sp.ss > sp.n * 0.45 + 1.5:
        return False
    return sp.se > sp.ss


def merge_intervals(iv: list[tuple[float, float]], gap: float = 0.0) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1] + gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def island_at(t: float, vad: list[tuple[float, float]], tol: float = 0.05) -> tuple[float, float] | None:
    for a, b in vad:
        if a - tol <= t <= b + tol:
            return a, b
    return None
