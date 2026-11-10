#!/usr/bin/env python3
"""tmpdir tests for stage_drive_chunks: split, manifest, skip, no overwrite."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import stage_drive_chunks as sdc


class StageDriveChunksTest(unittest.TestCase):
    def test_plan_chunks_last_remainder(self) -> None:
        plan = sdc.plan_chunks(321_478_7178, 99_000_000)
        self.assertEqual(len(plan), 33)
        self.assertEqual(plan[0], ("chunk-00", 0, 99_000_000))
        self.assertEqual(plan[-1], ("chunk-32", 32 * 99_000_000, 46_787_178))
        self.assertEqual(sum(size for _n, _o, size in plan), 3_214_787_178)

    def test_plan_chunks_width_stays_two_until_100(self) -> None:
        plan = sdc.plan_chunks(99_000_000 * 10, 99_000_000)
        self.assertEqual(plan[0][0], "chunk-00")
        self.assertEqual(plan[-1][0], "chunk-09")

    def test_split_manifest_and_skip_existing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "final.mp4"
            data = b"abcdefghijklmnopqrstuvwxyz012345"
            src.write_bytes(data)
            work = root / "yt-drive-chunks"
            plan = sdc.plan_chunks(len(data), 10)
            digest = sdc.sha256_file(src)
            paths = sdc.split_into_chunks(src, work, plan)
            self.assertEqual(len(paths), 4)
            self.assertEqual(paths[0].read_bytes(), data[:10])
            self.assertEqual(paths[-1].read_bytes(), data[30:])
            sdc.write_manifest(work / sdc.MANIFEST_NAME, plan, len(data), digest, src)
            sdc.write_sha256_file(work / sdc.HASH_NAME, digest, src)
            manifest = (work / sdc.MANIFEST_NAME).read_text(encoding="utf-8")
            self.assertIn(f"chunk-00 10\n", manifest)
            self.assertIn(f"TOTAL {len(data)}\n", manifest)
            self.assertIn(f"SHA256 {digest}  {src}\n", manifest)
            self.assertEqual((work / sdc.HASH_NAME).read_text(encoding="utf-8"), f"{digest}  {src}\n")

            # existing correct-size chunk is reused
            first = work / "chunk-00"
            mtime = first.stat().st_mtime_ns
            again = sdc.split_into_chunks(src, work, plan)
            self.assertEqual(again[0].stat().st_mtime_ns, mtime)

    def test_copy_skips_same_size_and_refuses_mismatch(self) -> None:
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
            self.assertEqual(dest_ok.read_bytes(), b"x" * 10)

            dest_bad = dest / "chunk-01"
            other = work / "chunk-01"
            other.write_bytes(b"y" * 10)
            dest_bad.write_bytes(b"z" * 3)
            with self.assertRaises(FileExistsError):
                sdc.copy_one(other, dest_bad)
            self.assertEqual(dest_bad.read_bytes(), b"z" * 3)
            self.assertFalse((dest / "chunk-01.partial").exists())

    def test_copy_missing_writes_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = root / "work"
            dest = root / "drive-chunks"
            work.mkdir()
            src = work / "chunk-02"
            src.write_bytes(b"hello-chunk")
            lines = sdc.copy_missing([src], dest, jobs=2)
            self.assertTrue((dest / "chunk-02").is_file())
            self.assertEqual((dest / "chunk-02").read_bytes(), b"hello-chunk")
            self.assertTrue(any(line.startswith("copy chunk-02") for line in lines))


if __name__ == "__main__":
    unittest.main()
