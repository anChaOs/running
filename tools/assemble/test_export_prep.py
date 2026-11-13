#!/usr/bin/env python3
"""冻结后的 HUD / 响度准备，以及确认导出仍是一次烧字编码。不依赖媒体盘。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
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


def test_short_keep_between_hud_ticks_still_has_one_sample() -> None:
    """最短语音 0.08 秒，可能落在 0.1 秒取样点之间。不能因为一帧都没有就退出。"""
    ticks = [index / 10 for index in range(20)]
    kept = hud.kept_source_steps(ticks, 1.02, 1.10)
    assert kept == [1.02]
    normal = hud.kept_source_steps([12.4, 12.5, 18.2, 18.25], 12.5, 18.25)
    assert normal == [12.5, 18.2]
    try:
        hud.kept_source_steps(ticks, 1.10, 1.02)
    except ValueError:
        pass
    else:
        raise AssertionError("empty HUD window should fail")


def test_prep_alpha_reaches_render_main_without_jobs_clash() -> None:
    """--prep-alpha 的非 dry-run 会进 _render_main。jobs 不能同时当任务列表和并行路数。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media, _episode = _stage(root, _table(partial=True), subs="waiting-review")
        (media / "2026-01-02-run-data.fit").write_bytes(b"fit")
        (media / "weather-hourly.json").write_text('{"hours":[]}\n', encoding="utf-8")
        seen: list[dict] = []

        def _write(batch, batch_index=0, **_kwargs):
            for plan in batch:
                dest = Path(plan["dest"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"alpha")
            seen.extend(batch)
            assert batch_index == 0

        venv_python = hud.REPO_ROOT / ".venv" / "bin" / "python"
        real_exists = Path.exists

        def _exists(self):
            if self == venv_python:
                return True
            return real_exists(self)

        with (
            patch.object(hud, "_probe_duration", return_value=100.0),
            patch.object(hud, "resolve_total_distance_meters", return_value=None),
            patch.object(hud, "launch_alpha_batch", side_effect=_write),
            patch.object(Path, "exists", _exists),
        ):
            assert hud.main(["--media-dir", str(media), "--prep-alpha"]) == 0
        assert len(seen) == 1
        assert seen[0]["src_start_s"] == 12.0
        assert seen[0]["src_end_s"] == 18.0
        assert Path(seen[0]["source"]).name == "2026-01-02-run-a.mp4"
        assert "keeps" not in Path(seen[0]["dest"]).parts
        assert (media / "logs" / "hud-alpha.json").is_file()
        assert not (media / "hud-renders" / "keeps").exists()
        assert todo.load(media)["hud-render"] == "done"
        assert todo.load(media)["subs"] == "waiting-review"


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
        assert render.call_args.kwargs["jobs"] == hud.HUD_EXPORT_JOBS
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


def _fake_plan(source, dest, start, end, *, ranged=True) -> dict:
    return {
        "clip": Path(source).name,
        "source": Path(source),
        "dest": Path(dest),
        "src_start_s": start,
        "src_end_s": end,
        "overlay_profile": "qtrle",
        "ranged": ranged,
    }


def _window_table(count: int) -> dict:
    table = edl.empty_program("2026-01-02-demo")
    edl.set_source_sync(
        table,
        [{"clip": "2026-01-02-run-a.mp4", "fit": "2026-01-02-run-data.fit", "offset_s": 0.0}],
    )
    keeps = [{"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0}]
    for index in range(count):
        start = 10.0 + index * 2
        keeps.append({"clip": "2026-01-02-run-a.mp4", "src_start_s": start, "src_end_s": start + 1.0})
    keeps.append({"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 4.0})
    edl.upsert_keeps(table, keeps)
    edl.record_hud(table, shoe_name="Fly", shoe_km_after=100.0, weather_city="shanghai")
    edl.freeze(table)
    return table


def _prep_launches(count: int, extra: list[str]) -> tuple[list[list[float]], list[int]]:
    launches: list[list[float]] = []
    pools: list[int] = []
    lock = threading.Lock()

    def _launch(batch, batch_index=0, **_kwargs):
        del batch_index
        with lock:
            launches.append([float(item["src_start_s"]) for item in batch])
        for item in batch:
            dest = Path(item["dest"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            if "keeps" in dest.parts:
                raise AssertionError(dest)
            dest.write_bytes(b"alpha")

    real_pool = hud.ThreadPoolExecutor

    class _Pool(real_pool):
        def __init__(self, max_workers, **kwargs):
            pools.append(max_workers)
            super().__init__(max_workers=max_workers, **kwargs)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media, _episode = _stage(root, _window_table(count), subs="waiting-review")
        (media / "2026-01-02-run-data.fit").write_bytes(b"fit")
        (media / "weather-hourly.json").write_text('{"hours":[]}\n', encoding="utf-8")
        venv_python = hud.REPO_ROOT / ".venv" / "bin" / "python"
        real_exists = Path.exists

        def _exists(self):
            if self == venv_python:
                return True
            return real_exists(self)

        with (
            patch.object(hud, "_probe_duration", return_value=1000.0),
            patch.object(hud, "resolve_total_distance_meters", return_value=None),
            patch.object(hud, "launch_alpha_batch", side_effect=_launch),
            patch.object(hud, "ThreadPoolExecutor", _Pool),
            patch.object(hud, "HUD_EXPORT_JOBS", 2),
            patch.object(Path, "exists", _exists),
        ):
            assert hud.main(["--media-dir", str(media), "--prep-alpha", *extra]) == 0
        assert not (media / "hud-renders" / "keeps").exists()
    return launches, pools


def test_same_source_windows_do_not_fork_one_wrap_each() -> None:
    """12 个窗口在同一条原片上。默认 2 路、指定 6 路、串行 1 路，启动次数都远少于窗口数。"""
    default_launches, default_pools = _prep_launches(12, [])
    assert hud.HUD_EXPORT_JOBS == 2
    assert len(default_launches) == 2
    assert sorted(len(batch) for batch in default_launches) == [6, 6]
    assert default_pools == [2]
    six_launches, six_pools = _prep_launches(12, ["--jobs", "6"])
    assert len(six_launches) == 6
    assert len(six_launches) < 12
    assert sorted(len(batch) for batch in six_launches) == [2, 2, 2, 2, 2, 2]
    assert six_pools == [6]
    serial_launches, serial_pools = _prep_launches(12, ["--jobs", "1"])
    assert len(serial_launches) == 1
    assert len(serial_launches[0]) == 12
    assert serial_pools == []


def test_batch_plan_splits_only_the_dominant_source() -> None:
    long = Path("/media/run-a.mp4")
    short_b = Path("/media/run-b.mp4")
    short_c = Path("/media/run-c.mp4")
    plans = [_fake_plan(long, f"/out/a{i}.mov", i, i + 0.5) for i in range(12)]
    plans += [_fake_plan(short_b, f"/out/b{i}.mov", i, i + 0.5) for i in range(2)]
    plans += [_fake_plan(short_c, f"/out/c{i}.mov", i, i + 0.5) for i in range(2)]
    batches = hud.batch_alpha_plans(plans, 6)
    by_source: dict[str, list[int]] = {}
    for batch in batches:
        sources = {str(Path(plan["source"]).resolve()) for plan in batch}
        assert len(sources) == 1
        by_source.setdefault(sources.pop(), []).append(len(batch))
    assert by_source[str(long.resolve())] == [2, 2, 2, 2, 2, 2]
    assert by_source[str(short_b.resolve())] == [2]
    assert by_source[str(short_c.resolve())] == [2]
    assert len(batches) < len(plans)
    even = [_fake_plan("/media/run-a.mp4", f"/out/a{i}.mov", i, i + 0.5) for i in range(6)]
    even += [_fake_plan("/media/run-b.mp4", f"/out/b{i}.mov", i, i + 0.5) for i in range(6)]
    even_batches = hud.batch_alpha_plans(even, 6)
    assert len(even_batches) == 2
    assert sorted(len(batch) for batch in even_batches) == [6, 6]
    try:
        hud.batch_alpha_plans(plans, 0)
    except SystemExit as exc:
        assert "jobs" in str(exc)
    else:
        raise AssertionError("--jobs 0 should stop")


def test_batch_command_is_one_wrap_and_keeps_full_clip_unbounded() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "run-a.mp4"
        source.write_bytes(b"clip")
        plans = [_fake_plan(source, root / f"w{i}.mov", 10 + i * 2, 11 + i * 2) for i in range(4)]
        cmd = hud.alpha_batch_argv(
            plans,
            batch_index=3,
            gopro_python=root / "python",
            gopro_dashboard=root / "gopro_dashboard_wrap.py",
            font=root / "font.otf",
            fit=root / "run.fit",
            resolved_template=root / "layout.xml",
            video_end_time_mode="file-modified",
            overlay_profile="qtrle",
            shoe_name="Fly",
            shoe_total_km_after_run=10,
            cache_dir=root / "cache",
        )
        assert sum(part.endswith("gopro_dashboard_wrap.py") for part in cmd) == 1
        assert "--hud-windows" in cmd
        assert "--hud-start" not in cmd
        assert "libx264" not in cmd
        assert "keeps" not in " ".join(cmd)
        assert str(source.resolve()) in cmd
        spec = json.loads((root / "cache" / "windows.json").read_text(encoding="utf-8"))
        assert len(spec["windows"]) == 4
        assert [row["start"] for row in spec["windows"]] == [10, 12, 14, 16]
        assert all(row["output"].endswith(".mov") for row in spec["windows"])
        assert "hud-renders/keeps" not in json.dumps(spec)
    full = _fake_plan("/media/run-a.mp4", "/out/full.mov", 0, 100, ranged=False)
    spec = hud.alpha_windows_spec([full])
    assert spec["windows"] == [
        {"start": None, "end": None, "output": str(Path("/out/full.mov").resolve())}
    ]


def test_existing_alpha_is_reused_inside_the_shared_wrap() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        table = _window_table(4)
        media, _episode = _stage(root, table, subs="waiting-review")
        (media / "2026-01-02-run-data.fit").write_bytes(b"fit")
        (media / "weather-hourly.json").write_text('{"hours":[]}\n', encoding="utf-8")
        plans = hud.plan_alpha_jobs(media, table, {"2026-01-02-run-a.mp4": 1000.0})
        assert len(plans) == 4
        plans[0]["dest"].parent.mkdir(parents=True, exist_ok=True)
        plans[0]["dest"].write_bytes(b"keep")
        seen: list[list[float]] = []

        def _launch(batch, batch_index=0, **_kwargs):
            del batch_index
            seen.append([float(item["src_start_s"]) for item in batch])
            for item in batch:
                Path(item["dest"]).parent.mkdir(parents=True, exist_ok=True)
                Path(item["dest"]).write_bytes(b"new")

        venv_python = hud.REPO_ROOT / ".venv" / "bin" / "python"
        real_exists = Path.exists

        def _exists(self):
            if self == venv_python:
                return True
            return real_exists(self)

        with (
            patch.object(hud, "_probe_duration", return_value=1000.0),
            patch.object(hud, "resolve_total_distance_meters", return_value=None),
            patch.object(hud, "launch_alpha_batch", side_effect=_launch),
            patch.object(hud, "_alpha_matches", side_effect=lambda path, _profile: Path(path).is_file()),
            patch.object(Path, "exists", _exists),
        ):
            assert hud.main(["--media-dir", str(media), "--prep-alpha", "--jobs", "1"]) == 0
        assert len(seen) == 1
        assert len(seen[0]) == 3
        assert plans[0]["src_start_s"] not in seen[0]
        assert plans[0]["dest"].read_bytes() == b"keep"
        assert not (media / "hud-renders" / "keeps").exists()


def test_confirmed_export_backfill_respects_jobs() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media, episode = _stage(root, _table(partial=False), subs="done")
        out = media / "2026-01-02-run-final.mp4"
        alpha = media / "hud-renders" / "qtrle" / "run-a-hud-alpha.mov"
        seen: dict[str, int] = {}

        def _render(*_args, **kwargs):
            seen["jobs"] = kwargs["jobs"]
            alpha.parent.mkdir(parents=True, exist_ok=True)
            alpha.write_bytes(b"alpha")
            return [alpha]

        with _patches(render_side=_render) as (encode, _render_mock, measure, full_measure):
            measure.return_value = dict(MEASURED)
            assert final_export.main(
                [
                    "--media-dir", str(media),
                    "--episode-dir", str(episode),
                    "--out", str(out),
                    "--confirmed",
                    "--jobs",
                    "6",
                ]
            ) == 0
        assert seen["jobs"] == 6
        assert encode.call_count == 1
        full_measure.assert_not_called()


if __name__ == "__main__":
    test_alpha_plan_does_not_need_keeps()
    test_loudness_reuse_allows_a_tiny_cut_only()
    test_short_keep_between_hud_ticks_still_has_one_sample()
    test_prep_alpha_reaches_render_main_without_jobs_clash()
    test_prep_runs_while_subtitles_are_still_open()
    test_confirmed_export_reuses_prep_and_encodes_once()
    test_confirmed_export_backfills_missing_prep_then_encodes_once()
    test_export_refuses_without_confirmed_subs_and_writes_nothing()
    test_same_source_windows_do_not_fork_one_wrap_each()
    test_batch_plan_splits_only_the_dominant_source()
    test_batch_command_is_one_wrap_and_keeps_full_clip_unbounded()
    test_existing_alpha_is_reused_inside_the_shared_wrap()
    test_confirmed_export_backfill_respects_jobs()
    print("ok")
