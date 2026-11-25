#!/usr/bin/env python3
"""从视频音轨里检测高驰（COROS）手表开表提示音（窄带高频「滴」/双音），反推相机时钟偏移。

典型 COROS 开表提示音：两声短促窄带高频纯音（~60–100ms/声，间隔 ~50–150ms，
基频或强谐波落在 2.0–9.0 kHz，邻频对比度极高）。

输出每个候选提示音的原片秒数；若提供 --fit，同时计算：
  clock_offset_s = FIT_start - camera_time(beep)
正数表示相机时钟比手表 GPS 慢，可直接喂给 `tools/program_edl.py calibrate`。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
import ingest_run_media as ingest  # noqa: E402
import media_layout  # noqa: E402

SAMPLE_RATE = 48000
N_FFT = 2048
HOP = 512
DEFAULT_MAX_OFFSET_S = 120.0


def parse_timecode(value: str) -> float:
    """解析秒数（103 / 103.5）或时分秒（1:43 / 0:01:43.5）为浮点秒。"""
    text = str(value).strip()
    if not text:
        raise ValueError("empty time value")
    parts = text.split(":")
    if len(parts) == 1:
        sec = float(parts[0])
    elif len(parts) == 2:
        minutes = float(parts[0])
        seconds = float(parts[1])
        if minutes < 0 or seconds < 0 or seconds >= 60:
            raise ValueError(f"invalid MM:SS timecode: {value}")
        sec = minutes * 60.0 + seconds
    elif len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        if hours < 0 or minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
            raise ValueError(f"invalid HH:MM:SS timecode: {value}")
        sec = hours * 3600.0 + minutes * 60.0 + seconds
    else:
        raise ValueError(f"invalid timecode: {value}")
    if sec < 0:
        raise ValueError(f"timecode must be >= 0: {value}")
    return sec


def _extract_mono_pcm(video_path: Path, start_s: float = 0.0, end_s: float | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error"]
    if start_s > 0:
        cmd.extend(["-ss", f"{start_s:.6f}"])
    if end_s is not None:
        duration = end_s - start_s
        if duration <= 0:
            raise ValueError(f"empty search window: {start_s}..{end_s}")
        cmd.extend(["-t", f"{duration:.6f}"])
    cmd.extend(["-i", str(video_path), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"])
    raw = subprocess.check_output(cmd)
    return np.frombuffer(raw, dtype=np.float32)


def detect_beeps_from_pcm(
    samples: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    offset_s: float = 0.0,
    min_freq_hz: float = 2000.0,
    max_freq_hz: float = 9000.0,
    min_local_ratio: float = 15.0,
    min_mag: float = 2.0,
    min_frames: int = 3,
    group_gap_s: float = 0.35,
) -> list[dict]:
    """在单声道 float32 PCM 中找窄带高频持续纯音，并把相近音符归成一次提示音事件。"""
    if len(samples) < N_FFT:
        return []
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sample_rate)
    band_mask = (freqs >= min_freq_hz) & (freqs <= max_freq_hz)
    band_freqs = freqs[band_mask]
    if len(band_freqs) < 25:
        return []

    win = np.hanning(N_FFT).astype(np.float32)
    n_frames = (len(samples) - N_FFT) // HOP + 1
    if n_frames <= 0:
        return []

    hits: list[tuple[int, float, float, float, float]] = []
    for i in range(n_frames):
        seg = samples[i * HOP : i * HOP + N_FFT]
        mag = np.abs(np.fft.rfft(seg * win))[band_mask]
        j = int(np.argmax(mag))
        peak = float(mag[j])
        if peak < min_mag:
            continue
        lo = max(0, j - 12)
        hi = min(len(mag), j + 13)
        left = mag[lo : max(lo, j - 3)]
        right = mag[min(hi, j + 4) : hi]
        neighbors = np.concatenate([left, right]) if (len(left) or len(right)) else mag
        bg = float(np.median(neighbors)) + 1e-8
        local_ratio = peak / bg
        if local_ratio >= min_local_ratio:
            t = offset_s + (i * HOP + N_FFT / 2.0) / sample_rate
            hits.append((i, t, float(band_freqs[j]), local_ratio, peak))

    # 连续同频帧合成单个音符
    notes: list[dict] = []
    current: list[tuple[int, float, float, float, float]] = []

    def _flush() -> None:
        if len(current) >= min_frames:
            # 音符起点取第一帧窗前沿，比窗中心更贴近按下按键的实际时刻
            start_t = offset_s + (current[0][0] * HOP) / sample_rate
            end_t = offset_s + (current[-1][0] * HOP + N_FFT) / sample_rate
            notes.append(
                {
                    "start_s": round(start_t, 3),
                    "end_s": round(end_t, 3),
                    "duration_ms": round((end_t - start_t) * 1000.0, 1),
                    "freq_hz": round(float(np.median([row[2] for row in current])), 1),
                    "max_local_ratio": round(max(row[3] for row in current), 1),
                    "max_mag": round(max(row[4] for row in current), 2),
                    "frames": len(current),
                }
            )

    for hit in hits:
        if current and (hit[0] - current[-1][0] <= 2) and abs(hit[2] - current[-1][2]) <= 60.0:
            current.append(hit)
        else:
            _flush()
            current = [hit]
    _flush()

    # 相邻音符（如 COROS 开表「滴-滴」双音）合成一次提示音事件
    events: list[dict] = []
    for note in notes:
        if events and (note["start_s"] - events[-1]["end_s"]) <= group_gap_s:
            ev = events[-1]
            ev["notes"].append(note)
            ev["end_s"] = note["end_s"]
            ev["note_count"] = len(ev["notes"])
            if note["max_mag"] > ev["max_mag"]:
                ev["peak_freq_hz"] = note["freq_hz"]
                ev["max_mag"] = note["max_mag"]
            ev["max_local_ratio"] = max(ev["max_local_ratio"], note["max_local_ratio"])
        else:
            events.append(
                {
                    "start_s": note["start_s"],
                    "end_s": note["end_s"],
                    "note_count": 1,
                    "peak_freq_hz": note["freq_hz"],
                    "max_local_ratio": note["max_local_ratio"],
                    "max_mag": note["max_mag"],
                    "notes": [note],
                }
            )
    return events


def detect_beeps(
    video_path: Path,
    *,
    start_s: float = 0.0,
    end_s: float | None = None,
    min_local_ratio: float = 15.0,
    min_mag: float = 2.0,
) -> list[dict]:
    samples = _extract_mono_pcm(video_path, start_s=start_s, end_s=end_s)
    return detect_beeps_from_pcm(
        samples,
        offset_s=start_s,
        min_local_ratio=min_local_ratio,
        min_mag=min_mag,
    )


def implied_clock_offset_s(video_path: Path, beep_src_s: float, fit_path: Path) -> float:
    """给定视频原片上的开表时刻 beep_src_s，算 FIT_start - camera_time(beep)。"""
    duration = ingest.run_ffprobe_duration(video_path)
    if duration is None:
        raise ValueError(f"cannot read duration: {video_path}")
    video_start, _ = ingest.video_window(video_path, duration)
    fit_start, _, _ = ingest.fit_window(fit_path)
    if fit_start is None:
        raise ValueError(f"FIT has no start time: {fit_path}")
    beep_camera_time = video_start + timedelta(seconds=float(beep_src_s))
    return (fit_start - beep_camera_time).total_seconds()


def pick_start_beep(events: list[dict], *, max_offset_s: float | None = DEFAULT_MAX_OFFSET_S) -> dict | None:
    """在候选提示音里挑最像「开表」的那次：排除超出时钟偏差阈值的跑中提示音，优先多音且最靠后。"""
    if not events:
        return None
    plausible = []
    for ev in events:
        off = ev.get("implied_clock_offset_s")
        if off is not None and max_offset_s is not None and abs(float(off)) > max_offset_s:
            continue
        plausible.append(ev)
    if not plausible:
        return None
    multi = [ev for ev in plausible if ev["note_count"] >= 2]
    pool = multi or plausible
    return pool[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect COROS watch start beep in a video clip.")
    parser.add_argument("--video", required=True, help="Video clip path (e.g. raw/YYYY-MM-DD-open.mp4)")
    parser.add_argument("--fit", help="Optional FIT path; computes implied clock_offset_s")
    parser.add_argument("--media-dir", help="Optional media dir; auto-finds FIT and prints calibrate command")
    parser.add_argument("--after", type=parse_timecode, default=0.0, help="Scan after this source time (sec or MM:SS)")
    parser.add_argument("--before", type=parse_timecode, help="Scan before this source time (sec or MM:SS)")
    parser.add_argument("--around", type=parse_timecode, help="Scan around this source time (sec or MM:SS)")
    parser.add_argument("--window", type=float, default=6.0, help="Half-window in seconds for --around (default 6)")
    parser.add_argument(
        "--max-offset",
        type=float,
        default=DEFAULT_MAX_OFFSET_S,
        help=f"Reject start-beep candidates with |implied_clock_offset_s| > this threshold (default {DEFAULT_MAX_OFFSET_S:.0f}s)",
    )
    parser.add_argument("--min-ratio", type=float, default=15.0, help="Minimum narrowband local contrast ratio")
    parser.add_argument("--min-mag", type=float, default=2.0, help="Minimum FFT peak magnitude")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")

    fit_path: Path | None = None
    if args.fit:
        fit_path = Path(args.fit).expanduser().resolve()
    elif args.media_dir:
        fits = media_layout.find_fits(Path(args.media_dir).expanduser().resolve())
        if fits:
            fit_path = fits[0]

    start_s = max(0.0, args.after)
    end_s = args.before
    if args.around is not None:
        start_s = max(0.0, args.around - args.window)
        end_s = args.around + args.window

    events = detect_beeps(
        video,
        start_s=start_s,
        end_s=end_s,
        min_local_ratio=args.min_ratio,
        min_mag=args.min_mag,
    )
    if fit_path is not None and fit_path.is_file():
        for ev in events:
            off = round(implied_clock_offset_s(video, ev["start_s"], fit_path), 3)
            ev["implied_clock_offset_s"] = off
            ev["plausible_start"] = abs(off) <= args.max_offset

    best = pick_start_beep(events, max_offset_s=args.max_offset)
    payload = {
        "video": str(video),
        "fit": str(fit_path) if fit_path else None,
        "window": {"start_s": start_s, "end_s": end_s},
        "max_offset_s": args.max_offset,
        "events": events,
        "recommended": best,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not events:
        print(f"No watch beep detected in {video.name} (window {start_s:.1f}s..{end_s or 'end'})")
        return 1

    print(f"Detected {len(events)} watch beep candidate(s) in {video.name}:")
    for idx, ev in enumerate(events, start=1):
        if ev is best:
            mark = " <-- recommended"
        elif ev.get("plausible_start") is False:
            mark = f" [ignored: |offset| > {args.max_offset:.0f}s, likely mid-run countdown/lap beep]"
        else:
            mark = ""
        off_str = f", implied clock_offset_s={ev['implied_clock_offset_s']:+.3f}s" if "implied_clock_offset_s" in ev else ""
        print(
            f"  #{idx}: t={ev['start_s']:.3f}..{ev['end_s']:.3f}s "
            f"(notes={ev['note_count']}, peak={ev['peak_freq_hz']:.0f}Hz, "
            f"ratio={ev['max_local_ratio']:.1f}, mag={ev['max_mag']:.1f}{off_str}){mark}"
        )
    if best is None:
        print(
            f"\nNo plausible start beep within ±{args.max_offset:.0f}s clock offset "
            "(adjust --max-offset if camera clock truly drifted farther)."
        )
        return 1
    if args.media_dir:
        media_dir = Path(args.media_dir).expanduser().resolve()
        rel = media_layout.rel_media_path(video, media_dir)
        print(
            "\nCalibrate command:\n"
            f"  .venv/bin/python tools/program_edl.py --media-dir {media_dir} "
            f"calibrate --clip {rel} --at {best['start_s']:.3f} --source beep"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
