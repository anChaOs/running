#!/usr/bin/env python3
"""成片定稿后把上传文件收到媒体目录 upload/。

标题烧字 .mp4：move 进 upload/（禁止 copy；根目录不留第二份）。
封面与 subtitles.srt：硬链进 upload/（失败才 copy 小文件）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import log_timeline  # noqa: E402

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
    stem = Path(name).stem.lower()
    if stem.endswith("-open") or stem.endswith("-close") or stem in {"open", "close"}:
        return True
    if stem.startswith("open-") or stem.startswith("close-"):
        return True
    return False


def _title_candidates(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() == ".mp4" and not is_excluded_mp4(p.name)
    )


def find_title_mp4(media_dir: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        p = explicit if explicit.is_absolute() else media_dir / explicit
        if not p.is_file():
            # 已 pack 过时标题只在 upload/
            alt = media_dir / UPLOAD_DIRNAME / Path(explicit).name
            if alt.is_file():
                return alt.resolve()
            raise SystemExit(f"title mp4 not found: {p}")
        return p.resolve()

    root_cands = _title_candidates(media_dir)
    upload_cands = _title_candidates(media_dir / UPLOAD_DIRNAME)
    if root_cands:
        if len(root_cands) > 1:
            raise SystemExit(
                "Multiple title mp4 candidates: "
                + ", ".join(p.name for p in root_cands)
                + "; pass --title-mp4"
            )
        return root_cands[0]
    if upload_cands:
        if len(upload_cands) > 1:
            raise SystemExit(
                "Multiple title mp4 candidates in upload/: "
                + ", ".join(p.name for p in upload_cands)
                + "; pass --title-mp4"
            )
        return upload_cands[0]
    raise SystemExit(
        f"No titled final .mp4 in {media_dir} or {media_dir / UPLOAD_DIRNAME} "
        "(expected renamed title.mp4; not *-run-*.mp4 / *raw* / *no-burn*). "
        "Pass --title-mp4."
    )


def resolve_small(media_dir: Path, name: str) -> Path | None:
    root = media_dir / name
    if root.is_file():
        return root
    up = media_dir / UPLOAD_DIRNAME / name
    if up.is_file():
        return up
    return None


def same_file(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def place_title_mp4(src: Path, dst: Path) -> str:
    """Move titled final into upload/. Never copy. One physical file only."""
    src = src.resolve()
    dst = dst if dst.is_absolute() else dst.resolve()
    if same_file(src, dst):
        if src != dst.resolve():
            src.unlink()
            return "kept upload/ (dropped root link)"
        return "already in upload/"
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.rename(src, dst)
        return "move"
    except OSError as exc:
        raise SystemExit(
            f"Cannot move title mp4 into upload/ (copy forbidden): {src} → {dst}: {exc}"
        ) from exc


def hardlink_or_copy_small(src: Path, dst: Path) -> str:
    src = src.resolve()
    if same_file(src, dst) or src == dst.resolve():
        return "already in place"
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
        p = resolve_small(media_dir, name)
        if p is None:
            missing.append(name)
        else:
            cover_paths.append(p)
    srt = resolve_small(media_dir, SRT_NAME)
    if srt is None:
        missing.append(SRT_NAME)
    if missing:
        raise SystemExit(f"Missing required file(s) in {media_dir}: {', '.join(missing)}")

    upload = media_dir / UPLOAD_DIRNAME
    upload.mkdir(parents=True, exist_ok=True)

    print(f"pack → {upload}")
    how = place_title_mp4(title, upload / title.name)
    print(f"  {title.name}  [{how}]")
    for c in cover_paths:
        how = hardlink_or_copy_small(c, upload / c.name)
        print(f"  {c.name}  ← {c}  [{how}]")
    how = hardlink_or_copy_small(srt, upload / SRT_NAME)
    print(f"  {SRT_NAME}  ← {srt}  [{how}]")

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
        help="标题名烧字成片；默认同目录或 upload/ 自动识别",
    )
    args = ap.parse_args(argv)
    with log_timeline.span(args.media_dir, "pack-upload"):
        pack(args.media_dir, args.title_mp4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
