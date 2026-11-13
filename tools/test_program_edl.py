#!/usr/bin/env python3
"""时间表的两套时钟、预览/导出同一张表、todo 门闩。不依赖媒体盘。

有 ffmpeg 时再用合成片确认 close 没被 xfade 丢掉。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import program_edl as edl
import todo_list as todo


def _ready() -> dict:
    table = edl.empty_program("2026-01-02-demo")
    edl.set_source_sync(
        table,
        [
            {"clip": "2026-01-02-run-a.mp4", "fit": "2026-01-02-run-data.fit", "offset_s": 30.0},
            {"clip": "2026-01-02-run-b.mp4", "fit": "2026-01-02-run-data.fit", "offset_s": 90.0},
        ],
    )
    edl.upsert_keeps(
        table,
        [
            {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 8.0},
            {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 12.3},
            {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 6.0},
        ],
    )
    edl.record_hud(table, shoe_name="Fly", shoe_km_after=100.0, weather_city="shanghai")
    return table


class ClockTest(unittest.TestCase):
    def test_cold_open_does_not_shift_run_source(self) -> None:
        table = _ready()
        run = next(seg for seg in table["program"] if seg["type"] == "run")
        self.assertAlmostEqual(run["program_start_s"], 8.0 - edl.XFADE_S)
        self.assertEqual(edl.hud_source_time(table, run["program_start_s"]), ("2026-01-02-run-a.mp4", 0.0))
        # 成片第 10 秒不是原片第 10 秒，也不用成片时间查 FIT。
        clip, src = edl.hud_source_time(table, 10.0) or ("", 0.0)
        self.assertEqual(clip, "2026-01-02-run-a.mp4")
        self.assertAlmostEqual(src, 10.0 - run["program_start_s"])
        self.assertAlmostEqual(edl.fit_time(table, clip, src), 30.0 + src)
        self.assertIsNone(edl.hud_source_time(table, 0.0))

    def test_pause_cut_drops_source_seconds_and_keeps_hud_on_source_clock(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 5.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 8.0, "src_end_s": 12.0},
            ],
        )
        first, second = table["program"]
        self.assertEqual(second["program_start_s"], 5.0)
        self.assertEqual(edl.hud_source_time(table, 5.0), ("2026-01-02-run-a.mp4", 8.0))
        self.assertIsNone(edl.source_to_program(table, "2026-01-02-run-a.mp4", 6.0))
        self.assertAlmostEqual(edl.source_to_program(table, "2026-01-02-run-a.mp4", 8.0) or -1, 5.0)
        self.assertEqual(edl.fit_time(table, first["clip"], 0.0), 0.0)

    def test_insert_pushes_program_time_not_run_clock(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 4.0}])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 5.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 8.0, "src_end_s": 12.0},
            ],
        )
        edl.add_insert(
            table,
            {
                "id": "card",
                "clip": "card.mp4",
                "src_start_s": 0.0,
                "src_end_s": 4.0,
                "after_id": "2026-01-02-run-a-1",
            },
        )
        insert = next(seg for seg in table["program"] if seg["type"] == "insert")
        nxt = next(seg for seg in table["program"] if seg["id"] == "2026-01-02-run-a-2")
        self.assertFalse(insert["hud"])
        self.assertAlmostEqual(insert["program_start_s"], 5.0)
        self.assertAlmostEqual(nxt["program_start_s"], 9.0)
        self.assertEqual(edl.hud_source_time(table, nxt["program_start_s"]), ("2026-01-02-run-a.mp4", 8.0))
        self.assertAlmostEqual(edl.fit_time(table, "2026-01-02-run-a.mp4", 8.0), 12.0)
        self.assertIsNone(edl.hud_source_time(table, 5.0))

    def test_lead_from_run_uses_that_clips_source_time(self) -> None:
        table = _ready()
        edl.set_lead(
            table,
            {"clip": "2026-01-02-run-a.mp4", "src_start_s": 10.0, "src_end_s": 18.0, "hud": True},
        )
        lead = table["program"][0]
        self.assertEqual(lead["type"], "cold_open")
        self.assertEqual(edl.hud_source_time(table, 0.0), ("2026-01-02-run-a.mp4", 10.0))
        run = next(seg for seg in table["program"] if seg["type"] == "run")
        self.assertEqual(edl.hud_source_time(table, run["program_start_s"]), ("2026-01-02-run-a.mp4", 0.0))
        self.assertNotAlmostEqual(run["src_start_s"], run["program_start_s"])

    def test_preview_and_export_share_source_ranges(self) -> None:
        table = _ready()
        edl.add_overlay(table, {"asset": "stats.jpg", "program_start_s": 20.0, "program_end_s": 24.0, "role": "stats"})
        preview = edl.preview_actions(table)
        export = edl.export_slices(table)
        self.assertEqual(
            [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in preview],
            [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in export],
        )
        self.assertEqual([edl.frame_range(row["src_start_s"], row["src_end_s"]) for row in preview],
                         [edl.frame_range(row["src_start_s"], row["src_end_s"]) for row in export])
        self.assertTrue(all(row["mode"] == "copy" for row in preview))
        self.assertNotIn("49", " ".join(edl.light_video_args("hevc")))
        self.assertNotIn("prores", " ".join(edl.light_video_args("h264")))
        jobs = edl.hud_jobs(table)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["overlay_profile"], "qtrle")
        self.assertEqual(jobs[0]["src_start_s"], 0.0)
        self.assertEqual(jobs[0]["src_end_s"], 12.3)

    def test_partial_run_is_stream_copied(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 1.0, "src_end_s": 4.0},
            ],
        )
        actions = edl.preview_actions(table)
        self.assertEqual(actions[0]["mode"], "copy")
        self.assertNotEqual(actions[0]["reason"], "kept-range")

    def test_freeze_blocks_cuts_and_stales_subtitles(self) -> None:
        table = _ready()
        edl.freeze(table)
        with self.assertRaises(ValueError):
            edl.upsert_keeps(table, [{"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 3.0}])
        table["frozen"] = False
        edl.upsert_keeps(table, [{"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 3.0}])
        self.assertTrue(table["subs_stale"])
        self.assertTrue(edl.validate(table))

    def test_source_sync_stays_locked_after_layout(self) -> None:
        table = _ready()
        with self.assertRaises(ValueError):
            edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "other.fit", "offset_s": 1.0}])

    def test_kept_alpha_mtime_uses_source_end(self) -> None:
        # 原片结束 1000，时长 100，保留到第 40 秒 → mtime 应是 940，开始才落在原片第 20 秒（若从 20 裁到 40）。
        self.assertEqual(edl.kept_alpha_mtime(1000.0, 100.0, 40.0), 940.0)

    def test_roundtrip_and_validate(self) -> None:
        table = _ready()
        self.assertEqual(edl.validate(table), [])
        with tempfile.TemporaryDirectory() as td:
            edl.save(td, table)
            loaded = edl.load_media(td)
        self.assertEqual(edl.validate(loaded), [])
        self.assertAlmostEqual(edl.program_duration(loaded), 8 + 12.3 + 6 - 2 * edl.XFADE_S)

    def test_graphic_overlay_refuses_another_cuts_times(self) -> None:
        table = _ready()
        graphic = {
            "asset": "16week.jpg",
            "program_start_s": 10.0,
            "program_end_s": 12.0,
            "role": "graphic",
        }
        with self.assertRaises(ValueError) as missing:
            edl.add_overlay(table, graphic)
        self.assertIn("expect_duration", str(missing.exception))
        with self.assertRaises(ValueError) as wrong:
            edl.add_overlay(table, graphic, expect_duration_s=1152.6)
        self.assertIn("refusing", str(wrong.exception))
        edl.add_overlay(table, graphic, expect_duration_s=edl.program_duration(table))
        self.assertEqual(edl.validate(table), [])
        with tempfile.TemporaryDirectory() as td:
            edl.save(td, table)
            self.assertEqual(edl.validate(edl.load_media(td)), [])
        edl.upsert_keeps(table, [{"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 4.0}])
        problems = edl.validate(table)
        self.assertTrue(any("no longer matches" in item for item in problems))

    def test_published_cut_keeps_close_on_the_frame_grid(self) -> None:
        # 2026-11-12-8020 的七段时长。#90 里 close 被浮点 xfade 丢掉；新表只有冷开场和 close 做 0.2s。
        durations = [
            ("2026-11-12-open.mp4", 86.4),
            ("2026-11-12-run-a.mp4", 201.866667),
            ("2026-11-12-run-b.mp4", 111.8),
            ("2026-11-12-run-c.mp4", 113.4),
            ("2026-11-12-run-d.mp4", 116.333333),
            ("2026-11-12-run-e.mp4", 263.933333),
            ("2026-11-12-close.mp4", 259.266667),
        ]
        table = edl.empty_program("2026-11-12-8020")
        edl.set_source_sync(
            table,
            [
                {"clip": name, "fit": "2026-11-12-run-data.fit", "offset_s": 0.0}
                for name, _dur in durations
                if "-run-" in name
            ],
        )
        edl.upsert_keeps(
            table,
            [{"clip": name, "src_start_s": 0.0, "src_end_s": dur} for name, dur in durations],
        )
        timeline = edl.frame_timeline(table)
        self.assertEqual([seg["fade_frames"] for seg in timeline], [0, 6, 0, 0, 0, 0, 6])
        close = timeline[-1]
        self.assertEqual(close["program_start_frame"], 26800)
        self.assertEqual(close["frames"], 7778)
        self.assertEqual(close["program_start_frame"] + close["frames"], 34578)
        self.assertAlmostEqual(edl.frame_program_duration(table), 1152.6)
        self.assertLess(close["program_start_frame"], close["program_start_frame"] + close["fade_frames"])

    def test_short_open_cannot_xfade_away_the_next_segment(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 0.21},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 5.0},
                {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 5.0},
            ],
        )
        problems = edl.validate(table)
        self.assertTrue(any("refusing to drop" in item for item in problems))

    def test_wind_between_different_run_clips_does_not_shorten(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0},
                {"clip": "2026-01-02-run-b.mp4", "fit": "run.fit", "offset_s": 10.0},
            ],
        )
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 6.0},
                {"clip": "2026-01-02-run-b.mp4", "src_start_s": 0.0, "src_end_s": 5.0},
                {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 3.0},
            ],
        )
        winds = edl.wind_transitions(table)
        self.assertEqual(len(winds), 1)
        self.assertEqual(winds[0]["type"], "wind")
        self.assertEqual(winds[0]["before_id"], "2026-01-02-run-b-1")
        self.assertAlmostEqual(winds[0]["duration_s"], edl.WIND_S)
        run_b = next(seg for seg in table["program"] if seg["id"] == "2026-01-02-run-b-1")
        self.assertAlmostEqual(winds[0]["at_program_s"], run_b["program_start_s"])
        self.assertAlmostEqual(edl.program_duration(table), 4 + 6 + 5 + 3 - 2 * edl.XFADE_S)
        self.assertEqual(edl.validate(table), [])
        actions = edl.preview_actions(table)
        run_actions = [row for row in actions if row["type"] == "run"]
        self.assertTrue(all(row["trim_head_s"] == 0 and row["trim_tail_s"] == 0 for row in run_actions))

    def test_same_clip_keeps_and_inserts_do_not_get_wind(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0},
                {"clip": "2026-01-02-run-b.mp4", "fit": "run.fit", "offset_s": 8.0},
            ],
        )
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 3.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 4.0, "src_end_s": 6.0},
            ],
        )
        self.assertEqual(edl.wind_transitions(table), [])
        edl.add_insert(
            table,
            {
                "id": "card",
                "clip": "card.mp4",
                "src_start_s": 0.0,
                "src_end_s": 2.0,
                "after_id": "2026-01-02-run-a-1",
            },
        )
        self.assertEqual(edl.wind_transitions(table), [])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 3.0},
                {"clip": "2026-01-02-run-b.mp4", "src_start_s": 0.0, "src_end_s": 3.0},
            ],
        )
        edl.add_insert(
            table,
            {
                "id": "card",
                "clip": "card.mp4",
                "src_start_s": 0.0,
                "src_end_s": 2.0,
                "after_id": "2026-01-02-run-a-1",
                "transition": "wind",
            },
        )
        winds = edl.wind_transitions(table)
        self.assertEqual([item["before_id"] for item in winds], ["card"])
        self.assertFalse(any(item["type"] == "xfade" for item in table["transitions"]))
        card = next(seg for seg in table["program"] if seg["id"] == "card")
        nxt = next(seg for seg in table["program"] if seg["id"] == "2026-01-02-run-b-1")
        self.assertAlmostEqual(nxt["program_start_s"], card["program_start_s"] + 2.0)

    def test_close_stats_share_the_close_segment(self) -> None:
        table = _ready()
        edl.add_close_stats(table, ["stats-01.jpg", "stats-02.jpg"])
        close = next(seg for seg in table["program"] if seg["type"] == "close")
        stats = [ov for ov in table["overlays"] if ov.get("role") == "stats"]
        self.assertEqual(len(stats), 2)
        self.assertAlmostEqual(stats[0]["program_start_s"], close["program_start_s"])
        self.assertAlmostEqual(stats[-1]["program_end_s"], close["program_start_s"] + edl.seg_duration(close))
        self.assertEqual(edl.validate(table), [])

    def test_close_stats_span_sentence_cuts_on_close(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 10.0},
                {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 3.0},
                {"clip": "2026-01-02-close.mp4", "src_start_s": 4.0, "src_end_s": 8.0},
            ],
        )
        edl.record_hud(table, shoe_name="Fly", shoe_km_after=100.0, weather_city="shanghai")
        edl.add_close_stats(table, ["stats-01.jpg", "stats-02.jpg"])
        closes = [seg for seg in table["program"] if seg["type"] == "close"]
        self.assertEqual(len(closes), 2)
        stats = [ov for ov in table["overlays"] if ov.get("role") == "stats"]
        self.assertEqual(len(stats), 2)
        start = closes[0]["program_start_s"]
        end = closes[-1]["program_start_s"] + edl.seg_duration(closes[-1])
        self.assertAlmostEqual(end - start, 7.0)
        self.assertAlmostEqual(stats[0]["program_start_s"], start)
        self.assertAlmostEqual(stats[0]["program_end_s"], start + 3.5)
        self.assertAlmostEqual(stats[-1]["program_start_s"], start + 3.5)
        self.assertAlmostEqual(stats[-1]["program_end_s"], end)
        self.assertEqual(edl.validate(table), [])


class SameTableTest(unittest.TestCase):
    def test_preview_commands_stay_light_and_export_burns(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import final_export
        import preview_episode

        table = _ready()
        edl.freeze(table)
        graph = final_export.build_program_filter(table, ["full"], 0, Path("/tmp/cues.ass"))
        self.assertGreaterEqual(graph.count("trim=start=0.000000:end=12.300000"), 2)
        self.assertIn("subtitles=", graph)
        self.assertIn("loudnorm", graph)
        self.assertIn("xfade=", graph)
        actions = edl.preview_actions(table)
        sources = {row["clip"]: Path("/media") / row["clip"] for row in actions}
        rows = preview_episode.playlist_rows(actions, sources)
        document = preview_episode.mpv_edl_text(rows)
        self.assertTrue(document.startswith("# mpv EDL v0\n"))
        body = [line for line in document.splitlines() if line and not line.startswith("#")]
        self.assertEqual(len(body), len(actions))
        # open 尾、close 头按 xfade 扣掉，跑步段不动。时长是长度，不是出点。
        expected = {
            "2026-01-02-open.mp4": ("0.000000", "7.800000"),
            "2026-01-02-run-a.mp4": ("0.000000", "12.300000"),
            "2026-01-02-close.mp4": ("0.200000", "5.800000"),
        }
        for action, line in zip(actions, body, strict=True):
            path, start, length = line.split(",")
            self.assertEqual(path, str(sources[action["clip"]]))
            self.assertEqual((start, length), expected[action["clip"]])
        virtual = preview_episode.virtual_duration(rows)
        self.assertAlmostEqual(virtual, edl.frame_program_duration(table), places=3)
        self.assertAlmostEqual(virtual, 7.8 + 12.3 + 5.8, places=3)
        blob = document + " " + " ".join(preview_episode.mpv_play_command(Path("/tmp/review.edl"), None))
        self.assertNotIn("libx264", blob)
        self.assertNotIn("hevc_videotoolbox", blob)
        self.assertNotIn("trim=start=", blob)
        self.assertNotIn("ffmpeg", blob)
        self.assertNotIn("-c copy", document)
        for name in (
            "build_program_preview_commands",
            "copy_range_command",
            "program_preview_duration_bounds",
            "assert_program_preview_duration",
            "_run_program_preview_commands",
        ):
            self.assertFalse(hasattr(preview_episode, name), name)
        slices = [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in actions]
        self.assertEqual(slices, [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in edl.export_slices(table)])
        self.assertEqual(graph.count("xfade="), 2)
        self.assertNotIn("dblur", graph)
        self.assertNotIn("whoosh", graph)

    def test_kept_range_preview_uses_input_seek_copy(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        sys.path.insert(0, str(Path(__file__).resolve().parent / "hud"))
        import preview_episode
        import render_running_hud as hud

        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [{"clip": "2026-01-02-run-a.mp4", "src_start_s": 12.5, "src_end_s": 18.25}],
        )
        actions = edl.preview_actions(table)
        self.assertEqual(actions[0]["mode"], "copy")
        source = Path("/media/2026-01-02-run-a.mp4")
        rows = preview_episode.playlist_rows(actions, {"2026-01-02-run-a.mp4": source})
        document = preview_episode.mpv_edl_text(rows)
        start = float(actions[0]["src_start_s"])
        end = float(actions[0]["src_end_s"])
        play_start, play_length = preview_episode.preview_play_span(actions[0])
        self.assertGreater(start, 12.0)
        self.assertLess(end, 18.3)
        self.assertAlmostEqual(play_start, start)
        self.assertAlmostEqual(play_length, end - start)
        self.assertNotEqual(f"{play_start:.6f}", "0.000000")
        line = next(item for item in document.splitlines() if item and not item.startswith("#"))
        self.assertEqual(
            line,
            f"{source},{play_start:.6f},{play_length:.6f}",
        )
        self.assertNotIn("trim=", document)
        self.assertNotIn("libx264", document)
        self.assertNotIn("atrim=", document)
        self.assertNotIn("ffmpeg", document)

        plans = hud.plan_alpha_jobs(Path("/media"), table)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["source"], Path("/media/2026-01-02-run-a.mp4"))
        self.assertNotIn("keeps", plans[0]["dest"].parts)
        self.assertNotIn("keeps", plans[0]["dest"].as_posix())
        self.assertTrue(plans[0]["ranged"])
        cmd = hud.hud_overlay_command(
            gopro_python=Path("/venv/bin/python"),
            gopro_dashboard=Path("/venv/bin/gopro-dashboard.py"),
            clip=plans[0]["source"],
            out=plans[0]["dest"],
            font=Path("/font.otf"),
            fit=Path("/media/run.fit"),
            template=Path("/tmp/layout.xml"),
            cache_dir=Path("/tmp/cache"),
            video_end_time_mode="file-modified",
            overlay_profile="qtrle",
            shoe_name="Fly",
            shoe_total_km_after_run=10,
            range_start=plans[0]["src_start_s"],
            range_end=plans[0]["src_end_s"],
        )
        self.assertLess(cmd.index("--hud-start"), cmd.index("--hud-end"))
        self.assertEqual(cmd[2], str(plans[0]["source"]))
        self.assertNotIn("libx264", cmd)
        self.assertNotIn("hud-renders/keeps", " ".join(cmd))
        self.assertEqual(hud.kept_source_steps([12.4, 12.5, 18.2, 18.25], 12.5, 18.25), [12.5, 18.2])

        keep = hud.hud_keep_trim_cmd(Path("/media/run.mp4"), Path("/tmp/keep.mp4"), 12.5, 18.25)
        keep_blob = " ".join(keep)
        self.assertLess(keep.index("-ss"), keep.index("-i"))
        self.assertEqual(keep[keep.index("-ss") + 1], "12.500000")
        self.assertGreater(keep.index("-t"), keep.index("-i"))
        self.assertEqual(keep[keep.index("-t") + 1], "5.750000")
        self.assertNotIn("trim=", keep_blob)
        self.assertNotIn("atrim=", keep_blob)
        self.assertIn("libx264", keep)
        argv = hud.overlay_render_argv(
            render_dir=Path("/media/keeps"),
            clips=["a.mp4", "b.mp4"],
            output_dir=Path("/media/out"),
            fit=Path("/media/run.fit"),
            hud={"shoe_name": "Fly", "shoe_km_after": 10, "weather_city": "shanghai"},
            weather=Path("/media/weather-hourly.json"),
            profile="qtrle",
            jobs=hud.HUD_EXPORT_JOBS,
        )
        self.assertGreaterEqual(hud.HUD_EXPORT_JOBS, 2)
        self.assertEqual(argv[argv.index("-j") + 1], "2")
        self.assertNotEqual(argv[argv.index("-j") + 1], "1")

    def test_preview_edl_matches_timeline_without_keyframe_preroll(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import preview_episode

        durations = [
            ("2026-11-12-open.mp4", 86.4),
            ("2026-11-12-run-a.mp4", 201.866667),
            ("2026-11-12-run-b.mp4", 111.8),
            ("2026-11-12-run-c.mp4", 113.4),
            ("2026-11-12-run-d.mp4", 116.333333),
            ("2026-11-12-run-e.mp4", 263.933333),
            ("2026-11-12-close.mp4", 259.266667),
        ]
        table = edl.empty_program("2026-11-12-8020")
        edl.set_source_sync(
            table,
            [
                {"clip": name, "fit": "2026-11-12-run-data.fit", "offset_s": 0.0}
                for name, _dur in durations
                if "-run-" in name
            ],
        )
        edl.upsert_keeps(
            table,
            [{"clip": name, "src_start_s": 0.0, "src_end_s": dur} for name, dur in durations],
        )
        actions = edl.preview_actions(table)
        sources = {row["clip"]: Path("/media") / row["clip"] for row in actions}
        rows = preview_episode.playlist_rows(actions, sources)
        self.assertEqual(len(rows), 7)
        timeline = edl.frame_program_duration(table)
        virtual = preview_episode.virtual_duration(rows)
        self.assertAlmostEqual(timeline, 1152.6)
        self.assertAlmostEqual(virtual, timeline, places=3)
        # 四道跑步接缝的 0.08 秒风刮不缩短。130 刀的关键帧预卷曾经多出约 55 秒。
        self.assertLess(abs(virtual - timeline), 0.05)
        self.assertNotAlmostEqual(virtual, timeline + 55, delta=1)
        run_rows = [row for action, row in zip(actions, rows, strict=True) if action["type"] == "run"]
        self.assertEqual(len(run_rows), 5)
        for action, (_, start, length) in zip(
            [item for item in actions if item["type"] == "run"], run_rows, strict=True
        ):
            self.assertAlmostEqual(start, action["src_start_s"])
            self.assertAlmostEqual(length, action["src_end_s"] - action["src_start_s"])

        cut = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(
            cut,
            [
                {"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0},
                {"clip": "2026-01-02-run-b.mp4", "fit": "run.fit", "offset_s": 0.0},
            ],
        )
        keeps = [{"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 8.0}]
        for index in range(130):
            src = 10.0 + index * 3.0
            keeps.append({"clip": "2026-01-02-run-a.mp4", "src_start_s": src, "src_end_s": src + 1.0})
        keeps.append({"clip": "2026-01-02-run-b.mp4", "src_start_s": 0.0, "src_end_s": 4.0})
        keeps.append({"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 6.0})
        edl.upsert_keeps(cut, keeps)
        edl.record_hud(cut, shoe_name="Fly", shoe_km_after=100.0, weather_city="shanghai")
        self.assertEqual(len(edl.wind_transitions(cut)), 1)
        cut_actions = edl.preview_actions(cut)
        cut_rows = preview_episode.playlist_rows(
            cut_actions, {row["clip"]: Path("/media") / row["clip"] for row in cut_actions}
        )
        self.assertEqual(len(cut_rows), 133)
        cut_timeline = edl.frame_program_duration(cut)
        cut_virtual = preview_episode.virtual_duration(cut_rows)
        self.assertAlmostEqual(cut_virtual, cut_timeline, places=3)
        self.assertLess(cut_virtual, cut_timeline + 1.0)
        runs = [row for action, row in zip(cut_actions, cut_rows, strict=True) if action["type"] == "run"]
        self.assertTrue(all(action["trim_head_s"] == 0 and action["trim_tail_s"] == 0
                            for action in cut_actions if action["type"] == "run"))
        self.assertAlmostEqual(sum(length for _, _, length in runs), 130.0 + 4.0, places=3)

    def test_mpv_edl_quotes_special_paths(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import preview_episode

        plain = "/media/2026-01-02-run-a.mp4"
        self.assertEqual(preview_episode.quote_mpv_edl_value(plain), plain)
        spaced = "/media/my run/clip.mp4"
        self.assertEqual(preview_episode.quote_mpv_edl_value(spaced), spaced)
        for value in ("dir/a,b.mp4", "a;b.mp4", "a\nb.mp4", "go!clip.mp4", "#clip.mp4", "%2Falready.mp4", ""):
            quoted = preview_episode.quote_mpv_edl_value(value)
            raw = value.encode("utf-8")
            self.assertEqual(quoted, f"%{len(raw)}%{value}")
        weird = Path("/media/a,b/跑.mp4")
        text = preview_episode.mpv_edl_text([(str(weird), 1.5, 2.25)])
        encoded = str(weird).encode("utf-8")
        self.assertEqual(text, f"# mpv EDL v0\n%{len(encoded)}%{weird},1.500000,2.250000\n")
        self.assertEqual(
            preview_episode.playlist_source(Path("/media/a.mp4"), Path("/media/review.edl")),
            "a.mp4",
        )
        outside = preview_episode.playlist_source(Path("/elsewhere/a.mp4"), Path("/media/review.edl"))
        self.assertTrue(outside.endswith("/elsewhere/a.mp4"))
        mpv = preview_episode.mpv_play_command(Path("/tmp/review.edl"), Path("/tmp/review.srt"))
        iina = preview_episode.iina_play_command(Path("/tmp/review.edl"), Path("/tmp/review.srt"))
        self.assertEqual(mpv[0], "mpv")
        self.assertNotIn("--no-stdin", mpv)
        self.assertIn("--sub-file=/tmp/review.srt", mpv)
        self.assertNotIn("--sub-files=/tmp/review.srt", mpv)
        self.assertEqual(preview_episode.mpv_play_command(Path("/tmp/review.edl"), None), ["mpv", "/tmp/review.edl"])
        self.assertEqual(
            iina,
            ["iina", "--no-stdin", "/tmp/review.edl", "--", "--sub-files=/tmp/review.srt"],
        )
        self.assertNotIn("--mpv-sub-file=/tmp/review.srt", iina)
        self.assertEqual(
            preview_episode.iina_play_command(Path("/tmp/review.edl"), None),
            ["iina", "--no-stdin", "/tmp/review.edl"],
        )

    def test_program_preview_writes_edl_not_mp4(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import preview_episode

        table = _ready()
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp)
            for name in ("2026-01-02-open.mp4", "2026-01-02-run-a.mp4", "2026-01-02-close.mp4"):
                (media / name).write_bytes(b"")
            edl.save(media, table)
            for step in ("ingest", "edl", "hud-record", "layout"):
                todo.mark(media, step, "done")
            subs = media / "subtitles.txt"
            subs.write_text("0:00:01.00–0:00:02.50  听这一句\n", encoding="utf-8")
            argv = ["--media-dir", str(media), "--subtitles", str(subs), "--play"]
            with unittest.mock.patch.object(
                preview_episode.subprocess, "Popen", side_effect=FileNotFoundError("mpv")
            ):
                rc = preview_episode.main(argv)
            self.assertEqual(rc, 0)
            playlist = media / "2026-01-02-review-preview.edl"
            sidecar = media / "2026-01-02-review-preview.srt"
            self.assertTrue(playlist.is_file())
            self.assertFalse((media / "2026-01-02-review-preview.mp4").exists())
            text = playlist.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# mpv EDL v0\n"))
            body = [line for line in text.splitlines() if line and not line.startswith("#")]
            self.assertEqual(len(body), 3)
            self.assertTrue(body[0].startswith("2026-01-02-open.mp4,0.000000,7.800000"))
            self.assertFalse(body[0].startswith("/"))
            self.assertIn("听这一句", sidecar.read_text(encoding="utf-8"))
            self.assertIn("00:00:01,000", sidecar.read_text(encoding="utf-8"))
            self.assertNotIn("libx264", text)
            self.assertNotIn("trim=start=", text)
            log = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("START  review-preview", log)
            self.assertIn("END    review-preview", log)
            self.assertEqual(todo.load(media)["preview"], "done")
            with self.assertRaises(SystemExit):
                preview_episode.main(["--media-dir", str(media), "--out", str(media / "nope.mp4"), "--dry-run"])

    def test_export_seeks_cut_sources_and_trims_from_zero(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import final_export

        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [{"clip": "2026-01-02-run-a.mp4", "src_start_s": 8.0, "src_end_s": 12.0}],
        )
        for seg in table["program"]:
            seg["hud"] = False
        args = final_export.program_input_args(Path("/media"), table, [])
        self.assertLess(args.index("-ss"), args.index("-i"))
        self.assertEqual(args[args.index("-ss") + 1], "8.000000")
        graph = final_export.build_program_filter(table, [], 0, None, apply_loudness=False)
        self.assertIn("trim=start=0.000000:end=4.000000", graph)
        self.assertIn("atrim=start=0.000000:end=4.000000", graph)
        self.assertNotIn("trim=start=8.000000", graph)

    def test_unaligned_keeps_do_not_push_close_xfade_past_the_picture(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import final_export

        table = edl.empty_program("2026-01-02-demo")
        runs = [f"2026-01-02-run-{index:02d}.mp4" for index in range(20)]
        edl.set_source_sync(table, [{"clip": name, "fit": "run.fit", "offset_s": 0.0} for name in runs])
        rows = [{"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 10.016}]
        rows.extend({"clip": name, "src_start_s": 0.0, "src_end_s": 10.016} for name in runs)
        rows.append({"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 10.016})
        edl.upsert_keeps(table, rows)
        close = edl.frame_timeline(table)[-1]
        graph = final_export.build_program_filter(
            table, ["full"] * len(runs), 0, None, apply_loudness=False,
        )
        offset = close["program_start_frame"] / 30
        self.assertAlmostEqual(offset, 209.6)
        self.assertIn(f"offset={offset:.6f}", graph)
        self.assertNotIn("offset=209.936", graph)
        self.assertEqual(graph.count("xfade="), 2)
        self.assertEqual(graph.count("dblur="), 38)

    def test_published_close_xfade_matches_frame_offset(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import final_export

        durations = [
            ("2026-11-12-open.mp4", 86.4),
            ("2026-11-12-run-a.mp4", 201.866667),
            ("2026-11-12-run-b.mp4", 111.8),
            ("2026-11-12-run-c.mp4", 113.4),
            ("2026-11-12-run-d.mp4", 116.333333),
            ("2026-11-12-run-e.mp4", 263.933333),
            ("2026-11-12-close.mp4", 259.266667),
        ]
        table = edl.empty_program("2026-11-12-8020")
        edl.set_source_sync(
            table,
            [{"clip": name, "fit": "fit.fit", "offset_s": 0.0} for name, _dur in durations if "-run-" in name],
        )
        edl.upsert_keeps(table, [{"clip": name, "src_start_s": 0.0, "src_end_s": dur} for name, dur in durations])
        graph = final_export.build_program_filter(table, ["full"] * 5, 0, Path("/tmp/cues.ass"), apply_loudness=False)
        self.assertIn("xfade=transition=fade:duration=0.200000:offset=893.333333", graph)
        self.assertEqual(graph.count("xfade="), 2)
        self.assertEqual(len(edl.wind_transitions(table)), 4)
        self.assertIn("trim=duration=0.066667", graph)
        self.assertIn("dblur=angle=0:radius=46", graph)
        self.assertIn("adelay=delays=", graph)
        self.assertIn("subtitles=", graph)
        self.assertAlmostEqual(edl.frame_program_duration(table), 1152.6)

    def test_ffmpeg_keeps_close_when_source_times_are_off_the_frame_grid(self) -> None:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg not installed")
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import final_export

        dur = 0.349
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            names = ["2026-01-02-open.mp4", *[f"2026-01-02-run-{i:02d}.mp4" for i in range(20)], "2026-01-02-close.mp4"]
            for name in names:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"color=c=blue:s=160x90:r=30:d={dur}",
                        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        str(root / name),
                    ],
                    check=True,
                )
            table = edl.empty_program("2026-01-02-demo")
            table["wind_s"] = 0
            runs = [name for name in names if "-run-" in name]
            edl.set_source_sync(table, [{"clip": name, "fit": "run.fit", "offset_s": 0.0} for name in runs])
            edl.upsert_keeps(table, [{"clip": name, "src_start_s": 0.0, "src_end_s": dur} for name in names])
            for seg in table["program"]:
                seg["hud"] = False
            expected = edl.frame_program_duration(table)
            graph = final_export.build_program_filter(table, [], 0, None, apply_loudness=False)
            out = root / "out.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    *final_export.program_input_args(root, table, []),
                    "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(out),
                ],
                check=True,
            )
            actual = final_export.probe_duration(out)
        self.assertLess(abs(actual - expected), 0.15)

    def test_ffmpeg_wind_does_not_shorten_two_runs(self) -> None:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg not installed")
        sys.path.insert(0, str(Path(__file__).resolve().parent / "assemble"))
        import final_export

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, color in (("2026-01-02-run-a.mp4", "red"), ("2026-01-02-run-b.mp4", "blue")):
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=30:d=1",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        str(root / name),
                    ],
                    check=True,
                )
            table = edl.empty_program("2026-01-02-demo")
            edl.set_source_sync(
                table,
                [
                    {"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0},
                    {"clip": "2026-01-02-run-b.mp4", "fit": "run.fit", "offset_s": 1.0},
                ],
            )
            edl.upsert_keeps(
                table,
                [
                    {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 1.0},
                    {"clip": "2026-01-02-run-b.mp4", "src_start_s": 0.0, "src_end_s": 1.0},
                ],
            )
            for seg in table["program"]:
                seg["hud"] = False
            self.assertEqual(len(edl.wind_transitions(table)), 1)
            graph = final_export.build_program_filter(table, [], 0, None, apply_loudness=False)
            self.assertIn("dblur=", graph)
            self.assertNotIn("xfade=", graph)
            out = root / "out.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    *final_export.program_input_args(root, table, []),
                    "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(out),
                ],
                check=True,
            )
            actual = final_export.probe_duration(out)
        self.assertAlmostEqual(edl.frame_program_duration(table), 2.0)
        self.assertLess(abs(actual - 2.0), 0.05)


class TodoTest(unittest.TestCase):
    def test_later_steps_cannot_skip_ahead(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            with self.assertRaises(ValueError):
                todo.mark(media, "preview", "done")
            todo.mark(media, "ingest", "done")
            todo.mark(media, "edl", "done")
            todo.mark(media, "hud-record", "done")
            todo.mark(media, "layout", "done")
            with self.assertRaises(ValueError):
                todo.mark(media, "hud-render", "done")
            todo.mark(media, "preview", "done")
            todo.mark(media, "subs", "waiting-review")
            todo.mark(media, "hud-render", "done")
            todo.mark(media, "loudness-measure", "done")
            self.assertEqual(todo.load(media)["subs"], "waiting-review")
            with self.assertRaises(ValueError):
                todo.mark(media, "final-export", "done")
            with self.assertRaises(ValueError):
                todo.mark(media, "subs", "confirmed")
            todo.mark(media, "subs", "aligned")
            todo.mark(media, "subs", "confirmed", confirmed=True)
            with self.assertRaises(ValueError):
                todo.assert_export_allowed(media) if False else todo.mark(media, "final-qc", "done")
            todo.mark(media, "final-export", "done")
            todo.mark(media, "final-qc", "done")
            todo.assert_pack_allowed(media)
            with self.assertRaises(ValueError):
                todo.assert_publish_allowed(media)
            text = todo.todo_path(media).read_text(encoding="utf-8")
            self.assertIn("subs: confirmed", text)
            self.assertIn("原片对齐", text)
            again = todo.parse(text)
            self.assertEqual(again["subs"], "confirmed")
            self.assertEqual(again["youtube"], "pending")

    def test_export_gate_requires_confirmed_subs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td)
            for step in ("ingest", "edl", "hud-record", "layout", "preview"):
                todo.mark(media, step, "done")
            todo.mark(media, "subs", "waiting-review")
            with self.assertRaises(ValueError):
                todo.assert_export_allowed(media)
            todo.mark(media, "subs", "confirmed", confirmed=True)
            todo.assert_export_allowed(media)


if __name__ == "__main__":
    unittest.main()
