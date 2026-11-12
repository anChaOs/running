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
        durations = {
            "2026-01-02-open.mp4": 8.0,
            "2026-01-02-run-a.mp4": 12.3,
            "2026-01-02-close.mp4": 6.0,
        }
        preview = edl.preview_actions(table, durations)
        export = edl.export_slices(table)
        self.assertEqual(
            [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in preview],
            [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in export],
        )
        self.assertEqual([edl.frame_range(row["src_start_s"], row["src_end_s"]) for row in preview],
                         [edl.frame_range(row["src_start_s"], row["src_end_s"]) for row in export])
        modes = {row["id"]: row["mode"] for row in preview}
        self.assertEqual(modes["2026-01-02-run-a-1"], "copy")
        self.assertEqual(modes["2026-01-02-open-1"], "preview-crf")
        self.assertNotIn("49", " ".join(edl.light_video_args("hevc")))
        self.assertNotIn("prores", " ".join(edl.light_video_args("h264")))
        jobs = edl.hud_jobs(table)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["overlay_profile"], "qtrle")
        self.assertEqual(jobs[0]["src_start_s"], 0.0)
        self.assertEqual(jobs[0]["src_end_s"], 12.3)

    def test_partial_run_is_not_stream_copied(self) -> None:
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(table, [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}])
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 1.0, "src_end_s": 4.0},
            ],
        )
        actions = edl.preview_actions(table, {"2026-01-02-run-a.mp4": 20.0})
        self.assertEqual(actions[0]["mode"], "preview-crf")
        self.assertEqual(actions[0]["reason"], "kept-range")

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

    def test_close_stats_share_the_close_segment(self) -> None:
        table = _ready()
        edl.add_close_stats(table, ["stats-01.jpg", "stats-02.jpg"])
        close = next(seg for seg in table["program"] if seg["type"] == "close")
        stats = [ov for ov in table["overlays"] if ov.get("role") == "stats"]
        self.assertEqual(len(stats), 2)
        self.assertAlmostEqual(stats[0]["program_start_s"], close["program_start_s"])
        self.assertAlmostEqual(stats[-1]["program_end_s"], close["program_start_s"] + edl.seg_duration(close))
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
        actions = edl.preview_actions(
            table,
            {
                "2026-01-02-open.mp4": 8.0,
                "2026-01-02-run-a.mp4": 12.3,
                "2026-01-02-close.mp4": 6.0,
            },
        )
        commands = preview_episode.build_program_preview_commands(
            actions,
            {row["clip"]: Path("/media") / row["clip"] for row in actions},
            Path("/tmp/review-preview.mp4"),
            Path("/tmp/work"),
            copy_codec="hevc",
        )
        blob = " ".join(" ".join(cmd) for cmd in commands)
        self.assertNotIn("49M", blob)
        self.assertNotIn("prores", blob)
        self.assertNotIn("loudnorm", blob)
        self.assertNotIn("subtitles=", blob)
        self.assertIn("8M", blob)
        self.assertIn("copy", blob)
        slices = [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in actions]
        self.assertEqual(slices, [(row["clip"], row["src_start_s"], row["src_end_s"]) for row in edl.export_slices(table)])
        self.assertEqual(graph.count("xfade="), 2)
        self.assertNotIn("dblur", graph)
        self.assertNotIn("whoosh", graph)

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
        self.assertNotIn("dblur", graph)

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
        self.assertNotIn("dblur", graph)
        self.assertNotIn("0.066667", graph)
        self.assertIn("subtitles=", graph)

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
            todo.mark(media, "preview", "done")
            todo.mark(media, "subs", "waiting-review")
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
