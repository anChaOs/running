#!/usr/bin/env python3
"""把成片切成略小于 100MB 的块，再并行拷进 Google Drive 桌面版目录。

默认只新增，不覆盖、不删除、不进废纸篓。本机拷完只说明文件已交给桌面客户端，
云端就绪还要等 Drive API 能列出稳定 id 和完整体积后再算。

新文件优先在同一目录硬链接；DriveFS 一类文件系统不支持时，改为对目标名排他创建后再写入。
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import os
import shutil
import stat
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import BinaryIO, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import log_timeline  # noqa: E402

DEFAULT_CHUNK_BYTES = 99_000_000
DEFAULT_JOBS = 8
HASH_NAME = "original.sha256"
MANIFEST_NAME = "manifest.txt"
_DRIVE_LEAVES = ("我的云端硬盘", "My Drive")
# 这些 errno 表示硬链接做不到，不是目标已存在。Drive 桌面版常见 ENOTSUP / EPERM / EXDEV。
_LINK_UNSUPPORTED_ERRNOS = {
    errno.EPERM,
    errno.EXDEV,
    errno.ENOTSUP,
    errno.EOPNOTSUPP,
}
if hasattr(errno, "ENOSYS"):
    _LINK_UNSUPPORTED_ERRNOS.add(errno.ENOSYS)


def _absolute_path(path: Path) -> Path:
    """转成绝对路径但不解析符号链接，便于后续拒绝链接路径。"""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _reject_newline(path: Path) -> None:
    if "\n" in str(path) or "\r" in str(path):
        raise ValueError("source path must not contain newline characters")


def _safe_leaf(name: str) -> None:
    """目录 fd 上的名字必须是单级文件名，不能借此走回路径解析。"""
    if name in ("", ".", "..") or "/" in name or "\x00" in name:
        raise ValueError(f"unsafe file name: {name}")


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


class _Dir:
    """已用 O_NOFOLLOW 逐级打开的目录。后续创建和发布都相对这个 fd，不再按路径重走父目录。"""

    def __init__(self, fd: int, path: Path) -> None:
        self.fd = fd
        self.path = path

    def close(self) -> None:
        fd = self.fd
        if fd < 0:
            return
        self.fd = -1
        os.close(fd)

    def lstat(self, name: str) -> os.stat_result | None:
        _safe_leaf(name)
        try:
            return os.lstat(name, dir_fd=self.fd)
        except FileNotFoundError:
            return None

    def unlink(self, name: str) -> None:
        _safe_leaf(name)
        try:
            os.unlink(name, dir_fd=self.fd)
        except FileNotFoundError:
            pass


def _open_child(parent_fd: int, part: str, current: Path, label: str, flags: int, is_last: bool) -> int | None:
    try:
        return os.open(part, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f"{label} path contains a symbolic link: {current}") from None
        if exc.errno == errno.ENOTDIR:
            if is_last:
                raise NotADirectoryError(f"{label} is not a directory: {current}") from None
            raise NotADirectoryError(f"{label} path component is not a directory: {current}") from None
        raise


def _open_dir(path: Path, label: str, *, create: bool) -> _Dir:
    """从根开始逐级 O_NOFOLLOW 打开目录。create 时缺的层级在父 fd 上 mkdir，不按路径跟链接。"""
    absolute = _absolute_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    try:
        for index, part in enumerate(parts):
            current = current / part
            is_last = index == len(parts) - 1
            child = _open_child(fd, part, current, label, flags, is_last)
            if child is None:
                if not create:
                    raise FileNotFoundError(f"{label} not found: {absolute}")
                try:
                    os.mkdir(part, 0o777, dir_fd=fd)
                except FileExistsError:
                    pass
                child = _open_child(fd, part, current, label, flags, is_last)
                if child is None:
                    raise FileNotFoundError(f"{label} not found: {absolute}")
            os.close(fd)
            fd = child
        held = fd
        fd = -1
        return _Dir(held, absolute)
    finally:
        if fd >= 0:
            os.close(fd)


def _ensure_directory(path: Path, label: str) -> Path:
    absolute = _validate_directory(path, label)
    directory = _open_dir(absolute, label, create=True)
    try:
        return directory.path
    finally:
        directory.close()


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


def _sha256_name(directory: _Dir, name: str) -> str:
    _safe_leaf(name)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory.fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise FileExistsError(f"file is a symbolic link: {directory.path / name}") from None
        raise
    try:
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(fd)


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


def _reject_output_name(directory: _Dir, name: str, label: str) -> None:
    info = directory.lstat(name)
    if info is None:
        return
    display = directory.path / name
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} is a symbolic link: {display}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} is not a regular file: {display}")


def _create_temp(directory: _Dir, final_name: str) -> tuple[str, BinaryIO]:
    _safe_leaf(final_name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    for _ in range(10):
        name = f".{final_name}.partial.{os.getpid()}.{uuid.uuid4().hex}"
        try:
            fd = os.open(name, flags, 0o600, dir_fd=directory.fd)
        except FileExistsError:
            continue
        try:
            return name, os.fdopen(fd, "wb")
        except Exception:
            os.close(fd)
            directory.unlink(name)
            raise
    raise FileExistsError(f"could not create exclusive temporary file for {final_name}")


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


def _manifest_text(plan: list[tuple[str, int, int]], total: int, digest: str, src: Path) -> str:
    _reject_newline(src)
    lines = [f"{name} {size}" for name, _, size in plan]
    lines.append(f"TOTAL {total}")
    lines.append(f"SHA256 {digest}  {src}")
    return "\n".join(lines) + "\n"


def _sha_text(digest: str, src: Path) -> str:
    _reject_newline(src)
    return f"{digest}  {src}\n"


def _stage_chunks_into(
    directory: _Dir,
    source: Path,
    plan: list[tuple[str, int, int]],
    expected_digest: str | None,
    staged: list[tuple[str, str]],
) -> None:
    _require_regular_file(source, "source")
    signature = _file_signature(source)
    actual = hashlib.sha256()
    with source.open("rb") as inf:
        for name, offset, size in plan:
            _safe_leaf(name)
            _reject_output_name(directory, name, "chunk output")
            # 固定名称的旧临时文件不参与写入，但链接和特殊文件不能被忽略。
            _reject_output_name(directory, f"{name}.partial", "chunk temporary file")
            inf.seek(offset)
            temp_name, out = _create_temp(directory, name)
            try:
                with out:
                    remaining = _write_chunk_bytes(inf, out, size, actual)
                info = directory.lstat(temp_name)
                if remaining or info is None or not stat.S_ISREG(info.st_mode) or info.st_size != size:
                    raise OSError(f"failed to write full chunk: {directory.path / name} expected {size}")
            except Exception:
                directory.unlink(temp_name)
                raise
            staged.append((temp_name, name))
    if _file_signature(source) != signature:
        raise ValueError("source changed while splitting")
    got = actual.hexdigest()
    source_digest = sha256_file(source)
    if got != source_digest or (expected_digest is not None and got != expected_digest):
        raise ValueError("source changed while splitting")


def _stage_text_into(
    directory: _Dir,
    final_name: str,
    content: str,
    label: str,
    staged: list[tuple[str, str]],
) -> None:
    _safe_leaf(final_name)
    _reject_output_name(directory, final_name, label)
    data = content.encode("utf-8")
    temp_name, out = _create_temp(directory, final_name)
    try:
        with out:
            out.write(data)
        info = directory.lstat(temp_name)
        if info is None or not stat.S_ISREG(info.st_mode) or info.st_size != len(data):
            raise OSError(f"failed to write complete {label}: {directory.path / final_name}")
    except Exception:
        directory.unlink(temp_name)
        raise
    staged.append((temp_name, final_name))


def _install_new_file(directory: _Dir, temp_name: str, final_name: str) -> None:
    """把临时名换成最终名。调用前旧文件应已挪走，这样失败时还能按 backup 恢复。"""
    _safe_leaf(temp_name)
    _safe_leaf(final_name)
    os.replace(temp_name, final_name, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)


def _move_aside(directory: _Dir, name: str) -> str | None:
    info = directory.lstat(name)
    if info is None:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"output is a symbolic link: {directory.path / name}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"output is not a regular file: {directory.path / name}")
    backup = f".{name}.rollback.{os.getpid()}.{uuid.uuid4().hex}"
    _safe_leaf(backup)
    os.replace(name, backup, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
    return backup


def _restore_backup(directory: _Dir, final_name: str, backup: str | None) -> None:
    if backup is None:
        directory.unlink(final_name)
        return
    os.replace(backup, final_name, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)


def _rollback_committed(directory: _Dir, committed: list[tuple[str, str | None]]) -> None:
    errors: list[str] = []
    for final_name, backup in reversed(committed):
        try:
            _restore_backup(directory, final_name, backup)
        except OSError as exc:
            errors.append(str(exc))
    if errors:
        raise OSError("rollback failed: " + "; ".join(errors))


def _publish_generation(directory: _Dir, staged: list[tuple[str, str]]) -> None:
    """按顺序把一代临时文件换成可见名。中途失败则恢复已经替换掉的旧文件。

    异常返回后，调用方看到的是上一代或什么都没发布，而不是新旧混在一起。
    进程被强杀或断电不在这个保证里：那时可能留下 .rollback 文件和半代内容。
    """
    committed: list[tuple[str, str | None]] = []
    try:
        for temp_name, final_name in staged:
            backup = _move_aside(directory, final_name)
            try:
                _install_new_file(directory, temp_name, final_name)
            except Exception as install_exc:
                try:
                    _restore_backup(directory, final_name, backup)
                except OSError as restore_exc:
                    raise OSError(
                        f"publish failed ({install_exc}) and restoring {final_name} failed ({restore_exc})"
                    ) from install_exc
                raise
            committed.append((final_name, backup))
    except Exception as original:
        try:
            _rollback_committed(directory, committed)
        except OSError as rollback_exc:
            raise OSError(f"{original}; {rollback_exc}") from original
        raise
    # 备份清掉失败也不能回滚：可见文件已经是这一代，回滚会把成功结果毁掉。
    for _, backup in committed:
        if backup is not None:
            try:
                directory.unlink(backup)
            except OSError:
                pass


def _with_directory(
    work_dir: Path,
    action: Callable[[_Dir, list[tuple[str, str]]], None],
) -> list[Path]:
    directory = _open_dir(work_dir, "work directory", create=True)
    staged: list[tuple[str, str]] = []
    try:
        action(directory, staged)
        _publish_generation(directory, staged)
        return [directory.path / final for _, final in staged]
    except Exception:
        for temp_name, _ in staged:
            try:
                directory.unlink(temp_name)
            except OSError:
                pass
        raise
    finally:
        directory.close()


def split_into_chunks(
    src: Path,
    work_dir: Path,
    plan: list[tuple[str, int, int]],
    expected_digest: str | None = None,
) -> list[Path]:
    source = _absolute_path(src)

    def action(directory: _Dir, staged: list[tuple[str, str]]) -> None:
        _stage_chunks_into(directory, source, plan, expected_digest, staged)

    return _with_directory(work_dir, action)


def _write_generation(
    src: Path,
    work_dir: Path,
    plan: list[tuple[str, int, int]],
    total: int,
    digest: str,
) -> None:
    """分块、manifest、sha256 作为一代发布。失败时整代回滚，不留下新块配旧 manifest。"""
    source = _absolute_path(src)

    def action(directory: _Dir, staged: list[tuple[str, str]]) -> None:
        _stage_chunks_into(directory, source, plan, digest, staged)
        after_total, after_digest = _stable_source_info(source)
        if after_total != total or after_digest != digest:
            raise ValueError("source changed after splitting")
        # 顺序固定：先按 plan 发布分块，再 manifest，再 sha256。回滚测试依赖这个顺序。
        _stage_text_into(directory, MANIFEST_NAME, _manifest_text(plan, total, digest, source), "manifest", staged)
        _stage_text_into(directory, HASH_NAME, _sha_text(digest, source), "sha256 file", staged)

    _with_directory(work_dir, action)


def _atomic_write_text(path: Path, content: str, label: str) -> None:
    destination = _validate_output_file(path, label)
    directory = _open_dir(destination.parent, f"{label} parent", create=True)
    staged: list[tuple[str, str]] = []
    try:
        _stage_text_into(directory, destination.name, content, label, staged)
        _install_new_file(directory, staged[0][0], destination.name)
    except Exception:
        for temp_name, _ in staged:
            try:
                directory.unlink(temp_name)
            except OSError:
                pass
        raise
    finally:
        directory.close()


def write_manifest(path: Path, plan: list[tuple[str, int, int]], total: int, digest: str, src: Path) -> None:
    _atomic_write_text(path, _manifest_text(plan, total, digest, src), "manifest")


def write_sha256_file(path: Path, digest: str, src: Path) -> None:
    _atomic_write_text(path, _sha_text(digest, src), "sha256 file")


def default_work_dir(src: Path) -> Path:
    if src.parent.name == "upload":
        return src.parent.parent / "yt-drive-chunks"
    return src.parent / "yt-drive-chunks"


def _realpath_directory(path: Path) -> Path | None:
    """把已知候选解析成不含符号链接的真实目录。解析不了就不收，避免发现之后又被自己拒绝。"""
    try:
        if not path.exists():
            return None
        resolved = Path(os.path.realpath(path))
        info = resolved.lstat()
    except OSError:
        return None
    if resolved == Path(resolved.anchor):
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return None
    try:
        _check_path_components(resolved, "Drive root")
    except (OSError, ValueError):
        return None
    return resolved


def find_drive_roots() -> list[Path]:
    """只认 CloudStorage 下的 GoogleDrive-* 和 ~/Google Drive 这两个入口。

    入口本身可以是指向真实盘的符号链接；返回值是解析后的真实目录，后面不再跟随用户路径里的链接。
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def consider(cand: Path) -> None:
        try:
            exists = cand.is_dir()
        except OSError:
            return
        if not exists:
            return
        resolved = _realpath_directory(cand)
        if resolved is None or resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    cloud = Path.home() / "Library" / "CloudStorage"
    try:
        cloud_is_dir = cloud.is_dir()
    except OSError:
        cloud_is_dir = False
    if cloud_is_dir:
        for mount in sorted(cloud.glob("GoogleDrive-*")):
            for folder in _DRIVE_LEAVES:
                consider(mount / folder)
    alias = Path.home() / "Google Drive"
    try:
        alias_exists = alias.exists()
    except OSError:
        alias_exists = False
    if alias_exists:
        for folder in _DRIVE_LEAVES:
            consider(alias / folder)
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


def _existing_in(directory: _Dir, name: str, label: str) -> os.stat_result | None:
    info = directory.lstat(name)
    if info is None:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise FileExistsError(f"{label} is a symbolic link: {directory.path / name}")
    if not stat.S_ISREG(info.st_mode):
        raise FileExistsError(f"{label} is not a regular file: {directory.path / name}")
    return info


def _copy_exclusive(directory: _Dir, temp_name: str, dest_name: str) -> None:
    """硬链接不可用时，用 O_EXCL 创建目标名再写入。已存在则抛 FileExistsError，调用方不得删除它。"""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        out_fd = os.open(dest_name, flags, 0o600, dir_fd=directory.fd)
    except FileExistsError:
        raise
    created_ino = os.fstat(out_fd).st_ino
    try:
        in_fd = os.open(temp_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory.fd)
        try:
            src_size = os.fstat(in_fd).st_size
            written = 0
            while True:
                block = os.read(in_fd, 1024 * 1024)
                if not block:
                    break
                offset = 0
                while offset < len(block):
                    count = os.write(out_fd, block[offset:])
                    if count <= 0:
                        raise OSError(f"short write publishing {dest_name}")
                    offset += count
                    written += count
            if written != src_size or os.fstat(out_fd).st_size != src_size:
                raise OSError(f"incomplete publish of {dest_name}")
        finally:
            os.close(in_fd)
    except Exception:
        os.close(out_fd)
        # 只删除本次 O_EXCL 创建的 inode。名字若已被换成别的文件，不能跟着删。
        current = directory.lstat(dest_name)
        if current is not None and not stat.S_ISLNK(current.st_mode) and current.st_ino == created_ino:
            directory.unlink(dest_name)
        raise
    os.close(out_fd)


def _publish_noreplace(directory: _Dir, temp_name: str, dest_name: str) -> None:
    """同目录发布新文件。能硬链接就硬链接；文件系统不支持时排他复制。目标已存在则失败且不覆盖。"""
    _safe_leaf(temp_name)
    _safe_leaf(dest_name)
    try:
        os.link(
            temp_name,
            dest_name,
            src_dir_fd=directory.fd,
            dst_dir_fd=directory.fd,
            follow_symlinks=False,
        )
        return
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno not in _LINK_UNSUPPORTED_ERRNOS:
            raise
    _copy_exclusive(directory, temp_name, dest_name)


def copy_one(src: Path, dest: Path) -> str:
    source = _absolute_path(src)
    destination = _validate_output_file(dest, "destination file")
    _require_regular_file(source, "source file")
    directory = _open_dir(destination.parent, "destination parent", create=True)
    try:
        _reject_output_name(directory, destination.name, "destination file")
        _reject_output_name(directory, f"{destination.name}.partial", "destination temporary file")
        expected, expected_digest = _stable_source_info(source)
        existing = _existing_in(directory, destination.name, "destination file")
        if existing is not None:
            if existing.st_size == expected and _sha256_name(directory, destination.name) == expected_digest:
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

        temp_name, out = _create_temp(directory, destination.name)
        try:
            with out:
                with source.open("rb") as inf:
                    shutil.copyfileobj(inf, out, length=1024 * 1024)
            info = directory.lstat(temp_name)
            if info is None or not stat.S_ISREG(info.st_mode) or info.st_size != expected:
                raise OSError(f"source changed while copying {source}")
            if _sha256_name(directory, temp_name) != expected_digest:
                raise OSError(f"source changed while copying {source}")
            try:
                _publish_noreplace(directory, temp_name, destination.name)
            except FileExistsError:
                appeared = _existing_in(directory, destination.name, "destination file")
                if (
                    appeared is not None
                    and appeared.st_size == expected
                    and _sha256_name(directory, destination.name) == expected_digest
                ):
                    return f"skip {destination.name} (appeared during copy, digest matches)"
                raise FileExistsError(
                    f"{destination.name} appeared during copy; left the existing file untouched"
                )
        finally:
            directory.unlink(temp_name)
        return f"copy {destination.name} ({expected} bytes)"
    finally:
        directory.close()


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
    src = Path(args.src).expanduser()
    media = src.parent.parent if src.parent.name == "upload" else None
    with log_timeline.span(media if media is not None else src, "drive-stage", enabled=media is not None) as wall:
        wall.rc = _stage(args)
        return wall.rc


def _stage(args) -> int:
    try:
        if args.dest is not None and args.drive_folder:
            raise SystemExit("pass only one of --dest or --drive-folder")
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

        _write_generation(src, work_dir, plan, total, digest)

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
