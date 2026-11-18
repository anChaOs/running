#!/usr/bin/env python3
"""logs/todo.md 的时间、cleanup，以及没有时间的旧清单。"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import todo_list as todo


SH = todo.SH
UTC = timezone.utc


def at(hms: str, day: str = "2026-11-18") -> datetime:
    return datetime.strptime(f"{day} {hms}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH)


def _through(media: Path, steps: tuple[str, ...], moment: datetime) -> None:
    for step in steps:
        state = "done"
        kwargs: dict = {"now": moment}
        if step == "subs":
            todo.mark(media, "subs", "waiting-review", now=moment)
            todo.mark(media, "subs", "aligned", now=moment)
            state = "confirmed"
            kwargs["confirmed"] = True
        todo.mark(media, step, state, **kwargs)


PREFIX = ("ingest", "edl", "hud-record", "layout", "preview")


class TodoFormatTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.media = Path(self.tmp.name) / "2026-11-18-slug"
        self.media.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_stamps_every_pending_row_and_does_not_reset(self) -> None:
        status = todo.init(self.media, now=at("07:37:36"))
        self.assertEqual(list(status), [key for key, _label in todo.STEPS])
        self.assertTrue(all(status[key] == "pending" for key in status))
        self.assertTrue(all(status.times[key] == "2026-11-18 07:37:36" for key in status))
        text = todo.todo_path(self.media).read_text(encoding="utf-8")
        self.assertIn("- [ ] ingest: 2026-11-18 07:37:36 pending — 原片对齐 FIT", text)
        self.assertIn("- [ ] cleanup: 2026-11-18 07:37:36 pending —", text)
        self.assertIn("可以发了", text)
        self.assertIn("YYYY-MM-DD-review-preview.edl", text)
        self.assertIn("waiting-review", text)
        todo.mark(self.media, "ingest", "done", now=at("08:00:00"))
        again = todo.init(self.media, now=at("09:00:00"))
        self.assertEqual(again["ingest"], "done")
        self.assertEqual(again.times["ingest"], "2026-11-18 08:00:00")
        self.assertEqual(again.times["edl"], "2026-11-18 07:37:36")
        self.assertEqual(again.times["cleanup"], "2026-11-18 07:37:36")

    def test_mark_stamps_only_the_changed_step(self) -> None:
        todo.mark(self.media, "ingest", "done", now=datetime(2026, 11, 17, 23, 37, 36, tzinfo=UTC))
        text = todo.todo_path(self.media).read_text(encoding="utf-8")
        self.assertIn("- [x] ingest: 2026-11-18 07:37:36 done — 原片对齐 FIT", text)
        self.assertRegex(text, r"- \[ \] edl: pending —")
        self.assertRegex(text, r"- \[ \] cleanup: pending —")
        status = todo.parse(text)
        self.assertEqual(status.times["ingest"], "2026-11-18 07:37:36")
        self.assertEqual(status.times["edl"], "")
        self.assertEqual(status.times["cleanup"], "")
        self.assertEqual(status["cleanup"], "pending")
        todo.mark(self.media, "ingest", "done", now=at("09:00:00"))
        self.assertEqual(todo.load(self.media).times["ingest"], "2026-11-18 07:37:36")

    def test_naive_clock_is_shanghai(self) -> None:
        todo.mark(self.media, "ingest", "done", now=datetime(2026, 11, 18, 7, 37, 36))
        self.assertEqual(todo.load(self.media).times["ingest"], "2026-11-18 07:37:36")

    def test_old_file_parses_without_backfill(self) -> None:
        old = (
            "# 成片进度\n\n"
            "- [x] ingest: done — 原片对齐 FIT\n"
            "- [ ] subs: waiting-review — 字幕\n"
            "- [x] preview: done — 低成本预览\n"
        )
        status = todo.parse(old)
        self.assertEqual(status["ingest"], "done")
        self.assertEqual(status["subs"], "waiting-review")
        self.assertEqual(status["preview"], "done")
        self.assertEqual(status["cleanup"], "pending")
        self.assertEqual(status["youtube"], "pending")
        self.assertEqual(status.times["ingest"], "")
        self.assertEqual(status.times["subs"], "")
        self.assertEqual(status.times["cleanup"], "")
        rendered = todo.render(status)
        self.assertRegex(rendered, r"- \[x\] ingest: done —")
        self.assertNotRegex(rendered, r"ingest: \d{4}")
        self.assertRegex(rendered, r"- \[ \] cleanup: pending —")
        path = todo.todo_path(self.media)
        path.parent.mkdir(parents=True)
        path.write_text(old, encoding="utf-8")
        todo.mark(self.media, "edl", "done", now=at("07:37:36"))
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"- \[x\] ingest: done —")
        self.assertIn("- [x] edl: 2026-11-18 07:37:36 done —", text)
        self.assertRegex(text, r"- \[ \] cleanup: pending —")
        again = todo.parse(text)
        self.assertEqual(again.times["ingest"], "")
        self.assertEqual(again.times["edl"], "2026-11-18 07:37:36")
        self.assertEqual(again.times["cleanup"], "")

    def test_clear_prep_restamps_only_steps_that_return_to_pending(self) -> None:
        missing = self.media / "nope"
        todo.clear_prep(missing, now=at("07:37:36"))
        self.assertFalse(todo.todo_path(missing).exists())
        _through(self.media, PREFIX, at("07:00:00"))
        todo.mark(self.media, "hud-render", "done", now=at("07:10:00"))
        todo.mark(self.media, "loudness-measure", "done", now=at("07:11:00"))
        todo.clear_prep(self.media, now=at("07:37:36"))
        status = todo.load(self.media)
        self.assertEqual(status["hud-render"], "pending")
        self.assertEqual(status["loudness-measure"], "pending")
        self.assertEqual(status.times["hud-render"], "2026-11-18 07:37:36")
        self.assertEqual(status.times["loudness-measure"], "2026-11-18 07:37:36")
        self.assertEqual(status["preview"], "done")
        self.assertEqual(status.times["preview"], "2026-11-18 07:00:00")
        todo.clear_prep(self.media, now=at("08:00:00"))
        self.assertEqual(todo.load(self.media).times["hud-render"], "2026-11-18 07:37:36")

    def test_gates_and_cleanup_still_wait_for_prereqs(self) -> None:
        with self.assertRaises(ValueError):
            todo.mark(self.media, "cleanup", "done")
        with self.assertRaises(ValueError):
            todo.mark(self.media, "subs", "confirmed")
        _through(self.media, PREFIX, at("07:00:00"))
        todo.mark(self.media, "subs", "waiting-review", now=at("07:20:00"))
        with self.assertRaises(ValueError):
            todo.assert_export_allowed(self.media)
        text = todo.todo_path(self.media).read_text(encoding="utf-8")
        self.assertRegex(text, r"- \[ \] subs: 2026-11-18 07:20:00 waiting-review —")
        todo.mark(self.media, "subs", "confirmed", confirmed=True, now=at("07:30:00"))
        self.assertRegex(
            todo.todo_path(self.media).read_text(encoding="utf-8"),
            r"- \[x\] subs: 2026-11-18 07:30:00 confirmed —",
        )
        todo.assert_export_allowed(self.media)
        with self.assertRaises(ValueError):
            todo.assert_pack_allowed(self.media)
        todo.mark(self.media, "final-export", "done", now=at("07:40:00"))
        todo.mark(self.media, "final-qc", "done", now=at("07:45:00"))
        todo.assert_pack_allowed(self.media)
        with self.assertRaises(ValueError):
            todo.assert_publish_allowed(self.media)
        todo.mark(self.media, "pack-upload", "done", now=at("07:50:00"))
        todo.mark(self.media, "bilibili", "done", now=at("07:51:00"))
        todo.mark(self.media, "drive", "done", now=at("07:52:00"))
        todo.mark(self.media, "youtube", "done", now=at("07:53:00"))
        todo.assert_publish_allowed(self.media)
        self.assertEqual(todo.load(self.media)["cleanup"], "pending")
        todo.mark(self.media, "published", "done", now=at("07:54:00"))
        todo.mark(self.media, "cleanup", "done", now=at("07:55:00"))
        done = todo.load(self.media)
        self.assertEqual(done["cleanup"], "done")
        self.assertEqual(done.times["cleanup"], "2026-11-18 07:55:00")
        self.assertEqual(done.times["published"], "2026-11-18 07:54:00")

    def test_cli_init_mark_and_gates(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(todo.main(["--media-dir", str(self.media), "show"]), 0)
        self.assertFalse(todo.todo_path(self.media).exists())
        self.assertIn("cleanup:", out.getvalue())
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(todo.main(["--media-dir", str(self.media), "init"]), 0)
        self.assertEqual(err.getvalue(), "")
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(todo.main(["--media-dir", str(self.media), "init"]), 0)
        self.assertIn("not rewritten", err.getvalue())
        marked = io.StringIO()
        with redirect_stdout(marked):
            self.assertEqual(todo.main(["--media-dir", str(self.media), "mark", "ingest", "done"]), 0)
        self.assertRegex(marked.getvalue(), r"- \[x\] ingest: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} done —")
        with self.assertRaises(SystemExit):
            todo.main(["--media-dir", str(self.media), "check", "export"])
        with self.assertRaises(SystemExit):
            todo.main(["--media-dir", str(self.media), "mark", "subs", "confirmed"])


if __name__ == "__main__":
    unittest.main()
