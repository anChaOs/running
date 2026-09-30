#!/usr/bin/env python3
"""把手机未重命名导出收进素材目录，按拍摄时间改成 open / run-* / close。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
VID_RE = re.compile(r"VID_(\d{8})_(\d{6})", re.IGNORECASE)
FIT_TS_RE = re.compile(r"(20\d{12})")
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
SKIP_NAME_PARTS = ("-hud-", "hud-preview", "run-final", "cover-", "-raw", "trimtmp")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
STATS_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-stats-\d+$")
STATS_HINTS = ("screenshot", "coros", "截图")


def run_ffprobe_duration(path: Path) -> float | None:
    try:
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
    except (subprocess.CalledProcessError, ValueError):
        return None


def parse_vid_start(name: str) -> datetime | None:
    match = VID_RE.search(name)
    if not match:
        return None
    return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)


def parse_fit_start(name: str) -> datetime | None:
    match = FIT_TS_RE.search(name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)


def file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=SHANGHAI)


def discover_videos(src: Path) -> list[Path]:
    videos: list[Path] = []
    for path in sorted(src.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
            continue
        name = path.name.lower()
        if any(part in name for part in SKIP_NAME_PARTS):
            continue
        if path.name.startswith("."):
            continue
        videos.append(path)
    return videos


def discover_fits(src: Path) -> list[Path]:
    return sorted(path for path in src.iterdir() if path.is_file() and path.suffix.lower() == ".fit")


def discover_raw_stats(src: Path) -> list[Path]:
    """高驰 App 截图：Screenshot_* / *coros* / 截图*。已命名的 stats-NN 不重复收。"""
    found: list[Path] = []
    for path in sorted(src.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXT:
            continue
        if STATS_STEM_RE.match(path.stem):
            continue
        name = path.name.lower()
        if name.startswith("cover-") or any(part in name for part in SKIP_NAME_PARTS):
            continue
        if any(hint in name for hint in STATS_HINTS):
            found.append(path)
    return found


def sort_key(path: Path) -> datetime:
    parsed = parse_vid_start(path.name)
    return parsed if parsed is not None else file_mtime(path)


def already_named(path: Path) -> str | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}-(open|close|run-[a-z]|broll-\d+)$", path.stem)
    return match.group(1) if match else None


def propose_roles(videos: list[Path], no_open: bool, no_close: bool) -> list[tuple[Path, str]]:
    ordered = sorted(videos, key=sort_key)
    named: list[tuple[Path, str]] = []
    leftover: list[Path] = []
    for path in ordered:
        role = already_named(path)
        if role:
            named.append((path, role))
        else:
            leftover.append(path)

    if not leftover:
        return named

    roles: list[str] = []
    n = len(leftover)
    if n == 1:
        roles = ["run-a"]
    elif n == 2:
        if no_open and no_close:
            roles = ["run-a", "run-b"]
        elif no_open:
            roles = ["run-a", "close"]
        elif no_close:
            roles = ["open", "run-a"]
        else:
            # 两段时默认跑前 + 跑中；不要猜成没有 run 的 open+close
            print("Two clips: proposing open + run-a. Override with --no-open / --no-close if needed.")
            roles = ["open", "run-a"]
    else:
        start = 0
        end = n
        if not no_open:
            roles.append("open")
            start = 1
        if not no_close:
            end = n - 1
        run_idx = 0
        for _ in range(start, end):
            roles.append(f"run-{chr(ord('a') + run_idx)}")
            run_idx += 1
        if not no_close:
            roles.append("close")

    if len(roles) != len(leftover):
        raise SystemExit(f"Role count {len(roles)} != video count {len(leftover)}")
    return named + list(zip(leftover, roles, strict=True))


def dest_name(date: str, role: str, suffix: str) -> str:
    return f"{date}-{role}{suffix}"


def copy_or_move(src: Path, dest: Path, move: bool, dry_run: bool) -> None:
    if src.resolve() == dest.resolve():
        return
    # 已经在目标目录里的文件只改名，不复制出第二份
    same_dir = src.parent.resolve() == dest.parent.resolve()
    action = "mv" if move or same_dir else "cp"
    print(f"{action} {src} -> {dest}")
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if action == "mv":
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)


def maybe_fix_mtime(path: Path, start: datetime | None, duration: float | None, dry_run: bool) -> str:
    if start is None or duration is None:
        return "mtime unchanged (no VID_ start or duration)"
    end = start + timedelta(seconds=duration)
    current = file_mtime(path)
    delta = abs((current - end).total_seconds())
    if delta <= 300:
        return f"mtime ok ({current.isoformat(timespec='seconds')})"
    msg = f"mtime {current.isoformat(timespec='seconds')} -> {end.isoformat(timespec='seconds')} (VID_ start + duration)"
    print(msg)
    if not dry_run:
        ts = end.timestamp()
        os.utime(path, (ts, ts))
    return msg


def write_assets_md(
    dest: Path,
    media_dir: Path,
    date: str,
    slug: str,
    rows: list[dict],
    fits: list[tuple[str, str]],
) -> None:
    lines = [
        f"# {date} {slug} 素材索引",
        "",
        "## 本地素材目录",
        "",
        f"`{media_dir}`",
        "",
        "## 重命名结果",
        "",
        "### 视频素材",
        "",
    ]
    for row in rows:
        lines.append(f"- `{row['src']}` -> `{row['dest']}`")
    lines.extend(["", "### 跑步数据", ""])
    if fits:
        for src, dest_name_ in fits:
            lines.append(f"- `{src}` -> `{dest_name_}`")
    else:
        lines.append("- （未发现 FIT）")
    lines.extend(["", "## 时间顺序依据", ""])
    for row in rows:
        lines.append(f"- {row['start']}: `{row['role']}`")
    lines.extend(["", "## 素材关联", ""])
    for row in rows:
        lines.append(f"- `{row['role']}`：`{row['dest']}`")
    for _, dest_name_ in fits:
        lines.append(f"- FIT：`{dest_name_}`")
    lines.extend(
        [
            "",
            "## 制作状态",
            "",
            "- ingest: done",
            "- hud: pending",
            "- subs: pending",
            "- cover: pending",
            "- assemble: pending",
            "- qc: pending",
            "",
        ]
    )
    dest.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest phone exports into a named running-content folder.")
    parser.add_argument("--src", required=True, help="Folder of unrenamed phone exports")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--media-root",
        default=str(Path.home() / "Movies" / "running-content"),
        help="Parent of YYYY-MM-DD-slug",
    )
    parser.add_argument("--episode-dir", help="Write assets.md here (repo episodes/...)")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-close", action="store_true")
    parser.add_argument("--move", action="store_true", help="Move instead of copy")
    parser.add_argument("--apply", action="store_true", help="Actually copy/rename. Default is dry-run")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--skip-pause-trim",
        action="store_true",
        help="Do not trim long pauses in open/close",
    )
    args = parser.parse_args()

    src = Path(args.src).expanduser().resolve()
    if not src.is_dir():
        raise SystemExit(f"Source is not a directory: {src}")
    date = args.date
    slug = args.slug
    media_dir = Path(args.media_root).expanduser().resolve() / f"{date}-{slug}"
    dry_run = not args.apply

    videos = discover_videos(src)
    fits = discover_fits(src)
    if not videos:
        raise SystemExit(f"No videos in {src}")

    mapping = propose_roles(videos, no_open=args.no_open, no_close=args.no_close)
    print(f"Media dir: {media_dir}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    rows: list[dict] = []
    for path, role in mapping:
        start = parse_vid_start(path.name) or file_mtime(path)
        duration = run_ffprobe_duration(path)
        dest = media_dir / dest_name(date, role, path.suffix.lower())
        exists = dest.exists() and dest.resolve() != path.resolve()
        print(f"  {path.name}  {start.strftime('%H:%M:%S')}  {duration or '?'}s  -> {dest.name}  [{role}]")
        if exists and not args.force:
            raise SystemExit(f"Refusing to overwrite {dest} (pass --force)")
        copy_or_move(path, dest, move=args.move, dry_run=dry_run)
        target = dest if (args.apply or dest.exists()) else path
        mtime_note = maybe_fix_mtime(
            target if args.apply else path,
            parse_vid_start(path.name),
            duration,
            dry_run,
        )
        rows.append(
            {
                "src": path.name,
                "dest": dest.name,
                "role": role,
                "start": start.strftime("%H:%M:%S"),
                "mtime": mtime_note,
            }
        )

    fit_pairs: list[tuple[str, str]] = []
    if fits:
        primary = fits[0]
        if len(fits) > 1:
            print("Multiple FIT files; using the first after sort. Confirm before --apply.")
        for item in fits:
            ts = parse_fit_start(item.name)
            stamp = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown-time"
            print(f"  FIT {item.name} ({stamp})")
        dest_fit = media_dir / f"{date}-run-data.fit"
        copy_or_move(primary, dest_fit, move=args.move, dry_run=dry_run)
        fit_pairs.append((primary.name, dest_fit.name))

    for i, path in enumerate(discover_raw_stats(src), start=1):
        dest_stat = media_dir / f"{date}-stats-{i:02d}{path.suffix.lower()}"
        print(f"  STAT {path.name} -> {dest_stat.name}")
        copy_or_move(path, dest_stat, move=args.move, dry_run=dry_run)

    payload = {
        "media_dir": str(media_dir),
        "date": date,
        "slug": slug,
        "rows": rows,
        "fits": [{"src": a, "dest": b} for a, b in fit_pairs],
        "dry_run": dry_run,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.episode_dir:
        assets = Path(args.episode_dir).expanduser().resolve() / "assets.md"
        print(f"assets.md -> {assets}")
        if not dry_run:
            assets.parent.mkdir(parents=True, exist_ok=True)
            write_assets_md(assets, media_dir, date, slug, rows, fit_pairs)

    if not dry_run:
        if args.skip_pause_trim:
            print("skip open/close pause trim")
        else:
            trim_script = Path(__file__).resolve().parent / "trim_talk_pauses.py"
            print("open/close pause trim")
            subprocess.run(
                [
                    sys.executable,
                    str(trim_script),
                    "--media-dir",
                    str(media_dir),
                    "--apply",
                ],
                check=False,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
