#!/usr/bin/env python3
"""Classified media-directory layout helpers with backward compatibility for legacy flat folders.

Classified episode layout under ``~/Movies/running-content/YYYY-MM-DD-slug/``:
  raw/      open, run-*, close, close-*, broll-*, *-raw.mp4
  data/     *-run-data.fit, *-stats-* images, weather-hourly.json
  stills/   raw selfie / reference photos (non-cover)
  covers/   cover-4x3-*.jpg, cover-3x4-*.jpg, cover-16x9-*.jpg
  preview/  *-review-preview.edl (and temporary review-preview.srt)
  upload/   final titled .mp4, hardlinked covers, subtitles.srt
  logs/     program.json, todo.md, timeline.txt, failures.md, pack-sha256.txt, ...

If an episode folder has none of the classified subdirectories (legacy flat episodes or
unit-test fixtures), discovery seamlessly falls back to the root of ``media_dir``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

RAW_DIR = "raw"
DATA_DIR = "data"
STILLS_DIR = "stills"
COVERS_DIR = "covers"
PREVIEW_DIR = "preview"
UPLOAD_DIR = "upload"
LOGS_DIR = "logs"

CLASSIFIED_MARKERS = (RAW_DIR, DATA_DIR, STILLS_DIR, COVERS_DIR, PREVIEW_DIR)
SCAFFOLD_DIRS = (
    RAW_DIR,
    DATA_DIR,
    STILLS_DIR,
    COVERS_DIR,
    PREVIEW_DIR,
    UPLOAD_DIR,
    LOGS_DIR,
)
SEARCH_SUBDIRS = (RAW_DIR, DATA_DIR, STILLS_DIR, COVERS_DIR, PREVIEW_DIR, UPLOAD_DIR)


def is_classified(media_dir: Path | str) -> bool:
    """Return True if ``media_dir`` uses the classified subdirectory layout."""
    root = Path(media_dir).expanduser()
    if not root.is_dir():
        return False
    return any((root / sub).is_dir() for sub in CLASSIFIED_MARKERS)


def should_use_classified_on_ingest(media_dir: Path | str, *, force_flat: bool = False) -> bool:
    """Decide layout for ``ingest_run_media.py``: classified by default unless legacy flat media already sits at root."""
    if force_flat:
        return False
    root = Path(media_dir).expanduser()
    if is_classified(root):
        return True
    if root.is_dir():
        has_root_media = any(
            p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".m4v", ".fit"}
            for p in root.iterdir()
        )
        if has_root_media:
            return False
    return True


def ensure_classified_dirs(media_dir: Path | str) -> Path:
    """Create empty classified subdirectories under ``media_dir`` and return resolved root."""
    root = Path(media_dir).expanduser().resolve()
    for sub in SCAFFOLD_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def rel_media_path(path: Path | str, media_dir: Path | str) -> str:
    """Return POSIX path relative to ``media_dir`` when inside it, otherwise basename/str."""
    root = Path(media_dir).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def resolve_media_path(
    media_dir: Path | str,
    rel_or_name: str | Path,
    *,
    subdirs: tuple[str, ...] = SEARCH_SUBDIRS,
) -> Path:
    """Resolve a clip/asset path relative to ``media_dir``, checking root then known classified subdirs."""
    root = Path(media_dir).expanduser()
    candidate = Path(rel_or_name)
    if candidate.is_absolute():
        return candidate
    direct = root / candidate
    if direct.exists() or len(candidate.parts) > 1:
        return direct
    for sub in subdirs:
        sub_path = root / sub / candidate.name
        if sub_path.exists():
            return sub_path
    return direct


def search_dirs(media_dir: Path | str, *subdirs: str) -> list[Path]:
    """Return existing search directories: classified subdirs first, then ``media_dir`` root."""
    root = Path(media_dir).expanduser()
    dirs: list[Path] = []
    for sub in subdirs:
        cand = root / sub
        if cand.is_dir():
            dirs.append(cand)
    if root.is_dir():
        dirs.append(root)
    return dirs


def glob_media(
    media_dir: Path | str,
    pattern: str,
    *,
    subdirs: tuple[str, ...],
) -> list[Path]:
    """Glob ``pattern`` across classified subdirs (preferred) and ``media_dir`` root, deduplicated by filename."""
    seen_names: set[str] = set()
    found: list[Path] = []
    for directory in search_dirs(media_dir, *subdirs):
        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            if path.name in seen_names:
                continue
            seen_names.add(path.name)
            found.append(path)
    return sorted(found, key=lambda p: (p.name, str(p)))


def iter_files(
    media_dir: Path | str,
    *,
    subdirs: tuple[str, ...],
) -> list[Path]:
    """List files in classified subdirs and ``media_dir`` root, deduplicated by filename (subdirs first)."""
    seen_names: set[str] = set()
    found: list[Path] = []
    for directory in search_dirs(media_dir, *subdirs):
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            if path.name in seen_names:
                continue
            seen_names.add(path.name)
            found.append(path)
    return found


def find_fits(media_dir: Path | str) -> list[Path]:
    return glob_media(media_dir, "*-run-data.fit", subdirs=(DATA_DIR,))


def find_all_fits(media_dir: Path | str) -> list[Path]:
    return glob_media(media_dir, "*.fit", subdirs=(DATA_DIR,))


def weather_json_read_path(media_dir: Path | str) -> Path:
    root = Path(media_dir).expanduser()
    in_data = root / DATA_DIR / "weather-hourly.json"
    if in_data.is_file():
        return in_data
    in_root = root / "weather-hourly.json"
    if in_root.is_file():
        return in_root
    return weather_json_write_path(root)


def weather_json_write_path(media_dir: Path | str) -> Path:
    root = Path(media_dir).expanduser()
    if (root / DATA_DIR).is_dir() or is_classified(root):
        return root / DATA_DIR / "weather-hourly.json"
    return root / "weather-hourly.json"


def cover_dest_dir(media_dir: Path | str, prefix: str = "") -> Path:
    """Return output directory for compose_cover.py (uses ``covers/`` when classified and prefix has no dir)."""
    root = Path(media_dir).expanduser()
    if "/" in prefix or prefix.startswith("cover-candidates"):
        return root
    if (root / COVERS_DIR).is_dir() or is_classified(root):
        return root / COVERS_DIR
    return root


def find_cover(media_dir: Path | str, name: str) -> Path | None:
    root = Path(media_dir).expanduser()
    for cand in (root / COVERS_DIR / name, root / name, root / UPLOAD_DIR / name):
        if cand.is_file():
            return cand
    return None


def preview_edl_path(media_dir: Path | str, date_prefix: str) -> Path:
    root = Path(media_dir).expanduser()
    filename = f"{date_prefix[:10]}-review-preview.edl"
    if (root / PREVIEW_DIR).is_dir() or is_classified(root):
        return root / PREVIEW_DIR / filename
    return root / filename


def existing_preview_files(media_dir: Path | str, date_prefix: str) -> list[Path]:
    date = date_prefix[:10]
    root = Path(media_dir).expanduser()
    hits: list[Path] = []
    for directory in search_dirs(root, PREVIEW_DIR):
        for name in (f"{date}-review-preview.edl", f"{date}-review-preview.mp4"):
            cand = directory / name
            if cand.is_file():
                hits.append(cand)
    return hits


def subtitles_srt_dest(media_dir: Path | str) -> Path:
    root = Path(media_dir).expanduser()
    if (root / UPLOAD_DIR).is_dir() and is_classified(root):
        return root / UPLOAD_DIR / "subtitles.srt"
    return root / "subtitles.srt"


def raw_dest_path(media_dir: Path | str, filename: str, *, classified: bool) -> Path:
    root = Path(media_dir).expanduser()
    return (root / RAW_DIR / filename) if classified else (root / filename)


def data_dest_path(media_dir: Path | str, filename: str, *, classified: bool) -> Path:
    root = Path(media_dir).expanduser()
    return (root / DATA_DIR / filename) if classified else (root / filename)


def stills_dest_path(media_dir: Path | str, filename: str, *, classified: bool) -> Path:
    root = Path(media_dir).expanduser()
    return (root / STILLS_DIR / filename) if classified else (root / filename)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize or inspect classified episode media directories.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init_p = sub.add_parser("init", help="Create classified subdirectories under --media-dir")
    init_p.add_argument("--media-dir", required=True)
    show_p = sub.add_parser("show", help="Print whether --media-dir is classified and resolved paths")
    show_p.add_argument("--media-dir", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "init":
        root = ensure_classified_dirs(args.media_dir)
        print(f"Initialized classified media layout in {root}")
        return 0
    root = Path(args.media_dir).expanduser().resolve()
    print(f"media_dir={root} classified={is_classified(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
