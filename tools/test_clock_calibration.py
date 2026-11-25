#!/usr/bin/env python3
"""相机时钟校准、高驰开表提示音检测、任意片段跨开表刻自动切分 HUD 单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "hud"))
sys.path.insert(0, str(TOOLS_DIR / "assemble"))

import detect_watch_beep as beep  # noqa: E402
import final_export as fe  # noqa: E402
import program_edl as edl  # noqa: E402
import render_running_hud as hud  # noqa: E402


class ClockCalibrationTest(unittest.TestCase):
    def test_classify_multi_open_clips(self) -> None:
        self.assertEqual(edl.classify_clip("raw/2026-11-25-open.mp4"), "cold_open")
        self.assertEqual(edl.classify_clip("raw/2026-11-25-open-1.mp4"), "cold_open")
        self.assertEqual(edl.classify_clip("raw/2026-11-25-open-2.mp4"), "cold_open")
        self.assertEqual(edl.classify_clip("raw/2026-11-25-open-a.mp4"), "cold_open")
        self.assertEqual(edl.classify_clip("2026-11-25-open-raw.mp4"), "cold_open")
        with self.assertRaises(ValueError):
            edl.classify_clip("2026-11-25-pre-coldopen.mp4")

    def test_calibrate_from_open_splits_hud_at_fit_start_without_transition(self) -> None:
        table = edl.empty_program("2026-11-25-demo")
        # 模拟相机时钟比 FIT 慢 16.29s：
        # open 原片 108.64s，未校准时 offset_s = -120.63s；开表在原片 104.34s 处
        # run-a 未校准时 offset_s = 100.0s
        edl.set_source_sync(
            table,
            [
                {"clip": "raw/2026-11-25-open.mp4", "fit": "data/2026-11-25-run-data.fit", "offset_s": -120.63, "fit_duration_s": 5500.0},
                {"clip": "raw/2026-11-25-run-a.mp4", "fit": "data/2026-11-25-run-data.fit", "offset_s": 100.0, "fit_duration_s": 5500.0},
                {"clip": "raw/2026-11-25-close.mp4", "fit": "data/2026-11-25-run-data.fit", "offset_s": 5600.0, "fit_duration_s": 5500.0},
            ],
        )
        edl.upsert_keeps(
            table,
            [
                {"clip": "raw/2026-11-25-open.mp4", "src_start_s": 0.0, "src_end_s": 108.64},
                {"clip": "raw/2026-11-25-run-a.mp4", "src_start_s": 0.0, "src_end_s": 30.0},
                {"clip": "raw/2026-11-25-close.mp4", "src_start_s": 0.0, "src_end_s": 10.0},
            ],
        )
        edl.record_hud(table, shoe_name="Plaid", shoe_km_after=100.0, weather_city="shanghai")

        # 校准前：open 整段在 FIT 开始之前，无 HUD
        open_before = [s for s in table["program"] if s["clip"] == "raw/2026-11-25-open.mp4"]
        self.assertEqual(len(open_before), 1)
        self.assertFalse(open_before[0]["hud"])

        # 校准：open 的 104.34s 对齐 FIT_start (0s)
        edl.calibrate_clock_from_clip(table, "raw/2026-11-25-open.mp4", 104.34, source="beep")
        self.assertAlmostEqual(edl.clock_offset(table), 16.29, places=3)
        self.assertAlmostEqual(edl.fit_time(table, "raw/2026-11-25-open.mp4", 104.34), 0.0, places=3)
        self.assertAlmostEqual(edl.fit_time(table, "raw/2026-11-25-run-a.mp4", 0.0), 116.29, places=3)

        # open 自动切为两段：0..104.34 无 HUD，104.34..108.64 有 HUD
        open_after = [s for s in table["program"] if s["clip"] == "raw/2026-11-25-open.mp4"]
        self.assertEqual(len(open_after), 2)
        self.assertFalse(open_after[0]["hud"])
        self.assertAlmostEqual(open_after[0]["src_start_s"], 0.0)
        self.assertAlmostEqual(open_after[0]["src_end_s"], 104.34, places=3)
        self.assertTrue(open_after[1]["hud"])
        self.assertAlmostEqual(open_after[1]["src_start_s"], 104.34, places=3)
        self.assertAlmostEqual(open_after[1]["src_end_s"], 108.64, places=3)
        # 同一原片切开点无 xfade、无 wind，成片时间严丝合缝
        self.assertAlmostEqual(open_after[1]["program_start_s"], 104.34, places=3)
        self.assertFalse(any(tr["before_id"] == open_after[1]["id"] for tr in table["transitions"]))
        # close 保持无 HUD
        close_segs = [s for s in table["program"] if s["type"] == "close"]
        self.assertTrue(all(not s["hud"] for s in close_segs))
        # validate 通过且未把字幕标过期（总时长不变）
        self.assertEqual(edl.validate(table), [])
        self.assertFalse(table["subs_stale"])

        # HUD jobs 包含 open 后半段 + run-a
        jobs = edl.hud_jobs(table)
        self.assertEqual([j["clip"] for j in jobs], ["raw/2026-11-25-open.mp4", "raw/2026-11-25-run-a.mp4"])
        self.assertAlmostEqual(jobs[0]["src_start_s"], 104.333333, places=3)

        # final_export 的 acts & openings 自动把 open 的无/有 HUD 两段拆开
        timeline = edl.frame_timeline(table, 30)
        wind_ids = {str(item["before_id"]) for item in edl.wind_transitions(table)}
        acts = fe._program_acts(timeline, wind_ids)
        self.assertEqual(acts, [(0,), (1,), (2,), (3,)])
        openings = fe.program_openings(timeline, wind_ids)
        self.assertEqual(len(openings), 4)

        # 二次重校准（幂等，不累加旧误差）
        edl.calibrate_clock_from_clip(table, "raw/2026-11-25-open.mp4", 104.50, source="manual")
        self.assertAlmostEqual(edl.clock_offset(table), 16.13, places=3)
        self.assertAlmostEqual(edl.fit_time(table, "raw/2026-11-25-open.mp4", 104.50), 0.0, places=3)
        self.assertEqual(edl.validate(table), [])

    def test_multi_open_and_run_straddling_fit_start(self) -> None:
        table = edl.empty_program("2026-11-25-multi")
        edl.set_source_sync(
            table,
            [
                {"clip": "raw/2026-11-25-open-1.mp4", "fit": "data/run.fit", "offset_s": -60.0, "fit_duration_s": 600.0},
                {"clip": "raw/2026-11-25-open-2.mp4", "fit": "data/run.fit", "offset_s": -10.0, "fit_duration_s": 600.0},
                {"clip": "raw/2026-11-25-run-a.mp4", "fit": "data/run.fit", "offset_s": -5.0, "fit_duration_s": 600.0},
            ],
        )
        edl.upsert_keeps(
            table,
            [
                {"clip": "raw/2026-11-25-open-1.mp4", "src_start_s": 0.0, "src_end_s": 20.0},
                {"clip": "raw/2026-11-25-open-2.mp4", "src_start_s": 0.0, "src_end_s": 18.0},
                {"clip": "raw/2026-11-25-run-a.mp4", "src_start_s": 0.0, "src_end_s": 30.0},
            ],
        )
        edl.record_hud(table, shoe_name="Plaid", shoe_km_after=50.0, weather_city="shanghai")
        self.assertEqual(edl.validate(table), [])
        summary = [(s["clip"], round(s["src_start_s"], 2), round(s["src_end_s"], 2), s["hud"]) for s in table["program"]]
        self.assertEqual(
            summary,
            [
                ("raw/2026-11-25-open-1.mp4", 0.0, 20.0, False),
                ("raw/2026-11-25-open-2.mp4", 0.0, 10.0, False),
                ("raw/2026-11-25-open-2.mp4", 10.0, 18.0, True),
                ("raw/2026-11-25-run-a.mp4", 0.0, 5.0, False),
                ("raw/2026-11-25-run-a.mp4", 5.0, 30.0, True),
            ],
        )

    def test_hud_signature_and_argv_include_clock_offset(self) -> None:
        table = edl.empty_program("2026-11-25-sig")
        edl.set_source_sync(table, [{"clip": "raw/2026-11-25-run-a.mp4", "fit": "data/run.fit", "offset_s": 10.0}])
        edl.upsert_keeps(table, [{"clip": "raw/2026-11-25-run-a.mp4", "src_start_s": 0.0, "src_end_s": 20.0}])
        edl.record_hud(table, shoe_name="Plaid", shoe_km_after=50.0, weather_city="shanghai")

        sig0 = hud.hud_signature(table)
        self.assertEqual(sig0["clock_offset_s"], 0.0)
        edl.calibrate_clock(table, clock_offset_s=16.29)
        sig1 = hud.hud_signature(table)
        self.assertEqual(sig1["clock_offset_s"], 16.29)
        self.assertNotEqual(sig0, sig1)

        argv = hud.overlay_render_argv(
            render_dir=Path("/tmp/m"),
            clips=["raw/2026-11-25-run-a.mp4"],
            output_dir=Path("/tmp/m/hud-renders/qtrle"),
            fit=Path("/tmp/m/data/run.fit"),
            hud=table["hud"],
            weather=Path("/tmp/m/nonexistent.json"),
            profile="qtrle",
            jobs=2,
            clock_offset_s=16.29,
        )
        self.assertIn("--clock-offset", argv)
        idx = argv.index("--clock-offset")
        self.assertAlmostEqual(float(argv[idx + 1]), 16.29, places=3)

        cmd = hud.hud_overlay_command(
            gopro_python=Path("/venv/bin/python"),
            gopro_dashboard=Path("/repo/tools/hud/gopro_dashboard_wrap.py"),
            clip=Path("/tmp/m/raw/2026-11-25-run-a.mp4"),
            out=Path("/tmp/m/hud-renders/qtrle/out.mov"),
            font=Path("/repo/font.otf"),
            fit=Path("/tmp/m/data/run.fit"),
            template=Path("/tmp/t.xml"),
            cache_dir=Path("/tmp/c"),
            video_end_time_mode="file-modified",
            overlay_profile="qtrle",
            shoe_name="Plaid",
            shoe_total_km_after_run=50.0,
            clock_offset_s=16.29,
        )
        self.assertIn("--clock-offset", cmd)

    def test_detect_synthetic_coros_two_tone_beep(self) -> None:
        sr = beep.SAMPLE_RATE
        rng = np.random.default_rng(42)
        dur_s = 3.0
        t = np.arange(int(sr * dur_s), dtype=np.float32) / sr
        # 背景噪声 + 两个类似 COROS 开表的 70ms 窄带纯音（1.50s 和 1.63s）
        sig = (0.01 * rng.standard_normal(len(t))).astype(np.float32)
        m1 = (t >= 1.50) & (t < 1.57)
        m2 = (t >= 1.63) & (t < 1.70)
        sig[m1] += 0.25 * np.sin(2 * np.pi * 7734.0 * t[m1]).astype(np.float32)
        sig[m2] += 0.15 * np.sin(2 * np.pi * 5789.0 * t[m2]).astype(np.float32)

        events = beep.detect_beeps_from_pcm(sig, sample_rate=sr, offset_s=100.0)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["note_count"], 2)
        self.assertAlmostEqual(ev["start_s"], 101.50, delta=0.05)
        self.assertAlmostEqual(ev["peak_freq_hz"], 7734.0, delta=30.0)

    def test_parse_timecode_and_offset_guard(self) -> None:
        self.assertAlmostEqual(beep.parse_timecode("104.35"), 104.35)
        self.assertAlmostEqual(beep.parse_timecode("1:44"), 104.0)
        self.assertAlmostEqual(beep.parse_timecode("1:44.5"), 104.5)
        self.assertAlmostEqual(beep.parse_timecode("0:01:44.5"), 104.5)
        for bad in ("", "-5", "1:60", "1:2:3:4"):
            with self.assertRaises(ValueError):
                beep.parse_timecode(bad)

        # 跑中倒计时（反推偏移 -900s）绝不能被当成开表音推荐
        countdown_only = [
            {"start_s": 12.0, "note_count": 4, "implied_clock_offset_s": -900.0},
        ]
        self.assertIsNone(beep.pick_start_beep(countdown_only, max_offset_s=120.0))

        # 合法开表音 + 离谱跑中音：只挑合法的
        mixed = [
            {"start_s": 104.3, "note_count": 2, "implied_clock_offset_s": 16.3},
            {"start_s": 500.0, "note_count": 4, "implied_clock_offset_s": -380.0},
        ]
        self.assertEqual(beep.pick_start_beep(mixed, max_offset_s=120.0), mixed[0])

    def test_export_alphas_manifest_invalidates_reuse_on_clock_offset_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            (media / "raw").mkdir()
            (media / "data").mkdir()
            (media / "hud-renders" / "qtrle").mkdir(parents=True)
            (media / "raw" / "2026-11-25-run-a.mp4").write_bytes(b"v")
            (media / "data" / "2026-11-25-run-data.fit").write_bytes(b"f")

            table = edl.empty_program("2026-11-25-reuse")
            edl.set_source_sync(table, [{"clip": "raw/2026-11-25-run-a.mp4", "fit": "data/2026-11-25-run-data.fit", "offset_s": 10.0}])
            edl.upsert_keeps(table, [{"clip": "raw/2026-11-25-run-a.mp4", "src_start_s": 0.0, "src_end_s": 5.0}])
            edl.record_hud(table, shoe_name="Plaid", shoe_km_after=50.0, weather_city="shanghai")

            plans = hud.plan_alpha_jobs(media, table, {"raw/2026-11-25-run-a.mp4": 5.0})
            dest = plans[0]["dest"]
            dest.write_bytes(b"dummy-qtrle")
            hud.write_alpha_manifest(media, table, plans)
            self.assertTrue(hud.alphas_ready(media, table))

            # 改 clock_offset 后：manifest 不再匹配，alphas_ready 为 False
            edl.calibrate_clock(table, clock_offset_s=16.29)
            self.assertFalse(hud.alphas_ready(media, table))
            saved = json.loads(hud.hud_manifest_path(media).read_text(encoding="utf-8"))
            self.assertEqual(saved["signature"]["clock_offset_s"], 0.0)


if __name__ == "__main__":
    unittest.main()
