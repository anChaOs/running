#!/usr/bin/env python3
"""Unit tests for tools/media_layout.py and classified layout integration across tools."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "assemble"))
sys.path.insert(0, str(TOOLS_DIR / "hud"))
sys.path.insert(0, str(TOOLS_DIR / "subs"))
sys.path.insert(0, str(TOOLS_DIR / "publish"))

import media_layout as ml  # noqa: E402
import pack_upload as pu  # noqa: E402
import preview_episode  # noqa: E402
import program_edl as edl  # noqa: E402
import render_running_hud as hud  # noqa: E402
import todo_list as todo  # noqa: E402
import txt_to_subs  # noqa: E402
import final_export  # noqa: E402


class MediaLayoutTests(unittest.TestCase):
    def test_ensure_classified_dirs_and_todo_init(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / "2026-11-24-demo"
            todo.init(media)
            self.assertTrue(ml.is_classified(media))
            for sub in ml.SCAFFOLD_DIRS:
                self.assertTrue((media / sub).is_dir(), sub)
            self.assertTrue((media / "logs" / "todo.md").is_file())

    def test_legacy_flat_folder_detection_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / "2026-11-19-legacy"
            media.mkdir()
            (media / "2026-11-19-run-a.mp4").write_bytes(b"mp4")
            (media / "2026-11-19-run-data.fit").write_bytes(b"fit")
            (media / "weather-hourly.json").write_text("{}", encoding="utf-8")

            self.assertFalse(ml.is_classified(media))
            self.assertFalse(ml.should_use_classified_on_ingest(media))
            self.assertEqual(ml.find_fits(media), [media / "2026-11-19-run-data.fit"])
            self.assertEqual(ml.weather_json_read_path(media), media / "weather-hourly.json")
            self.assertEqual(ml.preview_edl_path(media, "2026-11-19"), media / "2026-11-19-review-preview.edl")
            self.assertEqual(ml.subtitles_srt_dest(media), media / "subtitles.srt")

    def test_classified_resolution_and_end_to_end_pipeline_integration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = ml.ensure_classified_dirs(root / "2026-11-25-demo")
            ep = root / "episodes" / "2026-11-25-demo"
            ep.mkdir(parents=True)

            # Seed raw videos, data files, and classified covers
            open_mp4 = media / "raw" / "2026-11-25-open.mp4"
            run_mp4 = media / "raw" / "2026-11-25-run-a.mp4"
            close_mp4 = media / "raw" / "2026-11-25-close.mp4"
            fit = media / "data" / "2026-11-25-run-data.fit"
            stat = media / "data" / "2026-11-25-stats-01.jpg"
            for p in (open_mp4, run_mp4, close_mp4, fit, stat):
                p.write_bytes(b"data")
            for name in pu.COVERS:
                (media / "covers" / name).write_bytes(b"jpg")

            # 1. HUD clip discovery & alpha planning
            self.assertEqual([p.resolve() for p in hud.discover_clips(media)], [run_mp4.resolve()])
            table = edl.empty_program("2026-11-25-demo")
            edl.set_source_sync(table, [{"clip": "raw/2026-11-25-run-a.mp4", "fit": "data/2026-11-25-run-data.fit", "offset_s": 0.0}])
            edl.upsert_keeps(table, [
                {"clip": "raw/2026-11-25-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
                {"clip": "raw/2026-11-25-run-a.mp4", "src_start_s": 0.0, "src_end_s": 10.0},
                {"clip": "raw/2026-11-25-close.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
            ])
            edl.record_hud(table, shoe_name="Plaid", shoe_km_after=123.45, weather_city="shanghai")
            edl.add_close_stats(table, ["data/2026-11-25-stats-01.jpg"])
            edl.freeze(table)
            edl.save(media, table)

            plans = hud.plan_alpha_jobs(media, table, {"raw/2026-11-25-run-a.mp4": 10.0})
            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0]["source"].resolve(), run_mp4.resolve())
            self.assertIn("2026-11-25-run-a-f0-300-hud-alpha.mov", plans[0]["dest"].name)

            # 2. Final export input resolution resolves raw/ and data/
            args_list = final_export.program_input_args(media, table, [plans[0]["dest"]])
            self.assertIn(str(run_mp4), args_list)
            self.assertIn(str(stat), args_list)

            # 3. Preview EDL writes to preview/ with portable ../raw/ paths
            todo.init(media)
            for step in ("ingest", "edl", "hud-record", "layout"):
                todo.mark(media, step, "done")
            subs = ep / "subtitles.txt"
            subs.write_text("0:00:00.10–0:00:01.20  第一句\n", encoding="utf-8")
            with mock.patch.object(preview_episode.subprocess, "Popen", side_effect=FileNotFoundError):
                rc = preview_episode.main(["--media-dir", str(media), "--subtitles", str(subs)])
            self.assertEqual(rc, 0)
            edl_out = media / "preview" / "2026-11-25-review-preview.edl"
            self.assertTrue(edl_out.is_file())
            self.assertIn("../raw/2026-11-25-open.mp4", edl_out.read_text(encoding="utf-8"))

            # 4. txt_to_subs writes upload/subtitles.srt + preview/YYYY-MM-DD-review-preview.srt
            targets = txt_to_subs.media_sidecar_targets(media, ep.name)
            self.assertEqual(
                [p.resolve() for p in targets],
                [
                    (media / "upload" / "subtitles.srt").resolve(),
                    (media / "preview" / "2026-11-25-review-preview.srt").resolve(),
                ],
            )
            old_argv = sys.argv
            try:
                sys.argv = ["txt_to_subs.py", "--txt", str(subs), "--media-dir", str(media)]
                self.assertEqual(txt_to_subs.main(), 0)
            finally:
                sys.argv = old_argv
            self.assertTrue((media / "upload" / "subtitles.srt").is_file())
            self.assertFalse((media / "subtitles.srt").exists())

            # 5. pack_upload resolves covers from covers/ and keeps upload/subtitles.srt in place
            todo.mark(media, "preview", "done")
            todo.mark(media, "subs", "waiting-review")
            todo.mark(media, "subs", "aligned")
            todo.mark(media, "subs", "confirmed", confirmed=True)
            todo.mark(media, "final-export", "done")
            todo.mark(media, "final-qc", "done")
            titled = media / "测试标题.mp4"
            titled.write_bytes(b"final-video")
            pu.pack(media)
            self.assertTrue((media / "upload" / "测试标题.mp4").is_file())
            self.assertFalse(titled.exists())
            for name in pu.COVERS:
                self.assertTrue((media / "upload" / name).is_file())
            self.assertTrue((media / "upload" / "subtitles.srt").is_file())


if __name__ == "__main__":
    unittest.main()
