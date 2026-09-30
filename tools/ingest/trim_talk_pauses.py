#!/usr/bin/env python3
"""句间粗剪：明显长于均值的停顿，收到均值加安全余量。

ingest 阶段剪 open/close（不剪原片 run-*，HUD 时间轴才不会漂）。
HUD preview 出完后再剪 hud-renders/*-hud-preview.mp4。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path


# 检测做在人声频段上，全频能量会把风和车当成「还在说话」
NOISE_DB = -40.0
SPEECH_HIGHPASS = 280
SPEECH_LOWPASS = 3500
MIN_SILENCE = 0.22
# 短音节也要留下，否则会被并进「超长停顿」从左边剪掉
MIN_SPEECH = 0.08
OUTLIER_RATIO = 2.0
# 思考停顿常在均值以上 1 秒左右，+0.7 会误伤
OUTLIER_EXTRA = 1.2
MIN_KEEP_GAP = 0.55
HEAD_TAIL = 0.45
# 超长停顿收到「均值 + 安全余量」，不要收到均值，避免切到下一句开头
GAP_SAFETY = 0.45
# 片尾常更轻、更碎，最后几秒整段保留
END_PROTECT = 3.0
# Silero VAD：人声 vs 风/车。时间戳是百分之一秒。
DEFAULT_VAD_MODEL = Path.home() / "Movies/running-content/.models/ggml-silero-v5.1.2.bin"
VAD_MERGE_GAP = 0.25
VAD_SEGMENT_RE = re.compile(
    r"Speech segment \d+: start = ([0-9.]+), end = ([0-9.]+)"
)
SILENCE_RE = re.compile(
    r"silence_(?:start|end):\s*([0-9.]+)(?:\s*\|\s*silence_duration:\s*([0-9.]+))?"
)


def probe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(raw)


def probe_video_bitrate(path: Path) -> int:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=bit_rate",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    try:
        return int(raw)
    except ValueError:
        return 12_000_000


def detect_silences(path: Path) -> list[tuple[float, float]]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(path),
        "-af",
        f"silencedetect=noise={NOISE_DB}dB:d={MIN_SILENCE}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    text = proc.stderr
    starts: list[float] = []
    silences: list[tuple[float, float]] = []
    for line in text.splitlines():
        if "silence_start:" in line:
            match = SILENCE_RE.search(line)
            if match:
                starts.append(float(match.group(1)))
        elif "silence_end:" in line:
            match = SILENCE_RE.search(line)
            if match and starts:
                start = starts.pop(0)
                end = float(match.group(1))
                if end > start:
                    silences.append((start, end))
    duration = probe_duration(path)
    if starts:
        silences.append((starts[0], duration))
    return silences


def invert_to_speech(
    silences: list[tuple[float, float]], duration: float
) -> list[tuple[float, float]]:
    speech: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in silences:
        if start > cursor + 0.01:
            speech.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor + 0.01:
        speech.append((cursor, duration))
    return speech


def drop_micro_speech(
    speech: list[tuple[float, float]], min_len: float
) -> list[tuple[float, float]]:
    return [(a, b) for a, b in speech if b - a >= min_len]


def mid_gaps(
    speech: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    gaps: list[tuple[float, float]] = []
    for i in range(len(speech) - 1):
        a = speech[i][1]
        b = speech[i + 1][0]
        if b > a + 0.01:
            gaps.append((a, b))
    return gaps


def is_outlier(length: float, mean: float) -> bool:
    if mean <= 0:
        return length >= 1.2
    return length >= max(mean * OUTLIER_RATIO, mean + OUTLIER_EXTRA) and length >= 1.2


def extract_wav(src: Path, af: str | None = None) -> Path:
    fd, name = tempfile.mkstemp(suffix=".wav", prefix="trimwav-")
    os.close(fd)
    tmp = Path(name)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if af:
        cmd.extend(["-af", af])
    cmd.append(str(tmp))
    subprocess.run(cmd, check=True)
    return tmp


def extract_speech_band_wav(src: Path) -> Path:
    """抽 16k 单声道，只留人声频段。能量门限的兜底方案。"""
    return extract_wav(src, af=f"highpass=f={SPEECH_HIGHPASS},lowpass=f={SPEECH_LOWPASS}")


def detect_speech_vad(wav: Path, model: Path) -> list[tuple[float, float]]:
    """whisper.cpp Silero VAD。打印的 start/end 是百分之一秒，要除以 100。"""
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
    speech: list[tuple[float, float]] = []
    for line in proc.stdout.splitlines():
        match = VAD_SEGMENT_RE.search(line)
        if not match:
            continue
        start = float(match.group(1)) / 100.0
        end = float(match.group(2)) / 100.0
        if end > start:
            speech.append((start, end))
    return speech


def merge_speech(
    speech: list[tuple[float, float]], max_gap: float
) -> list[tuple[float, float]]:
    if not speech:
        return []
    merged = [speech[0]]
    for start, end in speech[1:]:
        if start <= merged[-1][1] + max_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def keep_windows(
    speech: list[tuple[float, float]],
    duration: float,
    keep_gap: float,
    cut_gaps: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not speech:
        return [(0.0, duration)]
    cuts = {(round(a, 2), round(b, 2)) for a, b in cut_gaps}
    windows: list[tuple[float, float]] = []
    first = speech[0][0]
    lead = min(HEAD_TAIL, first)
    start0 = max(0.0, first - lead)
    windows.append((start0, speech[0][1]))
    for i in range(len(speech) - 1):
        gap_a, gap_b = speech[i][1], speech[i + 1][0]
        gap_len = gap_b - gap_a
        if (round(gap_a, 2), round(gap_b, 2)) in cuts:
            left = min(keep_gap, gap_len)
            right = min(HEAD_TAIL, gap_len)
            if left + right >= gap_len - 0.05:
                windows.append((gap_a, gap_b))
            else:
                windows.append((gap_a, gap_a + left))
                windows.append((gap_b - right, gap_b))
        elif gap_len > 0.01:
            windows.append((gap_a, gap_b))
        windows.append(speech[i + 1])
    last_end = speech[-1][1]
    tail = min(HEAD_TAIL, max(0.0, duration - last_end))
    if tail > 0 and (not windows or windows[-1][1] < last_end + tail):
        windows[-1] = (windows[-1][0], min(duration, last_end + tail))
    protect_from = max(0.0, duration - END_PROTECT)
    if protect_from < duration:
        windows.append((protect_from, duration))
    merged: list[tuple[float, float]] = []
    for a, b in windows:
        if b - a < 0.04:
            continue
        if merged and a <= merged[-1][1] + 0.01:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def encode_keep(src: Path, dest: Path, windows: list[tuple[float, float]]) -> None:
    """每段音画用同一起止 trim，再 concat，避免 select/aselect 各切各的导致漂移。"""
    if not windows:
        raise ValueError("no windows to keep")
    bitrate = probe_video_bitrate(src)
    chains: list[str] = []
    pair: list[str] = []
    for i, (start, end) in enumerate(windows):
        chains.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        chains.append(
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]"
        )
        pair.append(f"[v{i}][a{i}]")
    n = len(windows)
    graph = (
        ";".join(chains)
        + ";"
        + "".join(pair)
        + f"concat=n={n}:v=1:a=1[vraw][araw];"
        "[vraw]fps=30,format=yuv420p[v];"
        "[araw]aresample=async=1:first_pts=0[a]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(src),
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "hevc_videotoolbox",
        "-b:v",
        str(bitrate),
        "-tag:v",
        "hvc1",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-fps_mode",
        "cfr",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    subprocess.run(cmd, check=True)


def plan_clip(
    path: Path,
    speech_detect: str = "vad",
    vad_model: Path | None = None,
) -> dict:
    duration = probe_duration(path)
    if speech_detect == "vad":
        model = vad_model or DEFAULT_VAD_MODEL
        if not model.is_file():
            raise SystemExit(f"VAD model not found: {model}")
        wav = extract_wav(path)
        try:
            speech = detect_speech_vad(wav, model)
        finally:
            wav.unlink(missing_ok=True)
        speech = merge_speech(speech, VAD_MERGE_GAP)
        speech = drop_micro_speech(speech, MIN_SPEECH)
    else:
        wav = extract_speech_band_wav(path)
        try:
            silences = detect_silences(wav)
        finally:
            wav.unlink(missing_ok=True)
        speech = drop_micro_speech(invert_to_speech(silences, duration), MIN_SPEECH)
    gaps = mid_gaps(speech)
    lengths = [b - a for a, b in gaps]
    mean = statistics.mean(lengths) if lengths else 0.0
    keep_gap = max(MIN_KEEP_GAP, mean + GAP_SAFETY) if mean else MIN_KEEP_GAP
    outliers = [(a, b) for a, b in gaps if is_outlier(b - a, mean)]
    windows = keep_windows(speech, duration, keep_gap, outliers)
    kept = sum(b - a for a, b in windows)
    return {
        "path": path,
        "duration": duration,
        "gap_count": len(gaps),
        "mean": mean,
        "keep_gap": keep_gap,
        "outliers": outliers,
        "windows": windows,
        "kept": kept,
        "saved": duration - kept,
        "speech_detect": speech_detect,
        "speech_count": len(speech),
    }


def find_talk_clips(media_dir: Path, targets: set[str]) -> list[Path]:
    found: list[Path] = []
    if "open" in targets or "close" in targets:
        for role in ("open", "close"):
            if role not in targets:
                continue
            matches = sorted(
                p
                for p in media_dir.glob(f"*-{role}.mp4")
                if "hud" not in p.name.lower() and "raw" not in p.stem
            )
            if matches:
                found.append(matches[0])
    if "preview" in targets:
        hud_dir = media_dir / "hud-renders"
        if hud_dir.is_dir():
            found.extend(
                sorted(
                    p
                    for p in hud_dir.glob("*-hud-preview.mp4")
                    if not p.stem.endswith("-raw") and "trimtmp" not in p.stem
                )
            )
    return found


def raw_path(clip: Path) -> Path:
    return clip.with_name(clip.stem + "-raw" + clip.suffix)


def apply_clip(plan: dict, dry_run: bool) -> None:
    clip: Path = plan["path"]
    outliers: list[tuple[float, float]] = plan["outliers"]
    raw = raw_path(clip)
    if not outliers:
        print(
            f"{clip.name}: 检测 {plan.get('speech_detect', '?')}，"
            f"没有明显长于均值的句间停顿，不剪"
        )
        if dry_run:
            return
        if raw.exists():
            shutil.copy2(raw, clip)
            print(f"  已从 {raw.name} 恢复")
        return
    print(
        f"{clip.name}: 检测 {plan.get('speech_detect', '?')}，"
        f"时长 {plan['duration']:.2f}s，"
        f"句间 {plan['gap_count']} 个，均值 {plan['mean']:.2f}s，"
        f"超长 {len(outliers)} 个，约省 {plan['saved']:.2f}s"
    )
    for a, b in outliers:
        print(f"  剪 {a:.2f}-{b:.2f}s ({b - a:.2f}s -> {plan['keep_gap']:.2f}s)")
    if dry_run:
        return
    if not raw.exists():
        shutil.move(str(clip), str(raw))
    src = raw if raw.exists() else clip
    tmp = clip.with_name(clip.stem + "-trimtmp" + clip.suffix)
    encode_keep(src, tmp, plan["windows"])
    tmp.replace(clip)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shorten outlier pauses in open/close or HUD preview clips."
    )
    parser.add_argument("--media-dir", required=True)
    parser.add_argument(
        "--targets",
        default="open,close",
        help="Comma list: open,close,preview. preview = hud-renders/*-hud-preview.mp4",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--speech-detect",
        choices=("vad", "band"),
        default="vad",
        help="vad=Silero 人声检测（默认）；band=人声频段能量门限",
    )
    parser.add_argument(
        "--vad-model",
        default=str(DEFAULT_VAD_MODEL),
        help="whisper.cpp ggml Silero VAD model",
    )
    args = parser.parse_args()
    media_dir = Path(args.media_dir).expanduser().resolve()
    targets = {part.strip() for part in args.targets.split(",") if part.strip()}
    clips = find_talk_clips(media_dir, targets)
    if not clips:
        print(f"No clips for targets {sorted(targets)} in {media_dir}")
        return 0
    dry_run = not args.apply
    print(
        f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}  "
        f"detect={args.speech_detect}"
    )
    vad_model = Path(args.vad_model).expanduser()
    for clip in clips:
        source = raw_path(clip) if raw_path(clip).exists() else clip
        plan = plan_clip(source, speech_detect=args.speech_detect, vad_model=vad_model)
        plan["path"] = clip
        apply_clip(plan, dry_run=dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
