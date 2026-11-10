#!/usr/bin/env python3
"""把成片切成略小于 100MB 的块，再并行拷进 Google Drive 桌面版目录。

默认只新增，不覆盖、不删除、不进废纸篓。本机拷完只说明文件已交给桌面客户端，
云端就绪还要等 Drive API 能列出稳定 id 和完整体积后再算。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_CHUNK_BYTES = 99_000_000
DEFAULT_JOBS = 8
HASH_NAME = "original.sha256"
MANIFEST_NAME = "manifest.txt"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def chunk_width(count: int) -> int:
    if count <= 0:
        raise ValueError("chunk count must be positive")
    return max(2, len(str(count - 1)))


def plan_chunks(total: int, chunk_bytes: int) -> list[tuple[str, int, int]]:
    if total <= 0:
        raise ValueError("source size must be positive")
    if chunk_bytes <= 0:
        raise ValueError("chunk bytes must be positive")
    count = (total + chunk_bytes - 1) // chunk_bytes
    width = chunk_width(count)
    plan: list[tuple[str, int, int]] = []
    offset = 0
    for i in range(count):
        size = min(chunk_bytes, total - offset)
        plan.append((f"chunk-{i:0{width}d}", offset, size))
        offset += size
    return plan


def write_manifest(path: Path, plan: list[tuple[str, int, int]], total: int, digest: str, src: Path) -> None:
    lines = [f"{name} {size}" for name, _offset, size in plan]
    lines.append(f"TOTAL {total}")
    lines.append(f"SHA256 {digest}  {src}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sha256_file(path: Path, digest: str, src: Path) -> None:
    path.write_text(f"{digest}  {src}\n", encoding="utf-8")


def split_into_chunks(src: Path, work_dir: Path, plan: list[tuple[str, int, int]]) -> list[Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with src.open("rb") as inf:
        for name, offset, size in plan:
            dest = work_dir / name
            if dest.is_file() and dest.stat().st_size == size:
                inf.seek(offset + size)
                written.append(dest)
                continue
            inf.seek(offset)
            tmp = dest.with_name(dest.name + ".partial")
            remaining = size
            with tmp.open("wb") as out:
                while remaining:
                    block = inf.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    out.write(block)
                    remaining -= len(block)
            if tmp.stat().st_size != size:
                tmp.unlink(missing_ok=True)
                raise SystemExit(f"failed to write full chunk: {dest} expected {size}")
            tmp.replace(dest)
            written.append(dest)
    return written


def default_work_dir(src: Path) -> Path:
    if src.parent.name == "upload":
        return src.parent.parent / "yt-drive-chunks"
    return src.parent / "yt-drive-chunks"


def find_drive_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    cloud = Path.home() / "Library" / "CloudStorage"
    if cloud.is_dir():
        for mount in sorted(cloud.glob("GoogleDrive-*")):
            for folder in ("我的云端硬盘", "My Drive"):
                cand = mount / folder
                if cand.is_dir():
                    resolved = cand.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        roots.append(cand)
    alias = Path.home() / "Google Drive"
    if alias.exists():
        for folder in ("我的云端硬盘", "My Drive"):
            cand = alias / folder
            if cand.is_dir():
                resolved = cand.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    roots.append(cand)
    return roots


def resolve_dest(dest: Path | None, drive_folder: str | None) -> Path:
    if dest is not None and drive_folder:
        raise SystemExit("pass only one of --dest or --drive-folder")
    if dest is not None:
        return dest
    if not drive_folder:
        raise SystemExit("need --dest or --drive-folder")
    rel = Path(drive_folder)
    if rel.is_absolute():
        raise SystemExit("--drive-folder must be relative to My Drive, e.g. 跑步成片/slug/chunks")
    roots = find_drive_roots()
    if not roots:
        raise SystemExit("Google Drive desktop folder not found; pass --dest explicitly")
    if len(roots) > 1:
        listed = ", ".join(str(p) for p in roots)
        raise SystemExit(f"multiple Drive roots, pass --dest: {listed}")
    return roots[0] / rel


def copy_one(src: Path, dest: Path) -> str:
    if dest.exists():
        got = dest.stat().st_size
        expected = src.stat().st_size
        if got == expected:
            return f"skip {dest.name} (already {got} bytes)"
        raise FileExistsError(
            f"{dest.name} already exists with size {got}, expected {expected}; "
            "will not overwrite or trash it"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    try:
        shutil.copyfile(src, tmp)
        if dest.exists():
            tmp.unlink(missing_ok=True)
            got = dest.stat().st_size
            expected = src.stat().st_size
            if got == expected:
                return f"skip {dest.name} (appeared during copy, size matches)"
            raise FileExistsError(
                f"{dest.name} appeared during copy with size {got}, expected {expected}; "
                "left the existing file untouched"
            )
        tmp.replace(dest)
    except Exception:
        if tmp.exists() and not dest.exists():
            tmp.unlink(missing_ok=True)
        raise
    return f"copy {dest.name} ({dest.stat().st_size} bytes)"


def copy_missing(work_files: list[Path], dest_dir: Path, jobs: int) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []
    errors: list[str] = []
    workers = max(1, min(jobs, len(work_files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(copy_one, src, dest_dir / src.name): src for src in work_files}
        for fut in as_completed(futs):
            try:
                messages.append(fut.result())
            except Exception as exc:
                errors.append(str(exc))
    messages.sort()
    if errors:
        raise SystemExit("copy failed:\n" + "\n".join(errors))
    return messages


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split a file into sub-100MB chunks and copy new ones into a Drive folder in parallel."
    )
    parser.add_argument("--src", type=Path, required=True, help="local final file, usually upload/<title>.mp4")
    parser.add_argument("--dest", type=Path, help="absolute Google Drive desktop chunks directory")
    parser.add_argument(
        "--drive-folder",
        help="path under My Drive, e.g. 跑步成片/2026-11-10-double11-shoes/chunks",
    )
    parser.add_argument("--work-dir", type=Path, help="local directory for chunks, manifest, and sha256")
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES, help="default 99000000")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="parallel copy workers")
    parser.add_argument("--split-only", action="store_true", help="only write local chunks, do not copy to Drive")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    src = args.src.expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"source not found: {src}")
    if args.chunk_bytes <= 0:
        raise SystemExit("--chunk-bytes must be positive")
    if args.jobs <= 0:
        raise SystemExit("--jobs must be positive")

    work_dir = (args.work_dir or default_work_dir(src)).expanduser().resolve()
    total = src.stat().st_size
    digest = sha256_file(src)
    plan = plan_chunks(total, args.chunk_bytes)
    print(f"source {src} ({total} bytes)")
    print(f"sha256 {digest}")
    print(f"chunks {len(plan)} x up to {args.chunk_bytes} bytes -> {work_dir}")

    split_into_chunks(src, work_dir, plan)
    write_manifest(work_dir / MANIFEST_NAME, plan, total, digest, src)
    write_sha256_file(work_dir / HASH_NAME, digest, src)

    work_files = [work_dir / name for name, _offset, _size in plan]
    work_files.extend([work_dir / MANIFEST_NAME, work_dir / HASH_NAME])
    for path in work_files:
        if not path.is_file():
            raise SystemExit(f"missing local file after split: {path}")

    if args.split_only:
        print("split-only: local chunks are ready, nothing copied to Drive")
        return 0

    dest_dir = resolve_dest(
        args.dest.expanduser() if args.dest else None,
        args.drive_folder,
    )
    print(f"copy to {dest_dir} with {min(args.jobs, len(work_files))} workers")
    for line in copy_missing(work_files, dest_dir, args.jobs):
        print(line)
    print(
        "local copy into the Drive folder is done; "
        "wait until Drive API lists each file with a stable id and full size before downloading"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
