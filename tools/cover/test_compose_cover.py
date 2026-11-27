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

    def test_multiline_styles_differ_in_size_and_color(self) -> None:
        gold = cc.resolve_focal_color((255, 255, 255))
        self.assertEqual(gold[:3], cc.FOCAL_RGB)
        question = cc.title_styles(["凉快就能", "更接近破三？"], gold)
        self.assertFalse(question[0].focal)
        self.assertTrue(question[1].focal)
        self.assertGreater(question[1].scale, question[0].scale)
        self.assertNotEqual(question[0].fill[:3], question[1].fill[:3])

        hook = cc.title_styles(["80/20", "是什么？"], gold)
        self.assertTrue(hook[0].focal)
        self.assertGreater(hook[0].scale, hook[1].scale)

        three = cc.title_styles(["碳板鞋", "为什么", "更省力？"], gold)
        self.assertTrue(three[-1].focal)
        self.assertEqual(len({style.scale for style in three}), 3)
        self.assertEqual(len({style.fill[:3] for style in three}), 3)
        self.assertGreater(three[-1].track_em, three[0].track_em)

        custom = cc.title_styles(["湖边", "10km", "第二名？"], cc.resolve_focal_color((30, 144, 255)))
        self.assertTrue(custom[1].focal)
        self.assertEqual(custom[1].fill[:3], (30, 144, 255))
        self.assertNotEqual(custom[0].fill[:3], custom[1].fill[:3])
        self.assertNotEqual(custom[2].fill[:3], custom[1].fill[:3])

    def test_compose_keeps_person_extremities_and_hierarchy(self) -> None:
        person = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
        for y in range(180, 760):
            for x in range(140, 280):
                person.putpixel((x, y), (190, 150, 130, 255))
        hand = (255, 0, 140, 255)
        for y in range(24, 96):
            for x in range(300, 372):
                person.putpixel((x, y), hand)
        for y in range(680, 752):
            for x in range(36, 108):
                person.putpixel((x, y), hand)
        outlined = cc.outline(person, 0.018)
        bg = Image.new("RGB", (2400, 1800), (18, 28, 42))
        lines = ["碳板鞋", "为什么", "更省力？"]
        focal = cc.resolve_focal_color((255, 208, 48))
        for _name, W, H, layout in cc.FORMATS:
            img, size, _series, thumb, sizes = cc.compose(
                bg, outlined, lines, "破三实验室", cc.DEFAULT_FONT, W, H, layout, "right", focal
            )
            self.assertEqual(img.size, (W, H))
            self.assertEqual(sizes[sizes.index(max(sizes))], size)
            self.assertGreater(max(sizes), min(sizes))
            self.assertGreaterEqual(thumb, cc.THUMB_MIN_PX)
            markers = 0
            gold_bottom = 0
            hand_top = H
            step = 3
            for y in range(0, H, step):
                for x in range(0, W, step):
                    r, g, b = img.getpixel((x, y))
                    if r > 220 and g < 80 and b > 90:
                        markers += 1
                        hand_top = min(hand_top, y)
                    if r > 230 and 150 < g < 230 and b < 80:
                        gold_bottom = max(gold_bottom, y)
            self.assertGreater(markers, 8, layout)
            if layout == "portrait":
                self.assertLess(gold_bottom, hand_top, "portrait title must stay above the raised hand")


if __name__ == "__main__":
    unittest.main()
