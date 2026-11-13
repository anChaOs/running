#!/usr/bin/env python3
"""冻结后的 HUD / 响度准备，以及确认导出仍是一次烧字编码。不依赖媒体盘。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "assemble"))
sys.path.insert(0, str(ROOT / "hud"))

import final_export
import final_qc
import program_edl as edl
import render_running_hud as hud
import todo_list as todo

MEASURED = {
    "input_i": "-23.4",
    "input_tp": "-3.1",
    "input_lra": "8.0",
    "input_thresh": "-33.0",
    "target_offset": "1.2",
}


def _table(*, partial: bool) -> dict:
    table = edl.empty_program("2026-01-02-demo")
    edl.set_source_sync(
        table,
        [{"clip": "2026-01-02-run-a.mp4", "fit": "2026-01-02-run-data.fit", "offset_s": 0.0}],
    )
    run = (12.0, 18.0) if partial else (0.0, 12.0)
    edl.upsert_keeps(
        table,
        [
            {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
            {"clip": "2026-01-02-run-a.mp4", "src_start_s": run[0], "src_end_s": run[1]},
            {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
        ],
    )
    edl.record_hud(table, shoe_name="Fly", shoe_km_after=100.0, weather_city="shanghai")
    edl.freeze(table)
    return table


def _stage(root: Path, table: dict, *, subs: str) -> tuple[Path, Path]:
    media = root / "2026-01-02-demo"
    episode = root / "episode"
    media.mkdir()
    episode.mkdir()
    edl.save(media, table)
    for name in ("2026-01-02-open.mp4", "2026-01-02-run-a.mp4", "2026-01-02-close.mp4"):
        (media / name).write_bytes(b"clip")
    (episode / "assets.md").write_text(
        "## 制作状态\n- preview: done\n- qc: done\n- subs: " + subs + "\n",
        encoding="utf-8",
    )
    (episode / "subtitles.txt").write_text("0:00:00.00–0:00:01.00  hi\n", encoding="utf-8")
    for step in ("ingest", "edl", "hud-record", "layout", "preview"):
        todo.mark(media, step, "done")
    if subs == "done":
        todo.mark(media, "subs", "waiting-review")
        todo.mark(media, "subs", "aligned")
        todo.mark(media, "subs", "confirmed", confirmed=True)
    else:
        todo.mark(media, "subs", subs)
    return media, episode


def _qc_ok():
    return (
        patch.object(final_qc, "probe_final", return_value={}),
        patch.object(final_qc, "measure_integrated_lufs", return_value=-16.0),
        patch.object(final_qc, "check_final", return_value=[]),
        patch.object(final_export, "probe_duration", return_value=30.0),
    )


def test_alpha_plan_does_not_need_keeps() -> None:
    table = _table(partial=True)
    media = Path("/media/2026-01-02-demo")
    plans = hud.plan_alpha_jobs(media, table, {"2026-01-02-run-a.mp4": 100.0})
    assert len(plans) == 1
    plan = plans[0]
    assert plan["source"] == media / "2026-01-02-run-a.mp4"
    assert plan["ranged"] is True
    assert "keeps" not in plan["dest"].parts
    assert plan["dest"].parts[-3:][:2] == ("hud-renders", "qtrle") or "hud-renders" in plan["dest"].parts
    assert "keeps" not in plan["dest"].as_posix()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        assert hud.export_alphas(root, table, {"2026-01-02-run-a.mp4": 100.0}, dry_run=True)
        assert not (root / "hud-renders" / "keeps").exists()


def test_loudness_reuse_allows_a_tiny_cut_only() -> None:
    table = _table(partial=False)
    saved = {"measured": dict(MEASURED), "signature": edl_copy(final_export.audio_signature(table))}
    assert final_export.loudness_reusable(saved, table)
    tiny = edl_copy(saved)
    tiny["signature"]["duration_s"] = round(tiny["signature"]["duration_s"] - 0.2, 3)
    tiny["signature"]["slices"][1][2] = round(tiny["signature"]["slices"][1][2] - 0.2, 3)
    assert final_export.loudness_reusable(tiny, table)
    large = edl_copy(saved)
    large["signature"]["duration_s"] = round(large["signature"]["duration_s"] - 5.0, 3)
    large["signature"]["slices"][1][2] = round(large["signature"]["slices"][1][2] - 5.0, 3)
    assert not final_export.loudness_reusable(large, table)
    dropped = edl_copy(saved)
    dropped["signature"]["slices"] = dropped["signature"]["slices"][:1]
    assert not final_export.loudness_reusable(dropped, table)
    graph = final_export.build_program_audio_filter(table)
    assert "subtitles=" not in graph
    assert "loudnorm=" in graph
    assert "scale=" not in graph
    args = final_export.program_audio_input_args(Path("/media"), table)
    run = str(Path("/media/2026-01-02-run-a.mp4"))
    assert "-ss" not in args
    partial = _table(partial=True)
    pargs = final_export.program_audio_input_args(Path("/media"), partial)
    seek = pargs.index("-ss")
    assert seek < pargs.index(run)
    assert pargs[seek + 1] == "12.000000"
    assert "keeps" not in " ".join(pargs)
    picture = final_export.program_input_args(Path("/media"), partial, [Path("/media/hud-renders/qtrle/a.mov")])
    assert "hud-renders/keeps" not in " ".join(picture)
    assert run in picture
    assert picture.index("-ss") < picture.index(run)


def edl_copy(value):
    return json.loads(json.dumps(value))


def test_prep_runs_while_subtitles_are_still_open() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media, _episode = _stage(root, _table(partial=True), subs="waiting-review")
        assert hud.main(["--media-dir", str(media), "--prep-alpha", "--dry-run"]) == 0
        assert not (media / "hud-renders" / "keeps").exists()
        assert todo.load(media)["hud-render"] == "pending"
        assert todo.load(media)["subs"] == "waiting-review"
        with patch.object(final_export, "measure_program_loudness", return_value=dict(MEASURED)) as measured:
            assert final_export.main(["--media-dir", str(media), "--measure-only"]) == 0
        measured.assert_called_once()
        assert todo.load(media)["loudness-measure"] == "done"
        assert todo.load(media)["subs"] == "waiting-review"
        assert final_export.loudness_path(media).is_file()
        assert not list(media.glob("*-run-final.mp4"))


def test_confirmed_export_reuses_prep_and_encodes_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        table = _table(partial=True)
        media, episode = _stage(root, table, subs="done")
        plans = hud.plan_alpha_jobs(media, table, {"2026-01-02-run-a.mp4": 100.0})
        for plan in plans:
            plan["dest"].parent.mkdir(parents=True, exist_ok=True)
            plan["dest"].write_bytes(b"alpha")
        hud.write_alpha_manifest(media, table, plans)
        final_export.write_loudness(media, table, dict(MEASURED))
        out = media / "2026-01-02-run-final.mp4"
        with _patches() as (encode, render, measure, full_measure):
            assert final_export.main(
                [
                    "--media-dir", str(media),
                    "--episode-dir", str(episode),
                    "--out", str(out),
                    "--confirmed",
                ]
            ) == 0
        render.assert_not_called()
        measure.assert_not_called()
        full_measure.assert_not_called()
        assert encode.call_count == 1
        cmd = encode.call_args.args[0]
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "subtitles=" in graph
        assert "measured_I=-23.4" in graph
        assert cmd[-1] == str(out)
        assert "no-subs" not in " ".join(cmd)
        assert "hud-renders/keeps" not in " ".join(cmd)
        assert todo.load(media)["final-export"] == "done"


def test_confirmed_export_backfills_missing_prep_then_encodes_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        table = _table(partial=False)
        media, episode = _stage(root, table, subs="done")
        out = media / "2026-01-02-run-final.mp4"
        alpha = media / "hud-renders" / "qtrle" / "run-a-hud-alpha.mov"

        def _render(*_args, **_kwargs):
            alpha.parent.mkdir(parents=True, exist_ok=True)
            alpha.write_bytes(b"alpha")
            return [alpha]

        with _patches(render_side=_render) as (encode, render, measure, full_measure):
            measure.return_value = dict(MEASURED)
            assert final_export.main(
                [
                    "--media-dir", str(media),
                    "--episode-dir", str(episode),
                    "--out", str(out),
                    "--confirmed",
                ]
            ) == 0
        render.assert_called_once()
        measure.assert_called_once()
        full_measure.assert_not_called()
        assert encode.call_count == 1
        cmd = encode.call_args.args[0]
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "subtitles=" in graph
        assert "loudnorm=" in graph
        assert "measured_I=-23.4" in graph
        assert cmd[-1] == str(out)
        assert todo.load(media)["hud-render"] == "done"
        assert todo.load(media)["loudness-measure"] == "done"


def test_export_refuses_without_confirmed_subs_and_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media, episode = _stage(root, _table(partial=False), subs="waiting-review")
        out = media / "2026-01-02-run-final.mp4"
        with _patches() as (encode, render, measure, _full):
            try:
                final_export.main(
                    ["--media-dir", str(media), "--episode-dir", str(episode), "--out", str(out)]
                )
            except SystemExit as exc:
                assert "confirmed" in str(exc)
            else:
                raise AssertionError("export without --confirmed should stop")
            try:
                final_export.main(
                    [
                        "--media-dir", str(media),
                        "--episode-dir", str(episode),
                        "--out", str(out),
                        "--confirmed",
                    ]
                )
            except SystemExit as exc:
                assert "subs" in str(exc).lower() or "confirmed" in str(exc)
            else:
                raise AssertionError("export before confirmed subtitles should stop")
        encode.assert_not_called()
        render.assert_not_called()
        measure.assert_not_called()
        assert not out.exists()


class _patches:
    def __init__(self, render_side=None):
        self.render_side = render_side

    def __enter__(self):
        self._stack = [
            patch.object(final_export.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
            patch.object(hud, "export_alphas", side_effect=self.render_side),
            patch.object(final_export, "measure_program_loudness"),
            patch.object(final_export, "measure_loudness", side_effect=AssertionError("full-graph measure")),
            *_qc_ok(),
        ]
        started = [item.__enter__() for item in self._stack]
        self.started = started
        return started[0], started[1], started[2], started[3]

    def __exit__(self, exc_type, exc, tb):
        for item in reversed(self._stack):
            item.__exit__(exc_type, exc, tb)
        return False


if __name__ == "__main__":
    test_alpha_plan_does_not_need_keeps()
    test_loudness_reuse_allows_a_tiny_cut_only()
    test_prep_runs_while_subtitles_are_still_open()
    test_confirmed_export_reuses_prep_and_encodes_once()
    test_confirmed_export_backfills_missing_prep_then_encodes_once()
    test_export_refuses_without_confirmed_subs_and_writes_nothing()
    print("ok")
