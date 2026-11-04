#!/usr/bin/env python3
"""tmpdir 硬链打包自测。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pack_upload as pu


class PackUploadTest(unittest.TestCase):
    def _touch(self, path: Path, data: bytes = b"x") -> Path:
        path.write_bytes(data)
        return path

    def test_pack_hardlink_five(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            title = self._touch(media / "凉快就能更接近破三？.mp4", b"video")
            for name in pu.COVERS:
                self._touch(media / name, b"jpg-" + name.encode())
            self._touch(media / "subtitles.srt", b"1\n")
            # noise that must not be packed / must not confuse detect
            self._touch(media / "2026-01-01-run-final.mp4", b"old")
            self._touch(media / "2026-01-01-open-raw.mp4", b"raw")
            self._touch(media / "subtitles.ass", b"[Script]")

            out = pu.pack(media)
            self.assertEqual(out, (media / "upload").resolve())
            expected = [title.name, *pu.COVERS, "subtitles.srt"]
            for name in expected:
                dst = out / name
                self.assertTrue(dst.is_file(), name)
                self.assertEqual(os.stat(media / name).st_ino, os.stat(dst).st_ino, name)

            self.assertFalse((out / "subtitles.ass").exists())
            self.assertFalse((out / "2026-01-01-run-final.mp4").exists())

    def test_refresh_replaces_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            title = media / "标题.mp4"
            self._touch(title, b"v1")
            for name in pu.COVERS:
                self._touch(media / name, b"c1")
            self._touch(media / "subtitles.srt", b"s1")
            pu.pack(media)
            # 换 inode（模拟重新导出同名成片），再 pack 应刷新 upload/
            title.unlink()
            self._touch(title, b"v2")
            pu.pack(media)
            dst = media / "upload" / "标题.mp4"
            self.assertEqual(dst.read_bytes(), b"v2")
            self.assertEqual(os.stat(title).st_ino, os.stat(dst).st_ino)

    def test_missing_cover_exits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            self._touch(media / "标题.mp4")
            self._touch(media / "subtitles.srt")
            with self.assertRaises(SystemExit):
                pu.pack(media)

    def test_exclude_run_and_detect_title(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            self.assertTrue(pu.is_excluded_mp4("2026-11-04-run-final.mp4"))
            self.assertTrue(pu.is_excluded_mp4("x-no-burn.mp4"))
            self.assertTrue(pu.is_excluded_mp4("2026-11-04-close-raw.mp4"))
            self.assertFalse(pu.is_excluded_mp4("今天体感不错？.mp4"))
            self._touch(media / "今天体感不错？.mp4")
            for name in pu.COVERS:
                self._touch(media / name)
            self._touch(media / "subtitles.srt")
            self.assertEqual(pu.find_title_mp4(media).name, "今天体感不错？.mp4")


if __name__ == "__main__":
    unittest.main()
