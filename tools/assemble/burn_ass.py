#!/usr/bin/env python3
"""对已有成片只烧 ASS：单文件进单文件出，不重拼 open/HUD/close。

默认 -c:a copy（假定响度已定稿）。视频重编码（hevc_videotoolbox / ASSEMBLE_VCODEC）。
有 *-pre-coldopen.mp4 时打印警告：本脚本保留画面轴，勿再全量 assemble。
"""

from __future__ import annotations

import argparse
import shutil
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
            + "：本脚本只烧字、保留画面。不要再跑 assemble_episode 全量重拼（会抹 bumper）。"
        )


def escape_subtitles_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def prepare_fontsdir() -> Path | None:
    fontsdir = Path("/tmp/running-ass-fonts")
    fontsdir.mkdir(parents=True, exist_ok=True)
    if asm.FONT_SRC.exists():
        shutil.copyfile(asm.FONT_SRC, fontsdir / asm.FONT_SRC.name)
        return fontsdir
    return fontsdir if fontsdir.exists() else None


def encode(src: Path, ass: Path, out: Path, bitrate: int, dry_run: bool) -> None:
    fontsdir = prepare_fontsdir()
    ass_esc = escape_subtitles_path(ass)
    vf = f"subtitles={ass_esc}:charenc=UTF-8"
    if fontsdir is not None:
        fonts_esc = str(fontsdir).replace(":", "\\:")
        vf = f"subtitles={ass_esc}:fontsdir={fonts_esc}:charenc=UTF-8"
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(src),
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        *asm.video_codec_args(bitrate),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
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
        description="Burn ASS onto an existing run-final (no open/HUD/close re-assemble)."
    )
    parser.add_argument("--media-dir", help="Media dir; finds *-run-final.mp4")
    parser.add_argument("--input", help="Explicit mp4 (overrides discovery)")
    parser.add_argument("--ass", required=True, help="ASS subtitle file to burn")
    parser.add_argument("--out", help="Output path (default: overwrite input via temp)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ass = Path(args.ass).expanduser().resolve()
    if not ass.is_file():
        raise SystemExit(f"ASS not found: {ass}")

    if args.input:
        src = Path(args.input).expanduser().resolve()
        media_dir = src.parent
    elif args.media_dir:
        media_dir = Path(args.media_dir).expanduser().resolve()
        src = find_run_final(media_dir)
    else:
        raise SystemExit("Need --media-dir or --input")

    if not src.is_file():
        raise SystemExit(f"input not found: {src}")

    warn_cold_open(media_dir)
    out = Path(args.out).expanduser().resolve() if args.out else src
    bitrate = asm.probe_video_bitrate(src)
    print(f"Input: {src}")
    print(f"ASS: {ass}")
    print(f"Output: {out}{' (in-place via temp)' if out == src else ''}")
    print(f"Video bitrate probe: {bitrate}")

    if args.dry_run:
        encode(src, ass, out, bitrate, dry_run=True)
        return 0

    if out == src:
        with tempfile.TemporaryDirectory(prefix="burn-ass-") as td:
            tmp = Path(td) / "out.mp4"
            encode(src, ass, tmp, bitrate, dry_run=False)
            tmp.replace(src)
            final = src
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        encode(src, ass, out, bitrate, dry_run=False)
        final = out

    print(f"Wrote {final}")
    print(subprocess.check_output(["ls", "-lh", str(final)], text=True).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
