#!/usr/bin/env python3
"""log_timeline 的格式、时区、追加、elapsed、failures.md。"""

from __future__ import annotations

import io
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "assemble"))

import log_timeline as tl


SH = tl.SH
UTC = timezone.utc


def at(hms: str, day: str = "2026-11-11") -> datetime:
    return datetime.strptime(f"{day} {hms}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH)


class LogTimelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.media = Path(self.tmp.name) / "2026-11-11-slug"
        self.media.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def timeline(self) -> str:
        return (self.media / "logs" / "timeline.txt").read_text(encoding="utf-8")

    def test_format_start_end_fail(self) -> None:
        start = tl.start(self.media, "final-export", now=at("10:25:30"))
        end = tl.end(self.media, "final-export", now=at("10:32:02"))
        fail = tl.fail(self.media, "bilibili-upload", rc=1, note="optional", now=at("11:01:00"))
        self.assertEqual(start, "2026-11-11 10:25:30  START  final-export")
        self.assertEqual(end, "2026-11-11 10:32:02  END    final-export  elapsed=6m32s  rc=0")
        self.assertEqual(
            fail,
            "2026-11-11 11:01:00  FAIL   bilibili-upload  rc=1  note=optional",
        )
        text = self.timeline()
        self.assertEqual(
            text,
            start + "\n" + end + "\n" + fail + "\n",
        )

    def test_timezone_converts_utc_and_keeps_naive_as_shanghai(self) -> None:
        utc = datetime(2026, 11, 11, 2, 25, 30, tzinfo=UTC)
        line = tl.start(self.media, "final-export", now=utc)
        self.assertTrue(line.startswith("2026-11-11 10:25:30  START  "))
        naive = datetime(2026, 11, 11, 10, 32, 2)
        end = tl.end(self.media, "final-export", now=naive)
        self.assertTrue(end.startswith("2026-11-11 10:32:02  END    "))
        self.assertIn("elapsed=6m32s", end)

    def test_append_does_not_rewrite_old_lines(self) -> None:
        path = self.media / "logs" / "timeline.txt"
        path.parent.mkdir()
        original = "# 2026-11-11-slug timeline (Asia/Shanghai)\n2026-11-04 08:00  START  hud-render\n"
        path.write_text(original, encoding="utf-8")
        tl.start(self.media, "cover", now=at("07:48:01"))
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original))
        self.assertTrue(text.endswith("2026-11-11 07:48:01  START  cover\n"))

    def test_elapsed_matches_latest_unmatched_start(self) -> None:
        tl.start(self.media, "hud-render", now=at("07:48:00"))
        tl.start(self.media, "cover", now=at("07:50:00"))
        tl.end(self.media, "cover", now=at("08:05:30"))
        tl.start(self.media, "hud-render", now=at("09:00:00"))
        hud = tl.end(self.media, "hud-render", now=at("09:02:05"))
        self.assertIn("elapsed=2m5s", hud)
        lines = self.timeline().splitlines()
        self.assertEqual(lines[0], "2026-11-11 07:48:00  START  hud-render")
        self.assertIn("elapsed=15m30s", lines[2])

    def test_elapsed_without_seconds_does_not_invent_them(self) -> None:
        path = self.media / "logs" / "timeline.txt"
        path.parent.mkdir()
        path.write_text("2026-11-11 10:52  START  bilibili-upload\n", encoding="utf-8")
        line = tl.fail(self.media, "bilibili-upload", now=at("11:01:30"), note="ssl")
        self.assertIn("elapsed=9m", line)
        self.assertNotIn("elapsed=9m0s", line)
        self.assertNotIn("elapsed=9m30s", line)
        self.assertNotRegex(line, r"10:52:00")

    def test_end_without_start_omits_elapsed(self) -> None:
        line = tl.end(self.media, "shoes", now=at("12:00:00"))
        self.assertEqual(line, "2026-11-11 12:00:00  END    shoes  rc=0")
        self.assertFalse((self.media / "logs" / "failures.md").exists())

    def test_fail_appends_failures_md_and_keeps_sections(self) -> None:
        tl.start(self.media, "bilibili-upload", now=at("10:52:00"))
        tl.fail(self.media, "bilibili-upload", rc=1, note="line one\nline two", now=at("11:01:00"))
        tl.start(self.media, "youtube-upload", now=at("11:10:00"))
        tl.end(self.media, "youtube-upload", now=at("11:12:00"))
        tl.fail(self.media, "youtube-upload", rc=3, note="timeout", now=at("11:20:00"))
        text = (self.media / "logs" / "failures.md").read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "\n".join(
                [
                    "## 2026-11-11 11:01:00  bilibili-upload",
                    "",
                    "- rc: 1",
                    "- elapsed: 9m0s",
                    "- note: line one line two",
                    "",
                    "## 2026-11-11 11:20:00  youtube-upload",
                    "",
                    "- rc: 3",
                    "- note: timeout",
                    "",
                    "",
                ]
            ),
        )
        self.assertNotIn("youtube-upload  elapsed=2m0s", text)

    def test_retry_adds_new_lines(self) -> None:
        tl.start(self.media, "final-export", now=at("10:00:00"))
        first = tl.fail(self.media, "final-export", rc=1, now=at("10:01:00"))
        tl.start(self.media, "final-export", now=at("10:05:00"))
        second = tl.end(self.media, "final-export", now=at("10:08:04"))
        lines = self.timeline().splitlines()
        self.assertEqual(lines[1], first)
        self.assertEqual(lines[3], second)
        self.assertIn("elapsed=1m0s", first)
        self.assertIn("elapsed=3m4s", second)

    def test_parallel_appends_keep_every_line(self) -> None:
        errors: list[BaseException] = []

        def go(step: str, start_at: datetime) -> None:
            try:
                tl.start(self.media, step, now=start_at)
                tl.end(self.media, step, now=start_at + timedelta(seconds=5))
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=go, args=("hud-render", at("07:48:00"))),
            threading.Thread(target=go, args=("cover", at("07:48:01"))),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        text = self.timeline()
        self.assertEqual(text.count("START"), 2)
        self.assertEqual(text.count("END"), 2)
        self.assertIn("hud-render", text)
        self.assertIn("cover", text)
        self.assertIn("elapsed=5s", text)

    def test_span_records_failure_and_reraises(self) -> None:
        clock = iter((at("10:25:30"), at("10:25:31")))

        def now() -> datetime:
            return next(clock)

        with self.assertRaises(RuntimeError):
            with tl.span(self.media, "final-export", now=now):
                raise RuntimeError("encoder blew up")
        text = self.timeline()
        self.assertIn("2026-11-11 10:25:30  START  final-export", text)
        self.assertIn("FAIL   final-export  elapsed=1s  rc=1  note=RuntimeError: encoder blew up", text)
        failure = (self.media / "logs" / "failures.md").read_text(encoding="utf-8")
        self.assertIn("- rc: 1", failure)
        self.assertIn("encoder blew up", failure)

    def test_span_nonzero_return_and_system_exit(self) -> None:
        with tl.span(self.media, "cover", now=at("01:00:00")) as wall:
            wall.rc = 2
            wall.note = "字太小"
        self.assertIn("rc=2", self.timeline())
        self.assertIn("note=字太小", self.timeline())
        with self.assertRaises(SystemExit):
            with tl.span(self.media, "hud-render", now=at("02:00:00")):
                raise SystemExit(1)
        self.assertIn("FAIL   hud-render", self.timeline())
        self.assertIn("rc=1", self.timeline())

    def test_span_disabled_writes_nothing(self) -> None:
        with self.assertRaises(SystemExit):
            with tl.span(self.media, "ingest", enabled=False):
                raise SystemExit("dry-run still stops")
        self.assertFalse((self.media / "logs").exists())

    def test_span_log_error_does_not_hide_work(self) -> None:
        with patch.object(tl, "start", side_effect=OSError("disk")):
            with redirect_stderr(io.StringIO()):
                with tl.span(self.media, "cover"):
                    pass
        with patch.object(tl, "fail", side_effect=OSError("disk")):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    with tl.span(self.media, "cover"):
                        raise RuntimeError("work")

    def test_cli_appends_and_rejects_bad_step(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = tl.main(["--media-dir", str(self.media), "start", "scaffold"])
        self.assertEqual(rc, 0)
        self.assertIn("START  scaffold", stdout.getvalue())
        with redirect_stdout(io.StringIO()):
            tl.main(["--media-dir", str(self.media), "end", "scaffold", "--note", "ok"])
        self.assertIn("note=ok", self.timeline())
        with self.assertRaises(SystemExit):
            tl.main(["--media-dir", str(self.media), "start", "bad step"])

    def test_hours_elapsed(self) -> None:
        tl.start(self.media, "youtube-upload", now=at("08:00:00"))
        line = tl.end(self.media, "youtube-upload", now=at("09:02:03"))
        self.assertIn("elapsed=1h2m3s", line)

    def test_preview_and_final_export_skip_dry_run(self) -> None:
        import final_export
        import preview_episode

        episode = self.media.parent / "episode"
        episode.mkdir()
        out = self.media / "2026-11-11-run-final.mp4"
        with self.assertRaises(SystemExit):
            preview_episode.main(["--media-dir", str(self.media), "--dry-run"])
        self.assertFalse((self.media / "logs").exists())
        with self.assertRaises(SystemExit):
            preview_episode.main(["--media-dir", str(self.media)])
        preview_log = self.timeline()
        self.assertIn("START  review-preview", preview_log)
        self.assertIn("FAIL   review-preview", preview_log)
        self.assertIn("rc=1", preview_log)

        logged = self.media / "logs" / "timeline.txt"
        before = logged.read_text(encoding="utf-8")
        with self.assertRaises(SystemExit):
            final_export.main(
                [
                    "--media-dir",
                    str(self.media),
                    "--episode-dir",
                    str(episode),
                    "--out",
                    str(out),
                    "--dry-run",
                ]
            )
        self.assertEqual(logged.read_text(encoding="utf-8"), before)
        with self.assertRaises(SystemExit):
            final_export.main(
                [
                    "--media-dir",
                    str(self.media),
                    "--episode-dir",
                    str(episode),
                    "--out",
                    str(out),
                ]
            )
        after = self.timeline()
        self.assertIn("START  final-export", after)
        self.assertIn("FAIL   final-export", after)
        self.assertGreater(after.count("FAIL"), before.count("FAIL"))

    def test_ingest_logs_only_when_apply(self) -> None:
        sys.path.insert(0, str(ROOT / "ingest"))
        import ingest_run_media as ing

        src = self.media / "missing-src"
        root = self.media / "root"
        root.mkdir()
        argv = [
            "ingest",
            "--src",
            str(src),
            "--media-root",
            str(root),
            "--date",
            "2026-11-11",
            "--slug",
            "slug",
        ]
        old = sys.argv
        try:
            sys.argv = argv
            with self.assertRaises(SystemExit):
                ing.main()
            self.assertFalse((root / "2026-11-11-slug" / "logs").exists())
            sys.argv = argv + ["--apply"]
            with self.assertRaises(SystemExit):
                ing.main()
        finally:
            sys.argv = old
        text = (root / "2026-11-11-slug" / "logs" / "timeline.txt").read_text(encoding="utf-8")
        self.assertIn("START  ingest", text)
        self.assertIn("FAIL   ingest", text)

    def test_drive_stage_logs_only_from_upload(self) -> None:
        sys.path.insert(0, str(ROOT / "publish"))
        import stage_drive_chunks as sdc

        src = self.media / "upload" / "title.mp4"
        src.parent.mkdir()
        src.write_bytes(b"abcdefghij")
        rc = sdc.main(
            ["--src", str(src), "--work-dir", str(self.media / "work"), "--split-only", "--chunk-bytes", "4"]
        )
        self.assertEqual(rc, 0)
        text = self.timeline()
        self.assertIn("START  drive-stage", text)
        self.assertIn("END    drive-stage", text)
        self.assertIn("rc=0", text)

        loose = self.media / "loose.mp4"
        loose.write_bytes(b"abcdefghij")
        before = self.timeline()
        rc = sdc.main(
            ["--src", str(loose), "--work-dir", str(self.media / "work2"), "--split-only", "--chunk-bytes", "4"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self.timeline(), before)


if __name__ == "__main__":
    unittest.main()
