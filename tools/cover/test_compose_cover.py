#!/usr/bin/env python3
"""compose_cover 自测：抠图前字号快速预检 + 人像抠图缓存复用。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "cover"))

import compose_cover as cc  # noqa: E402


class ComposeCoverTest(unittest.TestCase):
    def test_precheck_title_fails_before_cutout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            selfie = root / "selfie.jpg"
            bg = root / "bg.jpg"
            Image.new("RGB", (400, 600), (120, 80, 60)).save(selfie)
            Image.new("RGB", (1920, 1440), (20, 20, 20)).save(bg)
            args = SimpleNamespace(
                person=str(selfie),
                bg=str(bg),
                title="这是一行绝对放不下的超长封面主标题测试|第二行",
                series="破三实验室",
                out_dir=str(root),
                side="right",
                font=str(cc.DEFAULT_FONT),
                stroke_frac=0.018,
                title_color="255,255,255",
                prefix="",
            )
            with patch.object(cc, "load_person", side_effect=AssertionError("should fail before cutout")):
                with self.assertRaises(SystemExit) as ctx:
                    cc._compose(args)
            self.assertIn("放不下", str(ctx.exception))
            self.assertFalse((root / "cover-work").exists())

    def test_load_person_caches_cutout_and_invalidates_on_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "cover-work"
            selfie = root / "selfie.jpg"
            Image.new("RGB", (120, 180), (100, 120, 140)).save(selfie)

            cut_rgba = Image.new("RGBA", (120, 180), (0, 0, 0, 0))
            for x in range(30, 90):
                for y in range(20, 160):
                    cut_rgba.putpixel((x, y), (200, 180, 160, 255))

            calls = 0

            def fake_u2net(_im):
                nonlocal calls
                calls += 1
                return cut_rgba.copy()

            # 屏蔽 rembg 走 u2net 桩函数，验证只抠一次、二次走缓存、改图后失效重抠
            with patch.dict(sys.modules, {"rembg": None}), patch.object(cc, "u2net_cutout", side_effect=fake_u2net):
                im1 = cc.load_person(selfie, cache_dir=cache)
                self.assertEqual(calls, 1)
                self.assertEqual(im1.mode, "RGBA")
                self.assertTrue((cache / "person-cutout.png").is_file())

                im2 = cc.load_person(selfie, cache_dir=cache)
                self.assertEqual(calls, 1)
                self.assertEqual(im2.mode, "RGBA")

                # 缓存 PNG 损坏时自动回退重抠，不崩
                (cache / "person-cutout.png").write_bytes(b"corrupted-not-a-png")
                cc.load_person(selfie, cache_dir=cache)
                self.assertEqual(calls, 2)

                # 换一张不同尺寸的新自拍，缓存失效重新抠
                Image.new("RGB", (140, 200), (50, 60, 70)).save(selfie)
                cc.load_person(selfie, cache_dir=cache)
                self.assertEqual(calls, 3)


if __name__ == "__main__":
    unittest.main()
