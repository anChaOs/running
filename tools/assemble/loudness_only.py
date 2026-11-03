#!/usr/bin/env python3
"""对已有成片只做响度链：-c:v copy，不重拼 open/HUD/close。

复用 assemble_episode 的 LOUDNESS_* / 两遍 loudnorm；默认覆盖输入旁写临时再替换，
或 --out 另存。有 *-pre-coldopen.mp4 时打印警告：本脚本安全，但勿再全量 assemble。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assemble_episode as asm  # noqa: E402


def find_run_final(media_dir: Path) -> Path:
    cands = sorted(
        p
        for p in media_dir.glob("*-run-final.mp4")
        if "no-burn" not in p.name and "pre-loudnorm" not in p.name and "pre-coldopen" not in p.name
    )
    if not cands:
        raise SystemExit(f"No *-run-final.mp4 in {media_dir}")
    if len(cands) > 1:
        raise SystemExit(f"Multiple run-final candidates: {', '.join(p.name for p in cands)}; pass --input")
    return cands[0]


def warn_cold_open(media_dir: Path) -> None:
    bumps = list(media_dir.glob("*-pre-coldopen.mp4"))
    if bumps:
        print(
            "⚠ 检测到冷开场备份 "
            + ", ".join(p.name for p in bumps)
            + "：本脚本只改音轨、保留画面。不要再跑 assemble_episode 全量重拼（会抹 bumper）。"
        )


def measure_af(path: Path, af: str) -> dict | None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-vn",
        "-af",
        af,
        "-f",
        "null",
        "-",
    ]
    print("$ (loudnorm pass 1, audio only)", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        return None
    return asm.parse_loudnorm_json(proc.stderr)


def encode(path: Path, out: Path, af: str, dry_run: bool) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-af",
        af,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out),
    ]
    print("$", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audio-only loudness on an existing run-final (no open/HUD/close re-assemble)."
    )
    parser.add_argument("--media-dir", help="Media dir; finds *-run-final.mp4")
    parser.add_argument("--input", help="Explicit mp4 path (overrides media-dir discovery)")
    parser.add_argument("--out", help="Output path (default: overwrite input via temp)")
    parser.add_argument(
        "--single-pass-loudnorm",
        action="store_true",
        help="Skip two-pass loudnorm (measure then linear=true)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.input:
        src = Path(args.input).expanduser().resolve()
    elif args.media_dir:
        media_dir = Path(args.media_dir).expanduser().resolve()
        warn_cold_open(media_dir)
        src = find_run_final(media_dir)
    else:
        raise SystemExit("Need --media-dir or --input")

    if not src.is_file():
        raise SystemExit(f"input not found: {src}")

    out = Path(args.out).expanduser().resolve() if args.out else src
    print(f"Input: {src}")
    print(f"Output: {out}{' (in-place via temp)' if out == src else ''}")
    print(f"Loudness: {asm.LOUDNESS_AF}")

    af = asm.LOUDNESS_AF
    if not args.single_pass_loudnorm:
        if args.dry_run:
            print("Loudnorm: two-pass（dry-run 不测量）")
        else:
            measured = measure_af(src, asm.LOUDNESS_MEASURE_AF)
            if measured is None:
                print("⚠ Loudnorm 测量失败，退回单遍响度链")
            else:
                af = asm.loudness_af_two_pass(measured)
                print(
                    f"Loudnorm pass 1: I={measured['input_i']} LUFS  "
                    f"TP={measured['input_tp']} dBTP  LRA={measured['input_lra']}  "
                    f"thresh={measured['input_thresh']}  offset={measured['target_offset']}"
                )
                print(f"Loudnorm pass 2: {af}")

    if args.dry_run:
        encode(src, out, af, dry_run=True)
        return 0

    if out == src:
        with tempfile.TemporaryDirectory(prefix="loudness-only-") as td:
            tmp = Path(td) / "out.mp4"
            encode(src, tmp, af, dry_run=False)
            tmp.replace(src)
            final = src
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        encode(src, out, af, dry_run=False)
        final = out

    print(f"Wrote {final}")
    print(subprocess.check_output(["ls", "-lh", str(final)], text=True).strip())
    got = asm.measure_output(final)
    if got is None:
        print("⚠ 成片响度实测失败，手动跑 loudnorm summary")
    else:
        tp = float(got["input_tp"])
        flag = "OK" if tp <= -1.0 else "⚠ 超过 -1.0 dBTP，查局部"
        print(f"成片实测: I={got['input_i']} LUFS  TP={got['input_tp']} dBTP  LRA={got['input_lra']}  {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
