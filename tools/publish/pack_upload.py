#!/usr/bin/env python3
"""把一期上传要用的文件硬链/拷进媒体目录 upload/，方便 Finder 一次打开。

不删、不挪媒体根目录原文件（KEEP / 清临时路径仍有效）。同卷优先 os.link，失败再 copy2。
内容固定五件：标题名烧字 mp4、三张封面（4:3→3:4→16:9）、subtitles.srt。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

COVERS = (
    "cover-4x3-1920x1440.jpg",
    "cover-3x4-1080x1440.jpg",
    "cover-16x9-1920x1080.jpg",
)
SRT_NAME = "subtitles.srt"
UPLOAD_DIRNAME = "upload"


def is_excluded_mp4(name: str) -> bool:
    """排除制作片，只留标题改名后的烧字成片。"""
    lower = name.lower()
    if "-run-" in lower:
        return True
    if "-raw" in lower:
        return True
    if "no-burn" in lower:
        return True
    if "pre-coldopen" in lower or "pre-loudnorm" in lower:
        return True
    # 剪过的 open / close（无 -raw 时仍可能留在根目录）
    stem = Path(name).stem.lower()
    if stem.endswith("-open") or stem.endswith("-close") or stem in {"open", "close"}:
        return True
    if stem.startswith("open-") or stem.startswith("close-"):
        return True
    return False


def find_title_mp4(media_dir: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        p = explicit if explicit.is_absolute() else media_dir / explicit
        if not p.is_file():
            raise SystemExit(f"title mp4 not found: {p}")
        return p.resolve()

    cands = sorted(
        p
        for p in media_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".mp4" and not is_excluded_mp4(p.name)
    )
    if not cands:
        raise SystemExit(
            f"No titled final .mp4 in {media_dir} "
            "(expected renamed title.mp4; not *-run-*.mp4 / *raw* / *no-burn*). "
            "Pass --title-mp4."
        )
    if len(cands) > 1:
        raise SystemExit(
            "Multiple title mp4 candidates: "
            + ", ".join(p.name for p in cands)
            + "; pass --title-mp4"
        )
    return cands[0]


def hardlink_or_copy(src: Path, dst: Path) -> str:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError as exc:
        shutil.copy2(src, dst)
        return f"copy (hardlink failed: {exc})"


def pack(media_dir: Path, title_mp4: Path | None = None) -> Path:
    media_dir = media_dir.expanduser().resolve()
    if not media_dir.is_dir():
        raise SystemExit(f"media-dir not a directory: {media_dir}")

    title = find_title_mp4(media_dir, title_mp4)
    missing: list[str] = []
    cover_paths: list[Path] = []
    for name in COVERS:
        p = media_dir / name
        if not p.is_file():
            missing.append(name)
        else:
            cover_paths.append(p)
    srt = media_dir / SRT_NAME
    if not srt.is_file():
        missing.append(SRT_NAME)
    if missing:
        raise SystemExit(f"Missing required file(s) in {media_dir}: {', '.join(missing)}")

    upload = media_dir / UPLOAD_DIRNAME
    upload.mkdir(parents=True, exist_ok=True)

    members: list[tuple[Path, Path]] = [
        (title, upload / title.name),
        *((c, upload / c.name) for c in cover_paths),
        (srt, upload / SRT_NAME),
    ]

    print(f"pack → {upload}")
    for src, dst in members:
        how = hardlink_or_copy(src, dst)
        print(f"  {dst.name}  ← {src}  [{how}]")

    return upload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--media-dir",
        required=True,
        type=Path,
        help="~/Movies/running-content/YYYY-MM-DD-slug",
    )
    ap.add_argument(
        "--title-mp4",
        type=Path,
        default=None,
        help="标题名烧字成片；默认同目录自动识别（排除 *-run-*.mp4 / *raw* / *no-burn*）",
    )
    args = ap.parse_args(argv)
    pack(args.media_dir, args.title_mp4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
