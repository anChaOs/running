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
import stat
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import BinaryIO

DEFAULT_CHUNK_BYTES = 99_000_000
DEFAULT_JOBS = 8
HASH_NAME = "original.sha256"
MANIFEST_NAME = "manifest.txt"


def _absolute_path(path: Path) -> Path:
    """转成绝对路径但不解析符号链接，便于后续拒绝链接路径。"""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _reject_newline(path: Path) -> None:
    if "\n" in str(path) or "\r" in str(path):
        raise ValueError("source path must not contain newline characters")


def _check_path_components(path: Path, label: str) -> Path:
    """检查已经存在的路径组件，不跟随任何符号链接。"""
    absolute = _absolute_path(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return absolute
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"{label} path contains a symbolic link: {current}")
        if current != absolute and not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(f"{label} path component is not a directory: {current}")
    return absolute


def _validate_directory(path: Path, label: str) -> Path:
    absolute = _check_path_components(path, label)
    try:
        info = absolute.lstat()
    except FileNotFoundError:
        return absolute
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} is a symbolic link: {absolute}")
    if not stat.S_ISDIR(info.st_mode):
        raise NotADirectoryError(f"{label} is not a directory: {absolute}")
    return absolute


def _ensure_directory(path: Path, label: str) -> Path:
    absolute = _validate_directory(path, label)
    absolute.mkdir(parents=True, exist_ok=True)
    return _validate_directory(absolute, label)


def _validate_output_file(path: Path, label: str) -> Path:
    absolute = _absolute_path(path)
    _check_path_components(absolute.parent, label)
    try:
        info = absolute.lstat()
    except FileNotFoundError:
        return absolute
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} is a symbolic link: {absolute}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} is not a regular file: {absolute}")
    return absolute


def _require_regular_file(path: Path, label: str) -> os.stat_result:
    absolute = _absolute_path(path)
    _reject_newline(absolute)
    _check_path_components(absolute, label)
    try:
        info = absolute.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"{label} not found: {absolute}") from None
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} is a symbolic link: {absolute}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} is not a regular file: {absolute}")
    return info


def _file_signature(path: Path) -> tuple[int, int, int, int]:
    info = _require_regular_file(path, "source")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def sha256_file(path: Path) -> str:
    _require_regular_file(path, "file")
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_source_info(path: Path) -> tuple[int, str]:
    before = _file_signature(path)
    digest = sha256_file(path)
    after = _file_signature(path)
    if before != after:
        raise ValueError("source changed while being read")
    return after[2], digest


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


def _new_temp(path: Path, label: str) -> tuple[Path, BinaryIO]:
    parent = _ensure_directory(path.parent, f"{label} parent")
    for _ in range(10):
        temp = parent / f".{path.name}.partial.{os.getpid()}.{uuid.uuid4().hex}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            fd = os.open(temp, flags, 0o600)
        except FileExistsError:
            continue
        try:
            return temp, os.fdopen(fd, "wb")
        except Exception:
            os.close(fd)
            temp.unlink(missing_ok=True)
            raise
    raise FileExistsError(f"could not create exclusive temporary file for {path}")


def _cleanup_temp(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _write_chunk_bytes(
    inf: BinaryIO,
    out: BinaryIO,
    size: int,
    digest: hashlib._Hash | None = None,
    chunk_digest: hashlib._Hash | None = None,
) -> int:
    remaining = size
    while remaining:
        block = inf.read(min(1024 * 1024, remaining))
        if not block:
            break
        out.write(block)
        if digest is not None:
            digest.update(block)
        if chunk_digest is not None:
            chunk_digest.update(block)
        remaining -= len(block)
    return remaining


def write_manifest(path: Path, plan: list[tuple[str, int, int]], total: int, digest: str, src: Path) -> None:
    _reject_newline(src)
    lines = [f"{name} {size}" for name, _, size in plan]
    lines.append(f"TOTAL {total}")
    lines.append(f"SHA256 {digest}  {src}")
    _atomic_write_text(path, "\n".join(lines) + "\n", "manifest")


def write_sha256_file(path: Path, digest: str, src: Path) -> None:
    _reject_newline(src)
    _atomic_write_text(path, f"{digest}  {src}\n", "sha256 file")


def _atomic_write_text(path: Path, content: str, label: str) -> None:
    destination = _validate_output_file(path, label)
    temp, out = _new_temp(destination, label)
    try:
        with out:
            out.write(content.encode("utf-8"))
        info = temp.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(content.encode("utf-8")):
            raise OSError(f"failed to write complete {label}: {destination}")
        _validate_output_file(destination, label)
        os.replace(temp, destination)
    except Exception:
        _cleanup_temp(temp)
        raise


def _publish_replace(temp: Path, destination: Path, label: str) -> None:
    _validate_output_file(destination, label)
    os.replace(temp, destination)


def split_into_chunks(
    src: Path,
    work_dir: Path,
    plan: list[tuple[str, int, int]],
    expected_digest: str | None = None,
) -> list[Path]:
    source = _absolute_path(src)
    work = _ensure_directory(work_dir, "work directory")
    _require_regular_file(source, "source")
    source_signature = _file_signature(source)
    staged: list[tuple[Path, Path, int]] = []
    written: list[Path] = []
    actual_digest = hashlib.sha256()
    try:
        with source.open("rb") as inf:
            for name, offset, size in plan:
                destination = _validate_output_file(work / name, "chunk output")
                # 固定名称的旧临时文件不参与写入，但链接和特殊文件不能被忽略。
                _validate_output_file(destination.with_name(destination.name + ".partial"), "chunk temporary file")
                inf.seek(offset)
                temp, out = _new_temp(destination, "chunk")
                try:
                    with out:
                        remaining = _write_chunk_bytes(inf, out, size, actual_digest)
                    info = temp.lstat()
                    if remaining or not stat.S_ISREG(info.st_mode) or info.st_size != size:
                        raise OSError(f"failed to write full chunk: {destination} expected {size}")
                except Exception:
                    _cleanup_temp(temp)
                    raise
                staged.append((destination, temp, size))
        if _file_signature(source) != source_signature:
            raise ValueError("source changed while splitting")
        actual = actual_digest.hexdigest()
        source_digest = sha256_file(source)
        if actual != source_digest or (expected_digest is not None and actual != expected_digest):
            raise ValueError("source changed while splitting")
        for destination, temp, _ in staged:
            _publish_replace(temp, destination, "chunk output")
            written.append(destination)
    except Exception:
        for _, temp, _ in staged:
            _cleanup_temp(temp)
        raise
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
        expanded = dest.expanduser()
        if not expanded.is_absolute():
            raise SystemExit("--dest must be an absolute path")
        destination = _absolute_path(expanded)
        _validate_directory(destination, "destination")
        return destination
    if not drive_folder:
        raise SystemExit("need --dest or --drive-folder")
    rel = Path(drive_folder)
    if rel.is_absolute():
        raise SystemExit("--drive-folder must be relative to My Drive, e.g. 跑步成片/slug/chunks")
    if ".." in rel.parts:
        raise SystemExit("--drive-folder must not contain ..")
    roots = find_drive_roots()
    if not roots:
        raise SystemExit("Google Drive desktop folder not found; pass --dest explicitly")
    if len(roots) > 1:
        listed = ", ".join(str(p) for p in roots)
        raise SystemExit(f"multiple Drive roots, pass --dest: {listed}")
    root = _validate_directory(roots[0], "Drive root")
    destination = _absolute_path(root / rel)
    try:
        destination.relative_to(root)
    except ValueError:
        raise SystemExit("--drive-folder resolves outside the Drive root") from None
    _validate_directory(destination, "destination")
    return destination


def _existing_regular_file(path: Path, label: str) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise FileExistsError(f"{label} is a symbolic link: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise FileExistsError(f"{label} is not a regular file: {path}")
    return info


def _publish_noreplace(temp: Path, destination: Path) -> None:
    # 同目录硬链接发布在目标已存在时原子失败，不使用 replace 覆盖并发目标。
    os.link(temp, destination, follow_symlinks=False)


def copy_one(src: Path, dest: Path) -> str:
    source = _absolute_path(src)
    destination = _validate_output_file(dest, "destination file")
    _require_regular_file(source, "source file")
    _ensure_directory(destination.parent, "destination parent")
    _validate_output_file(destination.with_name(destination.name + ".partial"), "destination temporary file")
    expected, expected_digest = _stable_source_info(source)

    existing = _existing_regular_file(destination, "destination file")
    if existing is not None:
        if existing.st_size == expected and sha256_file(destination) == expected_digest:
            return f"skip {destination.name} (already {expected} bytes, digest matches)"
        if existing.st_size == expected:
            raise FileExistsError(
                f"{destination.name} already exists with matching size but different content; "
                "will not overwrite or trash it"
            )
        raise FileExistsError(
            f"{destination.name} already exists with size {existing.st_size}, expected {expected}; "
            "will not overwrite or trash it"
        )

    temp, out = _new_temp(destination, "destination copy")
    try:
        with out:
            with source.open("rb") as inf:
                shutil.copyfileobj(inf, out, length=1024 * 1024)
        info = temp.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected:
            raise OSError(f"source changed while copying {source}")
        if sha256_file(temp) != expected_digest:
            raise OSError(f"source changed while copying {source}")
        try:
            _publish_noreplace(temp, destination)
        except FileExistsError:
            appeared = _existing_regular_file(destination, "destination file")
            if appeared is not None and appeared.st_size == expected and sha256_file(destination) == expected_digest:
                return f"skip {destination.name} (appeared during copy, digest matches)"
            raise FileExistsError(
                f"{destination.name} appeared during copy; left the existing file untouched"
            )
    finally:
        _cleanup_temp(temp)
    return f"copy {destination.name} ({expected} bytes)"


def copy_missing(work_files: list[Path], dest_dir: Path, jobs: int) -> list[str]:
    destination = _ensure_directory(dest_dir, "destination")
    messages: list[str] = []
    errors: list[str] = []
    workers = max(1, min(jobs, len(work_files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(copy_one, src, destination / src.name): src for src in work_files}
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


def _validate_work_dir(source: Path, work_dir: Path, plan: list[tuple[str, int, int]]) -> Path:
    work = _absolute_path(work_dir)
    _check_path_components(work, "work directory")
    if work == source or work in source.parents:
        raise ValueError("source must not be inside work directory")
    _ensure_directory(work, "work directory")
    output_names = [name for name, _, _ in plan]
    output_names.extend((MANIFEST_NAME, HASH_NAME))
    for name in output_names:
        _validate_output_file(work / name, "work output")
    for name in output_names:
        if name.startswith("chunk-"):
            _validate_output_file(work / f"{name}.partial", "work temporary file")
    return work


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        src = _absolute_path(args.src)
        _reject_newline(src)
        try:
            source_info = _require_regular_file(src, "source")
        except FileNotFoundError:
            raise SystemExit(f"source not found: {src}") from None
        if args.chunk_bytes <= 0:
            raise SystemExit("--chunk-bytes must be positive")
        if args.jobs <= 0:
            raise SystemExit("--jobs must be positive")

        total, digest = _stable_source_info(src)
        plan = plan_chunks(total, args.chunk_bytes)
        work_dir = _validate_work_dir(src, args.work_dir or default_work_dir(src), plan)
        print(f"source {src} ({source_info.st_size} bytes)")
        print(f"sha256 {digest}")
        print(f"chunks {len(plan)} x up to {args.chunk_bytes} bytes -> {work_dir}")

        split_into_chunks(src, work_dir, plan, expected_digest=digest)
        after_total, after_digest = _stable_source_info(src)
        if after_total != total or after_digest != digest:
            raise ValueError("source changed after splitting")
        write_manifest(work_dir / MANIFEST_NAME, plan, total, digest, src)
        write_sha256_file(work_dir / HASH_NAME, digest, src)

        work_files = [work_dir / name for name, _, _ in plan]
        work_files.extend([work_dir / MANIFEST_NAME, work_dir / HASH_NAME])
        for path in work_files:
            _validate_output_file(path, "local output")

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
    except SystemExit:
        raise
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    sys.exit(main())
