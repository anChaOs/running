#!/usr/bin/env python3
"""生成只供人工检查的整条预览，不产生最终成片。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_spec import PREVIEW_SPEC  # noqa: E402

TIMELINE = PREVIEW_SPEC.timeline


RAW_PARTS = ("run-final", "review-preview", "hud-preview-raw", "-raw", "pre-", "-bad", "orient", "transpose")


def _one(paths: list[Path], label: str) -> Path | None:
    if len(paths) > 1:
        raise SystemExit(f"Multiple {label} candidates: {', '.join(p.name for p in paths)}")
    return paths[0] if paths else None


def discover(media_dir: Path) -> list[Path]:
    open_clip = _one(sorted(media_dir.glob("*-open.mp4")), "open")
    stats_close = sorted(media_dir.glob("*-close-stats.mp4"))
    close_clip = _one(stats_close, "close-stats") if stats_close else _one(sorted(media_dir.glob("*-close.mp4")), "close")
    runs = sorted(
        p for p in (media_dir / "hud-renders").glob("*-run-*-hud-preview.mp4")
        if not any(part in p.stem for part in RAW_PARTS)
    )
    if not runs:
        raise SystemExit(f"No HUD previews in {media_dir / 'hud-renders'}")
    return [p for p in (open_clip, *runs, close_clip) if p is not None]


def build_command(inputs: list[Path], output: Path) -> list[str]:
    cmd = ["ffmpeg", "-y", "-hide_banner"]
    for path in inputs:
        cmd.extend(["-i", str(path)])
    normalized: list[str] = []
    for i in range(len(inputs)):
        normalized.append(
            f"[{i}:v]scale={TIMELINE.width}:{TIMELINE.height}:force_original_aspect_ratio=decrease,"
            f"pad={TIMELINE.width}:{TIMELINE.height}:(ow-iw)/2:(oh-ih)/2,fps={TIMELINE.fps},settb=1/{TIMELINE.fps},format=yuv420p[v{i}];"
            f"[{i}:a]aformat=sample_rates={TIMELINE.sample_rate}:channel_layouts=stereo,"
            f"aresample=async=1:first_pts=0[a{i}]"
        )
    labels = "".join(f"[v{i}][a{i}]" for i in range(len(inputs)))
    graph = (
        "".join(normalized)
        + f"{labels}concat=n={len(inputs)}:v=1:a=1[v0][a0];[v0]format={TIMELINE.pix_fmt}[v]"
    )
    cmd.extend([
        "-filter_complex", graph,
        "-map", "[v]", "-map", "[a0]",
        "-c:v", PREVIEW_SPEC.vcodec,
        "-preset", PREVIEW_SPEC.preset or "veryfast",
        "-crf", str(PREVIEW_SPEC.crf or 23),
        "-pix_fmt", TIMELINE.pix_fmt,
        "-c:a", PREVIEW_SPEC.acodec,
        "-b:a", PREVIEW_SPEC.abitrate,
        "-ar", str(TIMELINE.sample_rate),
        "-movflags", "+faststart", str(output),
    ])
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--out")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    media_dir = Path(args.media_dir).expanduser().resolve()
    inputs = discover(media_dir)
    date = inputs[0].name[:10]
    output = Path(args.out).expanduser().resolve() if args.out else media_dir / f"{date}-review-preview.mp4"
    if output.name.endswith("-run-final.mp4") or "upload" in output.parts:
        raise SystemExit("Review preview cannot be written as run-final or inside upload/")
    cmd = build_command(inputs, output)
    print("$", " ".join(cmd))
    if not args.dry_run:
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
