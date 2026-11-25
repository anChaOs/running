#!/usr/bin/env python3
"""成片定稿后把上传文件收到媒体目录 upload/。

标题烧字 .mp4：move 进 upload/（禁止 copy；根目录不留第二份）。
封面与 subtitles.srt：硬链进 upload/（失败才 copy 小文件）。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import log_timeline  # noqa: E402
import media_layout  # noqa: E402
import todo_list  # noqa: E402

BILIBILI_DESC_MAX = 2000
# 这些是制作中间片，不能被当成标题成片搬走。
EXCLUDED_PARTS = (
    "-run-",
    "-raw",
    "no-burn",
    "no-subs",
    "pre-coldopen",
    "pre-loudnorm",
    "review-preview",
    "close-stats",
    "hud-preview",
    "truncated",
)

COVERS = (
    "cover-4x3-1920x1440.jpg",
    "cover-3x4-1080x1440.jpg",
    "cover-16x9-1920x1080.jpg",
)
SRT_NAME = "subtitles.srt"
UPLOAD_DIRNAME = "upload"


def filename_from_title(title: str) -> str:
    """macOS 文件名不能含 ASCII /。平台标题仍用原文，文件名里的斜杠换成全角。"""
    name = title.strip().replace("/", "／").replace("\x00", "")
    if not name:
        raise ValueError("empty title")
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    return name


def check_bilibili_desc(text: str, limit: int = BILIBILI_DESC_MAX) -> int:
    count = len(text)
    if count > limit:
        raise SystemExit(f"Bilibili description is {count} characters; limit is {limit}")
    return count


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_excluded_mp4(name: str) -> bool:
    """排除制作片，只留标题改名后的烧字成片。"""
    lower = name.lower()
    if any(part in lower for part in EXCLUDED_PARTS):
        return True
    stem = Path(name).stem.lower()
    if re.match(r"^vid_\d{8}_\d{6}", stem):
        return True
    if stem.endswith("-open") or stem.endswith("-close") or stem in {"open", "close"}:
        return True
    if stem.startswith("open-") or stem.startswith("close-") or "-open-" in stem or "-close-" in stem:
        return True
    return False


def title_from_plan(episode_dir: Path) -> str:
    """从 episodes/<slug>/plan.md 读取视频标题（对齐 youtube_cloud 口径：跳过「发这个」提示，支持 > 引用与 - 标题：回退）。"""
    plan = Path(episode_dir).expanduser().resolve() / "plan.md"
    if not plan.is_file():
        raise SystemExit(f"plan.md not found: {plan}")
    lines = plan.read_text(encoding="utf-8").splitlines()
    in_title = False
    for raw in lines:
        stripped = raw.strip()
        if re.match(r"^##\s+标题\s*$", stripped):
            in_title = True
            continue
        if in_title:
            if re.match(r"^#{2,3}\s+", stripped):
                break
            if not stripped:
                continue
            s = re.sub(r"^>\s*", "", stripped)
            s = re.sub(r"^-\s+", "", s).strip("`").strip()
            if not s:
                continue
            if "发这个" in s:
                m = re.search(r"发这个[^：:]*[：:]\s*(.+)$", s)
                if m and m.group(1).strip():
                    return m.group(1).strip().strip("`").strip()
                continue
            return s
    for raw in lines:
        m = re.match(r"^-\s*标题[：:]\s*(.+)$", raw.strip())
        if m and m.group(1).strip():
            return m.group(1).strip().strip("`").strip()
    raise SystemExit(f"Could not parse title from {plan}")


def _find_run_final(media_dir: Path) -> Path | None:
    cands = sorted(
        p
        for p in media_dir.iterdir()
        if p.is_file() and re.fullmatch(r"\d{4}-\d{2}-\d{2}-run-final\.mp4", p.name)
    )
    if len(cands) > 1:
        raise SystemExit(
            "Multiple *-run-final.mp4 files: " + ", ".join(p.name for p in cands) + "; pass --title-mp4"
        )
    return cands[0].resolve() if cands else None


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
    if name.startswith("cover-"):
        return media_layout.find_cover(media_dir, name)
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
    backup: Path | None = None
    if dst.exists() or dst.is_symlink():
        backup = dst.with_name(dst.name + ".replacing")
        if backup.exists():
            raise SystemExit(f"refusing to replace {dst}; leftover {backup.name}")
        os.rename(dst, backup)
    try:
        os.rename(src, dst)
    except OSError as exc:
        if backup is not None:
            os.rename(backup, dst)
        raise SystemExit(
            f"Cannot move title mp4 into upload/ (copy forbidden): {src} → {dst}: {exc}"
        ) from exc
    if backup is not None:
        backup.unlink()
    return "move"


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


def pack(media_dir: Path, title_mp4: Path | None = None, episode_dir: Path | None = None) -> Path:
    media_dir = media_dir.expanduser().resolve()
    if not media_dir.is_dir():
        raise SystemExit(f"media-dir not a directory: {media_dir}")
    try:
        todo_list.assert_pack_allowed(media_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    if episode_dir is not None:
        target_name = filename_from_title(title_from_plan(episode_dir))
        if title_mp4 is not None:
            title = find_title_mp4(media_dir, title_mp4)
        else:
            titled_root = media_dir / target_name
            titled_up = media_dir / UPLOAD_DIRNAME / target_name
            run_final = _find_run_final(media_dir)
            if titled_root.is_file() and run_final is not None:
                raise SystemExit(
                    f"Both {titled_root.name} and {run_final.name} exist in {media_dir}; "
                    "remove the stale one or pass --title-mp4"
                )
            if titled_root.is_file():
                title = titled_root.resolve()
            elif run_final is not None:
                title = run_final
            elif titled_up.is_file():
                title = titled_up.resolve()
            else:
                title = find_title_mp4(media_dir, title_mp4)
    else:
        title = find_title_mp4(media_dir, title_mp4)
        target_name = title.name

    missing: list[str] = []
    cover_paths: list[Path] = []
    for name in COVERS:
        p = resolve_small(media_dir, name)
        if p is None:
            missing.append(name)
        else:
            cover_paths.append(p)
    srt_from_repo = False
    ep_srt = (Path(episode_dir).expanduser().resolve() / SRT_NAME) if episode_dir is not None else None
    if ep_srt is not None and ep_srt.is_file():
        srt = ep_srt
        srt_from_repo = True
    else:
        srt = resolve_small(media_dir, SRT_NAME)
    if srt is None:
        missing.append(SRT_NAME)
    if missing or srt is None:
        raise SystemExit(f"Missing required file(s) in {media_dir}: {', '.join(missing)}")

    upload = media_dir / UPLOAD_DIRNAME
    upload.mkdir(parents=True, exist_ok=True)

    print(f"pack → {upload}")
    how = place_title_mp4(title, upload / target_name)
    print(f"  {target_name}  [{how}]")
    for c in cover_paths:
        how = hardlink_or_copy_small(c, upload / c.name)
        print(f"  {c.name}  ← {c}  [{how}]")
    if srt_from_repo:
        # 仓库内字幕不与 upload/ 共享硬链 inode，避免改字/切分支后陈旧或串改。
        dst_srt = upload / SRT_NAME
        if dst_srt.exists() or dst_srt.is_symlink():
            dst_srt.unlink()
        shutil.copy2(srt, dst_srt)
        how = "copy"
    else:
        how = hardlink_or_copy_small(srt, upload / SRT_NAME)
    print(f"  {SRT_NAME}  ← {srt}  [{how}]")
    packed = upload / target_name
    digest = sha256_file(packed)
    record = media_dir / "logs" / "pack-sha256.txt"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(f"{digest}  {packed.name}\n", encoding="utf-8")
    print(f"  sha256 {digest}  {packed.name}")
    todo_list.mark(media_dir, "pack-upload", "done")
    return upload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--media-dir",
        type=Path,
        help="~/Movies/running-content/YYYY-MM-DD-slug",
    )
    ap.add_argument(
        "--episode-dir",
        type=Path,
        default=None,
        help="episodes/YYYY-MM-DD-slug；读取 plan.md 标题并自动把 *-run-final.mp4 改名移入 upload/",
    )
    ap.add_argument("--check-desc", type=Path, help="Refuse if this Bilibili description exceeds 2000 characters")
    ap.add_argument(
        "--print-filename",
        help="Print a macOS-safe mp4 name for a platform title (ASCII / becomes fullwidth) and exit",
    )
    ap.add_argument(
        "--title-mp4",
        type=Path,
        default=None,
        help="标题名烧字成片；默认同目录或 upload/ 自动识别",
    )
    args = ap.parse_args(argv)
    if args.print_filename:
        print(filename_from_title(args.print_filename))
        return 0
    if args.check_desc is not None:
        count = check_bilibili_desc(args.check_desc.read_text(encoding="utf-8"))
        print(f"bilibili description {count} characters")
        if args.media_dir is None:
            return 0
    if args.media_dir is None:
        ap.error("--media-dir is required")
    with log_timeline.span(args.media_dir, "pack-upload"):
        pack(args.media_dir, args.title_mp4, episode_dir=args.episode_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
