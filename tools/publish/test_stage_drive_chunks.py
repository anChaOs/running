#!/usr/bin/env python3
"""只用临时目录和小字节文件测试分块、复制及路径安全边界。"""

from __future__ import annotations

import errno
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import stage_drive_chunks as sdc


def _staged_leftovers(path: Path) -> list[Path]:
    """唯一临时文件和回滚文件都以点开头，不能只靠最终文件名判断目录是否干净。"""
    return [
        child
        for child in path.iterdir()
        if ".partial." in child.name or ".rollback." in child.name or child.name.endswith(".partial")
    ]


class StageDriveChunksTest(unittest.TestCase):
    def test_plan_chunks_last_remainder(self) -> None:
        plan = sdc.plan_chunks(321_478_7178, 99_000_000)
        self.assertEqual(len(plan), 33)
        self.assertEqual(plan[0], ("chunk-00", 0, 99_000_000))
        self.assertEqual(plan[-1], ("chunk-32", 32 * 99_000_000, 46_787_178))
        self.assertEqual(sum(size for _, _, size in plan), 3_214_787_178)

    def test_plan_chunks_width_stays_two_until_100(self) -> None:
        plan = sdc.plan_chunks(99_000_000 * 10, 99_000_000)
        self.assertEqual(plan[0][0], "chunk-00")
        self.assertEqual(plan[-1][0], "chunk-09")

    def test_split_manifest_and_rebuild_digest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "final.mp4"
            data = b"abcdefghijklmnopqrstuvwxyz012345"
            src.write_bytes(data)
            work = root / "yt-drive-chunks"
            plan = sdc.plan_chunks(len(data), 10)
            digest = sdc.sha256_file(src)
            paths = sdc.split_into_chunks(src, work, plan, expected_digest=digest)
            self.assertEqual(len(paths), 4)
            self.assertEqual(b"".join(path.read_bytes() for path in paths), data)
            self.assertEqual(
                hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest(),
                digest,
            )
            sdc.write_manifest(work / sdc.MANIFEST_NAME, plan, len(data), digest, src)
            sdc.write_sha256_file(work / sdc.HASH_NAME, digest, src)
            manifest = (work / sdc.MANIFEST_NAME).read_text(encoding="utf-8")
            self.assertIn("chunk-00 10\n", manifest)
            self.assertIn(f"TOTAL {len(data)}\n", manifest)
            self.assertIn(f"SHA256 {digest}  {src}\n", manifest)
            self.assertEqual((work / sdc.HASH_NAME).read_text(encoding="utf-8"), f"{digest}  {src}\n")

            # 同大小的旧分块也必须被当前源内容重新生成。
            (work / "chunk-00").write_bytes(b"x" * 10)
            sdc.split_into_chunks(src, work, plan, expected_digest=digest)
            self.assertEqual((work / "chunk-00").read_bytes(), data[:10])

    def test_copy_skips_only_digest_match_and_refuses_same_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = root / "work"
            dest = root / "drive-chunks"
            work.mkdir()
            dest.mkdir()
            src = work / "chunk-00"
            src.write_bytes(b"x" * 10)
            dest_ok = dest / "chunk-00"
            dest_ok.write_bytes(b"x" * 10)
            msg = sdc.copy_one(src, dest_ok)
            self.assertTrue(msg.startswith("skip"))
            self.assertIn("digest matches", msg)

            dest_bad = dest / "chunk-01"
            other = work / "chunk-01"
            other.write_bytes(b"y" * 10)
            dest_bad.write_bytes(b"z" * 10)
            with self.assertRaisesRegex(FileExistsError, "different content"):
                sdc.copy_one(other, dest_bad)
            self.assertEqual(dest_bad.read_bytes(), b"z" * 10)
            self.assertFalse(list(dest.glob("*.partial*")))

    def test_copy_missing_writes_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = root / "work"
            dest = root / "drive-chunks"
            work.mkdir()
            src = work / "chunk-02"
            src.write_bytes(b"hello-chunk")
            lines = sdc.copy_missing([src], dest, jobs=2)
            self.assertEqual((dest / "chunk-02").read_bytes(), b"hello-chunk")
            self.assertTrue(any(line.startswith("copy chunk-02") for line in lines))
            self.assertFalse(list(dest.glob("*.partial*")))

    def test_split_rejects_source_inside_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = root / "work"
            src = work / "source.bin"
            work.mkdir()
            src.write_bytes(b"source")
            with self.assertRaisesRegex(SystemExit, "source must not be inside work directory"):
                sdc.main(["--src", str(src), "--work-dir", str(work), "--split-only"])

    def test_split_write_error_removes_unique_partial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.bin"
            work = root / "work"
            src.write_bytes(b"0123456789")
            plan = sdc.plan_chunks(10, 5)
            with mock.patch.object(sdc, "_write_chunk_bytes", side_effect=OSError("simulated write failure")):
                with self.assertRaisesRegex(OSError, "simulated write failure"):
                    sdc.split_into_chunks(src, work, plan)
            self.assertFalse(list(work.glob("*.partial*")))
            self.assertFalse((work / "chunk-00").exists())

    def test_symlink_paths_are_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside.bin"
            outside.write_bytes(b"keep")
            src = root / "source.bin"
            src.write_bytes(b"0123456789")
            work = root / "work"
            work.mkdir()
            plan = sdc.plan_chunks(10, 10)

            (work / "chunk-00.partial").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sdc.split_into_chunks(src, work, plan)
            self.assertEqual(outside.read_bytes(), b"keep")

            manifest = work / sdc.MANIFEST_NAME
            manifest.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sdc.write_manifest(manifest, plan, 10, sdc.sha256_file(src), src)
            self.assertEqual(outside.read_bytes(), b"keep")

            hash_file = work / sdc.HASH_NAME
            hash_file.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sdc.write_sha256_file(hash_file, sdc.sha256_file(src), src)
            self.assertEqual(outside.read_bytes(), b"keep")

            destination = root / "destination"
            destination.mkdir()
            target = destination / "chunk-00"
            target.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sdc.copy_one(src, target)
            self.assertEqual(outside.read_bytes(), b"keep")

            dangling = destination / "dangling"
            dangling.symlink_to(root / "missing")
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sdc.copy_one(src, dangling)

            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(destination, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sdc.copy_one(src, linked_parent / "new")

    def test_racing_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.bin"
            dest = root / "dest"
            src.write_bytes(b"source")
            dest.mkdir()
            target = dest / "source.bin"

            def race(directory: sdc._Dir, temp_name: str, dest_name: str) -> None:
                info = directory.lstat(temp_name)
                if info is None or info.st_size <= 0:
                    raise AssertionError("temporary file was not created")
                fd = os.open(
                    dest_name,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=directory.fd,
                )
                try:
                    os.write(fd, b"raced!")
                finally:
                    os.close(fd)
                raise FileExistsError(dest_name)

            with mock.patch.object(sdc, "_publish_noreplace", side_effect=race):
                with self.assertRaisesRegex(FileExistsError, "appeared during copy"):
                    sdc.copy_one(src, target)
            self.assertEqual(target.read_bytes(), b"raced!")
            self.assertFalse(list(dest.glob("*.partial*")))

    def test_copy_falls_back_when_hardlink_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "drive"
            dest.mkdir()
            fresh = root / "chunk-00"
            payload = b"h" * (1024 * 1024 + 32)
            fresh.write_bytes(payload)
            link_error = OSError(errno.ENOTSUP, "Operation not supported")
            with mock.patch("os.link", side_effect=link_error) as link_mock:
                msg = sdc.copy_one(fresh, dest / "chunk-00")
            self.assertTrue(link_mock.called)
            self.assertTrue(msg.startswith("copy"))
            self.assertEqual((dest / "chunk-00").read_bytes(), payload)
            self.assertFalse(_staged_leftovers(dest))

            existing = dest / "chunk-01"
            existing.write_bytes(b"zzzzzzzzzz")
            other = root / "chunk-01"
            other.write_bytes(b"yyyyyyyyyy")
            with mock.patch("os.link", side_effect=link_error) as link_mock:
                with self.assertRaisesRegex(FileExistsError, "different content"):
                    sdc.copy_one(other, existing)
            self.assertFalse(link_mock.called)
            self.assertEqual(existing.read_bytes(), b"zzzzzzzzzz")
            self.assertFalse(_staged_leftovers(dest))

    def test_exclusive_copy_failure_removes_only_the_file_it_created(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "drive"
            dest.mkdir()
            directory = sdc._open_dir(dest, "destination", create=True)
            try:
                temp_name, out = sdc._create_temp(directory, "chunk-00")
                with out:
                    out.write(b"payload")

                def fail_read(*args: object) -> bytes:
                    raise OSError(f"simulated copy failure ({len(args)} args)")

                with mock.patch("os.read", side_effect=fail_read):
                    with self.assertRaisesRegex(OSError, "simulated copy failure"):
                        sdc._copy_exclusive(directory, temp_name, "chunk-00")
                self.assertIsNone(directory.lstat("chunk-00"))
                self.assertIsNotNone(directory.lstat(temp_name))
                directory.unlink(temp_name)
            finally:
                directory.close()

    def test_drive_folder_accepts_google_drive_symlink_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            home.mkdir()
            account = root / "real-account"
            my_drive = account / "My Drive"
            my_drive.mkdir(parents=True)
            (home / "Google Drive").symlink_to(account, target_is_directory=True)
            outside = root / "outside"
            outside.mkdir()
            with mock.patch.object(Path, "home", return_value=home):
                dest = sdc.resolve_dest(None, "跑步成片/slug/chunks")
                self.assertEqual(dest, my_drive / "跑步成片" / "slug" / "chunks")
                self.assertIn(my_drive, dest.parents)
                self.assertNotIn("Google Drive", dest.parts)
                with self.assertRaisesRegex(SystemExit, "must not contain"):
                    sdc.resolve_dest(None, "../outside")
                with self.assertRaisesRegex(SystemExit, "must not contain"):
                    sdc.resolve_dest(None, "跑步成片/../../outside")
                (my_drive / "escape").symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    sdc.resolve_dest(None, "escape/chunks")

            cloud_home = root / "cloud-home"
            cloud_home.mkdir()
            cloud_account = root / "cloud-account"
            (cloud_account / "My Drive").mkdir(parents=True)
            mount = cloud_home / "Library" / "CloudStorage"
            mount.mkdir(parents=True)
            (mount / "GoogleDrive-user").symlink_to(cloud_account, target_is_directory=True)
            (cloud_home / "Google Drive").symlink_to(cloud_account, target_is_directory=True)
            with mock.patch.object(Path, "home", return_value=cloud_home):
                roots = sdc.find_drive_roots()
                self.assertEqual(roots, [cloud_account / "My Drive"])
                cloud_dest = sdc.resolve_dest(None, "chunks")
            self.assertEqual(cloud_dest, cloud_account / "My Drive" / "chunks")
            self.assertFalse(cloud_dest.is_symlink())

    def test_held_directory_fd_ignores_parent_symlink_swap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside"
            outside.mkdir()
            src = root / "source.bin"
            payload = b"0123456789"
            src.write_bytes(payload)
            work = root / "work"
            work.mkdir()
            real_open = sdc._open_dir
            swapped: dict[str, Path] = {}

            def swap_work(path: Path, label: str, *, create: bool = True) -> sdc._Dir:
                opened = real_open(path, label, create=create)
                if os.path.normpath(path) == os.path.normpath(work) and "work" not in swapped:
                    moved = root / "work.real"
                    os.rename(work, moved)
                    work.symlink_to(outside, target_is_directory=True)
                    swapped["work"] = moved
                return opened

            with mock.patch.object(sdc, "_open_dir", side_effect=swap_work):
                sdc.split_into_chunks(src, work, sdc.plan_chunks(len(payload), 10))
            self.assertEqual((swapped["work"] / "chunk-00").read_bytes(), payload)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertTrue(work.is_symlink())

            dest = root / "dest"
            dest.mkdir()
            copy_src = root / "copy-src.bin"
            copy_src.write_bytes(b"copied-ok")

            def swap_dest(path: Path, label: str, *, create: bool = True) -> sdc._Dir:
                opened = real_open(path, label, create=create)
                if os.path.normpath(path) == os.path.normpath(dest) and "dest" not in swapped:
                    moved = root / "dest.real"
                    os.rename(dest, moved)
                    dest.symlink_to(outside, target_is_directory=True)
                    swapped["dest"] = moved
                return opened

            with mock.patch.object(sdc, "_open_dir", side_effect=swap_dest):
                sdc.copy_one(copy_src, dest / "chunk-00")
            self.assertEqual((swapped["dest"] / "chunk-00").read_bytes(), b"copied-ok")
            self.assertEqual(list(outside.iterdir()), [])

    def test_failed_republish_does_not_leave_mixed_generation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.bin"
            work = root / "work"
            old = b"aaaaaaaaaa"
            new = b"bbbbbbbbbb"
            src.write_bytes(old)
            argv = ["--src", str(src), "--work-dir", str(work), "--split-only", "--chunk-bytes", "5"]
            self.assertEqual(sdc.main(argv), 0)
            old_manifest = (work / sdc.MANIFEST_NAME).read_text(encoding="utf-8")
            old_hash = (work / sdc.HASH_NAME).read_text(encoding="utf-8")
            self.assertEqual((work / "chunk-00").read_bytes(), b"aaaaa")
            self.assertEqual((work / "chunk-01").read_bytes(), b"aaaaa")

            src.write_bytes(new)
            real_install = sdc._install_new_file

            def fail_second_chunk(directory: sdc._Dir, temp_name: str, final_name: str) -> None:
                if final_name == "chunk-01":
                    self.assertEqual((work / "chunk-00").read_bytes(), b"bbbbb")
                    raise OSError("simulated publish failure")
                real_install(directory, temp_name, final_name)

            with mock.patch.object(sdc, "_install_new_file", side_effect=fail_second_chunk):
                with self.assertRaisesRegex(SystemExit, "simulated publish failure"):
                    sdc.main(argv)
            self.assertEqual((work / "chunk-00").read_bytes(), b"aaaaa")
            self.assertEqual((work / "chunk-01").read_bytes(), b"aaaaa")
            self.assertEqual((work / sdc.MANIFEST_NAME).read_text(encoding="utf-8"), old_manifest)
            self.assertEqual((work / sdc.HASH_NAME).read_text(encoding="utf-8"), old_hash)
            self.assertFalse(_staged_leftovers(work))
            self.assertNotIn(hashlib.sha256(new).hexdigest(), old_manifest)

            def fail_manifest(directory: sdc._Dir, temp_name: str, final_name: str) -> None:
                if final_name == sdc.MANIFEST_NAME:
                    self.assertEqual((work / "chunk-00").read_bytes(), b"bbbbb")
                    self.assertEqual((work / "chunk-01").read_bytes(), b"bbbbb")
                    raise OSError("simulated publish failure")
                real_install(directory, temp_name, final_name)

            with mock.patch.object(sdc, "_install_new_file", side_effect=fail_manifest):
                with self.assertRaisesRegex(SystemExit, "simulated publish failure"):
                    sdc.main(argv)
            self.assertEqual((work / "chunk-00").read_bytes(), b"aaaaa")
            self.assertEqual((work / "chunk-01").read_bytes(), b"aaaaa")
            self.assertEqual((work / sdc.MANIFEST_NAME).read_text(encoding="utf-8"), old_manifest)
            self.assertEqual((work / sdc.HASH_NAME).read_text(encoding="utf-8"), old_hash)
            self.assertFalse(_staged_leftovers(work))

    def test_split_only_rejects_dest_and_drive_folder_together(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "source.bin"
            src.write_bytes(b"source")
            with self.assertRaisesRegex(SystemExit, "only one"):
                sdc.main([
                    "--src", str(src),
                    "--split-only",
                    "--dest", str(Path(td) / "dest"),
                    "--drive-folder", "跑步成片/chunks",
                ])
            self.assertFalse((Path(td) / "yt-drive-chunks").exists())

    def test_resolve_dest_rejects_escape_relative_and_symlink_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "drive-root"
            root.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()
            with mock.patch.object(sdc, "find_drive_roots", return_value=[root]):
                with self.assertRaisesRegex(SystemExit, "must not contain"):
                    sdc.resolve_dest(None, "../outside")
                with self.assertRaisesRegex(SystemExit, "absolute path"):
                    sdc.resolve_dest(Path("relative-dest"), None)
                (root / "link").symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    sdc.resolve_dest(None, "link/chunks")

    def test_main_reports_destination_file_and_rejects_newline_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.bin"
            src.write_bytes(b"source")
            dest_file = root / "not-a-directory"
            dest_file.write_bytes(b"x")
            with self.assertRaisesRegex(SystemExit, "destination is not a directory"):
                sdc.main([
                    "--src", str(src),
                    "--work-dir", str(root / "work"),
                    "--dest", str(dest_file),
                ])

            newline_src = root / "bad\nname.bin"
            newline_src.write_bytes(b"source")
            with self.assertRaisesRegex(SystemExit, "newline"):
                sdc.main(["--src", str(newline_src), "--split-only"])

    def test_source_change_during_split_fails_before_publishing_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.bin"
            work = root / "work"
            src.write_bytes(b"0123456789abcdefghij")
            plan = sdc.plan_chunks(20, 10)
            original = sdc._write_chunk_bytes
            calls = 0

            def mutate_after_first(inf, out, size, digest, chunk_digest=None):
                nonlocal calls
                result = original(inf, out, size, digest, chunk_digest)
                calls += 1
                if calls == 1:
                    src.write_bytes(b"Z" * 20)
                return result

            with mock.patch.object(sdc, "_write_chunk_bytes", side_effect=mutate_after_first):
                with self.assertRaisesRegex(ValueError, "source changed"):
                    sdc.split_into_chunks(src, work, plan)
            self.assertFalse((work / "chunk-00").exists())
            self.assertFalse(list(work.glob("*.partial*")))

    def test_reassembled_chunks_match_source_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source with spaces.bin"
            data = b"a" * 17 + b"b" * 13
            src.write_bytes(data)
            plan = sdc.plan_chunks(len(data), 7)
            paths = sdc.split_into_chunks(src, root / "work", plan, sdc.sha256_file(src))
            rebuilt = b"".join(path.read_bytes() for path in paths)
            self.assertEqual(hashlib.sha256(rebuilt).hexdigest(), sdc.sha256_file(src))


if __name__ == "__main__":
    unittest.main()
