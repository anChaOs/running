#!/usr/bin/env python3
"""tmpdir pack 自测：成片 move、小文件硬链、无大文件副本。"""

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

    def _seed(self, media: Path, title_name: str = "凉快就能更接近破三？.mp4") -> Path:
        title = self._touch(media / title_name, b"video")
        for name in pu.COVERS:
            self._touch(media / name, b"jpg-" + name.encode())
        self._touch(media / "subtitles.srt", b"1\n")
        return title

    def test_pack_moves_mp4_hardlinks_small(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            title = self._seed(media)
            title_name = title.name
            title_ino = os.stat(title).st_ino
            # noise
            self._touch(media / "2026-01-01-run-final.mp4", b"old")
            self._touch(media / "2026-01-01-open-raw.mp4", b"raw")
            self._touch(media / "subtitles.ass", b"[Script]")

            out = pu.pack(media)
            self.assertEqual(out, (media / "upload").resolve())
            dst = out / title_name
            self.assertTrue(dst.is_file())
            self.assertFalse((media / title_name).exists(), "root must not keep titled mp4")
            self.assertEqual(os.stat(dst).st_ino, title_ino)

            for name in [*pu.COVERS, "subtitles.srt"]:
                self.assertTrue((out / name).is_file(), name)
                self.assertTrue((media / name).is_file(), name)
                self.assertEqual(os.stat(media / name).st_ino, os.stat(out / name).st_ino, name)

            self.assertFalse((out / "subtitles.ass").exists())
            self.assertFalse((out / "2026-01-01-run-final.mp4").exists())

    def test_refresh_replaces_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            self._seed(media, "标题.mp4")
            pu.pack(media)
            # 新成片出现在根目录，再 pack 应替换 upload/ 并清空根
            title = media / "标题.mp4"
            self._touch(title, b"v2")
            pu.pack(media)
            dst = media / "upload" / "标题.mp4"
            self.assertEqual(dst.read_bytes(), b"v2")
            self.assertFalse(title.exists())

    def test_idempotent_already_in_upload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            self._seed(media, "标题.mp4")
            pu.pack(media)
            ino = os.stat(media / "upload" / "标题.mp4").st_ino
            pu.pack(media)
            self.assertFalse((media / "标题.mp4").exists())
            self.assertEqual(os.stat(media / "upload" / "标题.mp4").st_ino, ino)

    def test_drops_root_hardlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            title = self._seed(media, "标题.mp4")
            upload = media / "upload"
            upload.mkdir()
            os.link(title, upload / "标题.mp4")
            self.assertEqual(os.stat(title).st_nlink, 2)
            pu.pack(media)
            self.assertFalse(title.exists())
            self.assertTrue((upload / "标题.mp4").is_file())
            self.assertEqual(os.stat(upload / "标题.mp4").st_nlink, 1)

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
            self._seed(media, "今天体感不错？.mp4")
            self.assertEqual(pu.find_title_mp4(media).name, "今天体感不错？.mp4")


if __name__ == "__main__":
    unittest.main()
