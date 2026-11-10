#!/usr/bin/env python3
"""只用临时目录和小字节文件测试分块、复制及路径安全边界。"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import stage_drive_chunks as sdc


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

            def race(temp: Path, destination: Path) -> None:
                if not temp.exists():
                    raise AssertionError("temporary file was not created")
                destination.write_bytes(b"raced!")
                raise FileExistsError(destination)

            with mock.patch.object(sdc, "_publish_noreplace", side_effect=race):
                with self.assertRaisesRegex(FileExistsError, "appeared during copy"):
                    sdc.copy_one(src, target)
            self.assertEqual(target.read_bytes(), b"raced!")
            self.assertFalse(list(dest.glob("*.partial*")))

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
