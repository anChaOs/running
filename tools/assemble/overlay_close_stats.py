#!/usr/bin/env python3
"""把高驰训练截图叠到 close 左侧。默认多张均分各播一次。--holds 按秒循环，剩余时间停在第一张。不覆盖原 close。"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import Counter
from pathlib import Path


DATE_STATS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-stats-\d+$")
RAW_HINTS = ("screenshot", "coros", "截图")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
# 叠在画面左侧，高度约为成片的 82%，半透明
OVERLAY_H_RATIO = 0.82
OVERLAY_X = 40
OVERLAY_ALPHA = 0.82
FADE_IN = 0.35


def run(cmd: list[str], dry_run: bool = False) -> None:
    print("$", " ".join(str(part) for part in cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


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


def probe_wh(path: Path) -> tuple[int, int]:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        text=True,
    ).strip()
    w_s, h_s = raw.split(",")
    return int(w_s), int(h_s)


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
            "-show_entries",
            "format=bit_rate",
            "-of",
            "default=nw=1",
            str(path),
        ],
        text=True,
    )
    bits: list[int] = []
    for line in raw.splitlines():
        if "=" in line:
            try:
                bits.append(int(line.split("=", 1)[1]))
            except ValueError:
                continue
    bit_rate = max(bits) if bits else 0
    return bit_rate if bit_rate >= 1_000_000 else 28_000_000


def find_close(media_dir: Path) -> Path:
    closes = sorted(
        p
        for p in media_dir.glob("*-close.mp4")
        if "stats" not in p.name and "hud" not in p.name
    )
    if not closes:
        raise SystemExit(f"No close clip in {media_dir}")
    return closes[0]


def find_stats(media_dir: Path) -> list[Path]:
    named = sorted(
        p
        for p in media_dir.iterdir()
        if p.is_file() and DATE_STATS_RE.match(p.stem) and p.suffix.lower() in IMAGE_EXT
    )
    if named:
        return named
    raw: list[Path] = []
    for p in sorted(media_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXT:
            continue
        n = p.name.lower()
        if n.startswith("cover-") or "hud" in n:
            continue
        if any(hint in n for hint in RAW_HINTS):
            raw.append(p)
    return raw


def rename_raw_stats(media_dir: Path, date: str, images: list[Path], dry_run: bool) -> list[Path]:
    """未按 stats-NN 命名的高驰截图，改成 YYYY-MM-DD-stats-01.jpg。"""
    out: list[Path] = []
    idx = 1
    for src in images:
        if DATE_STATS_RE.match(src.stem):
            out.append(src)
            continue
        dest = media_dir / f"{date}-stats-{idx:02d}{src.suffix.lower()}"
        while dest.exists() and dest.resolve() != src.resolve():
            idx += 1
            dest = media_dir / f"{date}-stats-{idx:02d}{src.suffix.lower()}"
        print(f"mv {src.name} -> {dest.name}")
        if not dry_run and src.resolve() != dest.resolve():
            src.rename(dest)
        out.append(dest if not dry_run else dest)
        idx += 1
    return out


def build_playlist(n_images: int, holds: list[float] | None, dur: float) -> list[tuple[int, float]]:
    """(图片下标, 秒)。有 holds 则按顺序循环，多出来的时间给第一张。"""
    if n_images == 1:
        return [(0, dur)]
    if not holds:
        slice_d = dur / n_images
        return [(i, slice_d) for i in range(n_images)]
    if len(holds) != n_images:
        raise SystemExit(f"--holds 要 {n_images} 个数，现在是 {len(holds)}")
    if any(h <= 0 for h in holds):
        raise SystemExit("--holds 每项必须 > 0")
    cycle = sum(holds)
    slots: list[tuple[int, float]] = []
    t = 0.0
    while t + cycle <= dur + 1e-6:
        for i, h in enumerate(holds):
            slots.append((i, h))
        t += cycle
    remain = dur - t
    if remain > 0.05:
        slots.append((0, remain))
    total = sum(h for _i, h in slots)
    if slots and abs(total - dur) > 0.01:
        idx, h = slots[-1]
        slots[-1] = (idx, h + (dur - total))
    return slots


def overlay_filter(
    n_stills: int,
    close_h: int,
    close_dur: float,
    playlist: list[tuple[int, float]],
    fade: float,
) -> str:
    h = max(320, int(close_h * OVERLAY_H_RATIO))
    parts: list[str] = []
    uses = Counter(i for i, _hold in playlist)
    for i in range(n_stills):
        src = i + 1
        scaled = f"s{i}"
        parts.append(
            f"[{src}:v]scale=-2:{h}:force_original_aspect_ratio=decrease,"
            f"format=rgba,colorchannelmixer=aa={OVERLAY_ALPHA:.2f}[{scaled}]"
        )
        n = uses[i]
        if n <= 1:
            parts.append(f"[{scaled}]null[s{i}c0]")
        else:
            outs = "".join(f"[s{i}c{k}]" for k in range(n))
            parts.append(f"[{scaled}]split={n}{outs}")

    use_idx = [0] * n_stills
    piece_labels: list[str] = []
    for pi, (img_i, hold) in enumerate(playlist):
        k = use_idx[img_i]
        use_idx[img_i] += 1
        src_lab = f"s{img_i}c{k}"
        fade_d = min(fade, hold / 2.0) if hold > 0.2 else 0.0
        fade_out_st = max(0.0, hold - fade_d)
        piece = f"[{src_lab}]trim=duration={hold:.4f},setpts=PTS-STARTPTS"
        if fade_d >= 0.05:
            piece += (
                f",fade=t=in:st=0:d={fade_d:.2f}:alpha=1"
                f",fade=t=out:st={fade_out_st:.2f}:d={fade_d:.2f}:alpha=1"
            )
        piece += f"[p{pi}]"
        parts.append(piece)
        piece_labels.append(f"[p{pi}]")

    if len(playlist) == 1:
        parts.append(f"{piece_labels[0]}fps=60,settb=1/60[slide]")
    else:
        parts.append(
            f"{''.join(piece_labels)}concat=n={len(playlist)}:v=1:a=0,fps=60,settb=1/60[slide]"
        )
    parts.append(f"[slide]null[st]")
    parts.append(
        f"[0:v][st]overlay=x={OVERLAY_X}:y=(H-h)/2:shortest=1,format=yuv420p[v]"
    )
    d = f"{close_dur:.6f}"
    parts.append(
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"aresample=async=1:first_pts=0,"
        f"apad=whole_dur={d},atrim=0:{d},asetpts=PTS-STARTPTS[a]"
    )
    return ";".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Overlay COROS stats screenshots on close, left side.")
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--holds",
        default="",
        help="Seconds per image, comma-separated, same order as stats-01, stats-02. "
        "Cycles until close ends; leftover stays on the first image. Empty = one pass, equal split.",
    )
    parser.add_argument("--fade", type=float, default=FADE_IN, help="Per-slide alpha fade seconds")
    args = parser.parse_args()

    media_dir = Path(args.media_dir).expanduser().resolve()
    close = find_close(media_dir)
    date = close.name[:10]
    images = find_stats(media_dir)
    if not images:
        raise SystemExit(
            f"No stats screenshots in {media_dir}. "
            "Put COROS shots there (Screenshot_* / *coros*) and rerun."
        )
    images = rename_raw_stats(media_dir, date, images, args.dry_run)
    if args.dry_run:
        images = find_stats(media_dir) or images

    dur = probe_duration(close)
    _w, height = probe_wh(close)
    bitrate = probe_video_bitrate(close)
    n = len(images)
    holds = [float(x) for x in args.holds.split(",") if x.strip()] if args.holds.strip() else None
    playlist = build_playlist(n, holds, dur)
    out = media_dir / f"{date}-close-stats.mp4"

    cmd: list[str] = ["ffmpeg", "-y", "-hide_banner", "-i", str(close)]
    for img in images:
        # 静帧默认 25fps，后面 fps=60 会把轮播加速；按 60fps 读满 close 时长再 trim
        cmd.extend(["-framerate", "60", "-loop", "1", "-t", f"{dur:.4f}", "-i", str(img)])
    cmd.extend(
        [
            "-filter_complex",
            overlay_filter(n, height, dur, playlist, args.fade),
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
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    print(f"Close: {close.name}  {dur:.3f}s")
    print(f"Stats: {', '.join(p.name for p in images)}")
    print(
        "Playlist: "
        + " → ".join(f"{images[i].name}/{h:.2f}s" for i, h in playlist)
    )
    print(f"Out: {out.name}  alpha={OVERLAY_ALPHA}  height={int(height * OVERLAY_H_RATIO)}px")
    run(cmd, dry_run=args.dry_run)
    if not args.dry_run:
        print(subprocess.check_output(["ls", "-lh", str(out)], text=True).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
