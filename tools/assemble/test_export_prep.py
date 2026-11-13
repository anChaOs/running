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
        videos, audios, joins = _encode_calls(encode)
        assert len(videos) == 1
        assert len(audios) == 1
        assert len(joins) == 1
        cmd = videos[0]
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "subtitles=" in graph
        assert "loudnorm=" not in graph
        assert "-an" in cmd
        assert "fps=30:start_time=0" in graph
        assert cmd[cmd.index("-filter_complex_threads") + 1] == "3"
        assert cmd.index("-filter_complex_threads") < cmd.index("-i")
        assert "-threads" not in cmd
        assert "no-subs" not in " ".join(cmd)
        assert "hud-renders/keeps" not in " ".join(cmd)
        assert cmd.count("hevc_videotoolbox") == 1
        audio = audios[0]
        audio_graph = audio[audio.index("-filter_complex") + 1]
        assert "measured_I=-23.4" in audio_graph
        assert "loudnorm=" in audio_graph
        assert "subtitles=" not in audio_graph
        assert "-vn" in audio
        assert audio[audio.index("-filter_complex_threads") + 1] == "2"
        assert "hevc_videotoolbox" not in audio
        assert joins[0][joins[0].index("-c") + 1] == "copy"
        assert "hevc_videotoolbox" not in joins[0]
        assert joins[0][-1] == str(out)
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
        measure.assert_not_called()
        full_measure.assert_not_called()
        videos, audios, joins = _encode_calls(encode)
        kinds = []
        for cmd in _patches.launched:
            if "-an" in cmd:
                kinds.append("video")
            elif "-vn" in cmd:
                kinds.append("audio")
            elif "-f" in cmd and cmd[cmd.index("-f") + 1] == "null":
                kinds.append("measure")
            else:
                kinds.append("other")
        assert kinds == ["measure", "video", "audio", "other"]
        assert _patches.launched[0][_patches.launched[0].index("-filter_complex_threads") + 1] == "2"
        assert len(videos) == 1
        assert len(audios) == 1
        assert len(joins) == 1
        cmd = videos[0]
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "subtitles=" in graph
        assert "loudnorm=" not in graph
        assert "-an" in cmd
        assert cmd[cmd.index("-filter_complex_threads") + 1] == "3"
        assert cmd.index("-filter_complex_threads") < cmd.index("-i")
        assert "-threads" not in cmd
        assert cmd.count("hevc_videotoolbox") == 1
        audio_graph = audios[0][audios[0].index("-filter_complex") + 1]
        assert "loudnorm=" in audio_graph
        assert "measured_I=-23.4" in audio_graph
        assert joins[0][-1] == str(out)
        assert joins[0][joins[0].index("-c") + 1] == "copy"
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
    launched: list[list[str]] = []

    def __init__(self, render_side=None):
        self.render_side = render_side

    def __enter__(self):
        type(self).launched = []

        def _remember(cmd, **_kwargs):
            if isinstance(cmd, (list, tuple)):
                type(self).launched.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0)

        def _popen(cmd, **_kwargs):
            argv = list(cmd)
            type(self).launched.append(argv)

            class _Err:
                def read(self) -> str:
                    return json.dumps(MEASURED)

            class _Proc:
                def __init__(self) -> None:
                    self.args = argv
                    self.pid = 4242
                    self.returncode = None
                    self.stderr = None
                    if "-f" in argv and argv[argv.index("-f") + 1] == "null":
                        self.stderr = _Err()

                def wait(self, timeout=None):
                    del timeout
                    self.returncode = 0
                    return 0

                def poll(self):
                    return self.returncode

                def kill(self):
                    self.returncode = -9

            return _Proc()

        def _frames(path, **_kwargs):
            for cmd in reversed(type(self).launched):
                if cmd and str(cmd[-1]) == str(path) and "-frames:v" in cmd:
                    return int(cmd[cmd.index("-frames:v") + 1])
            raise AssertionError(f"no video command for {path}")

        self._stack = [
            patch.object(final_export.subprocess, "run", side_effect=_remember),
            patch.object(final_export.subprocess, "Popen", side_effect=_popen),
            patch.object(final_export, "_process_memory_gb", return_value=(0.1, "rss")),
            patch.object(final_export, "probe_video_frames", side_effect=_frames),
            patch.object(hud, "export_alphas", side_effect=self.render_side),
            patch.object(final_export, "measure_program_loudness"),
            patch.object(final_export, "measure_loudness", side_effect=AssertionError("full-graph measure")),
            *_qc_ok(),
        ]
        started = [item.__enter__() for item in self._stack]
        self.started = started
        return started[0], started[4], started[5], started[6]

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


def _input_paths(args: list[str]) -> list[str]:
    return [args[index + 1] for index, flag in enumerate(args) if flag == "-i"]


def _encode_calls(_encode=None) -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    """画面段、整片音频、最后的流拷贝。画面和音频走 Popen，接片走 subprocess.run。"""
    cmds = [list(cmd) for cmd in _patches.launched]
    videos = [cmd for cmd in cmds if "-an" in cmd]
    audios = [cmd for cmd in cmds if "-vn" in cmd]
    joins = [
        cmd for cmd in cmds
        if "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
    ]
    return videos, audios, joins


def _many_slice_program() -> tuple[dict, list[str]]:
    """130 段、7 条原片、118 个跑步 HUD 窗。和撑爆 16GB 的那次导出同一形状。"""
    table = edl.empty_program("2026-01-02-demo")
    runs = [f"2026-01-02-run-{index}.mp4" for index in range(5)]
    edl.set_source_sync(
        table,
        [{"clip": name, "fit": "run.fit", "offset_s": float(index)} for index, name in enumerate(runs)],
    )
    rows: list[dict] = []
    cursor = 0.0
    for _ in range(6):
        rows.append({"clip": "2026-01-02-open.mp4", "src_start_s": cursor, "src_end_s": cursor + 1.0})
        cursor += 1.5
    counts = (24, 24, 24, 23, 23)
    for name, count in zip(runs, counts, strict=True):
        cursor = 8.0
        for _ in range(count):
            rows.append({"clip": name, "src_start_s": cursor, "src_end_s": cursor + 1.0})
            cursor += 1.5
    cursor = 0.0
    for _ in range(6):
        rows.append({"clip": "2026-01-02-close.mp4", "src_start_s": cursor, "src_end_s": cursor + 1.0})
        cursor += 1.5
    edl.upsert_keeps(table, rows)
    return table, runs


def test_confirmed_input_plan_opens_shared_clip_once() -> None:
    table, runs = _many_slice_program()
    timeline = edl.export_slices(table)
    assert len(timeline) == 130
    assert len({row["clip"] for row in timeline}) == 7
    assert sum(1 for row in timeline if row["hud"]) == 118
    alphas = [Path(f"/media/hud-renders/qtrle/{index}.mov") for index in range(118)]
    groups = final_export.confirmed_alpha_groups(table, alphas)
    assert [len(group) for group in groups] == [24, 24, 24, 23, 23]
    assert groups[0][0] == alphas[0]
    assert groups[0][-1] == alphas[23]
    assert groups[1][0] == alphas[24]
    assert set(groups[0]).isdisjoint(groups[1])
    with tempfile.TemporaryDirectory() as td:
        list_dir = Path(td)
        args = final_export.program_input_args(Path("/media"), table, alphas, list_dir=list_dir)
        listing = (list_dir / "alpha-00.ffconcat").read_text(encoding="utf-8")
        assert listing.startswith("ffconcat version 1.0\n")
        assert listing.count("\nfile ") == 24
        assert "file '/media/hud-renders/qtrle/0.mov'" in listing
        assert "file '/media/hud-renders/qtrle/24.mov'" not in listing
        other = (list_dir / "alpha-01.ffconcat").read_text(encoding="utf-8")
        assert "file '/media/hud-renders/qtrle/24.mov'" in other
        assert "file '/media/hud-renders/qtrle/0.mov'" not in other
    paths = _input_paths(args)
    clip_paths = [path for path in paths if path.endswith(".mp4")]
    # 7 条原片 + 5 条按原片收好的 alpha + whoosh。不再是 118 个窗口各一个 -i。
    assert len(paths) == 7 + 5 + 1
    assert len(clip_paths) == 7
    assert len(set(clip_paths)) == 7
    assert paths[0].endswith("2026-01-02-open.mp4")
    assert paths[6].endswith("2026-01-02-close.mp4")
    assert sum(path.endswith(".ffconcat") for path in paths) == 5
    assert not any(path.endswith(".mov") for path in paths)
    for name in runs:
        assert clip_paths.count(str(Path("/media") / name)) == 1
    seeks = [args[index + 1] for index, flag in enumerate(args) if flag == "-ss"]
    assert seeks == ["8.000000"] * 5
    assert "9.500000" not in seeks
    assert "hud-renders/keeps" not in " ".join(args)
    assert len(clip_paths) < len(timeline)

    graph = final_export.build_program_filter(table, ["kept"] * 118, 0, None, apply_loudness=False)
    # 同一条原片的句间刀用 select，不再 split。split 会把解码帧留到这段结束。
    assert "[0:v]fps=30:start_time=0,select=" in graph
    assert "[1:v]fps=30:start_time=0,select=" in graph
    assert "]split=24" not in graph
    assert "]split=6" not in graph
    assert "fps=30:start_time=0" in graph
    assert "gte(t\\,1.483333)*lt(t\\,2.483333)" in graph
    assert "atrim=start=1.500000:end=2.500000" in graph
    assert "concat=n=24:v=0:a=1" in graph
    assert "[7:v]trim=duration=24.000000" in graph
    assert "[10:v]trim=duration=23.000000" in graph
    assert "[11:v]trim=duration=23.000000" in graph
    assert graph.count("overlay=eof_action=pass:shortest=0:format=auto") == 5
    assert "[12:a]" in graph
    assert "[13:v]" not in graph
    assert "[124:v]" not in graph
    assert "[125:a]" not in graph
    assert "[130:v]" not in graph
    cmd = final_export.build_encode_cmd(
        final_export.InputPlan(tuple(args), 7, (), (), 0.0),
        graph,
        Path("/tmp/2026-01-02-run-final.mp4"),
    )
    assert cmd[cmd.index("-filter_complex_threads") + 1] == "1"
    assert cmd.index("-filter_complex_threads") < cmd.index("-i")
    assert cmd.count("hevc_videotoolbox") == 1
    assert "hud-renders/keeps" not in " ".join(cmd)
    audio_args = final_export.program_audio_input_args(Path("/media"), table)
    assert len(_input_paths(audio_args)) == 8
    audio = final_export.build_program_audio_filter(table, apply_loudness=False)
    assert "]split=" not in audio
    assert "asplit=24" in audio
    assert "[7:a]" in audio
    assert "[8:a]" not in audio
    assert "subtitles=" not in audio


def test_rewound_source_opens_a_second_decoder() -> None:
    table = edl.empty_program("2026-01-02-demo")
    edl.set_source_sync(
        table,
        [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}],
    )
    edl.upsert_keeps(
        table,
        [
            {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 2.0},
            {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 2.0},
        ],
    )
    edl.set_lead(
        table,
        {"clip": "2026-01-02-run-a.mp4", "src_start_s": 8.0, "src_end_s": 10.0, "hud": False},
    )
    for seg in table["program"]:
        if seg["type"] != "run":
            seg["hud"] = False
    args = final_export.program_input_args(Path("/media"), table, [Path("/media/hud-renders/qtrle/a.mov")])
    paths = _input_paths(args)
    run = str(Path("/media/2026-01-02-run-a.mp4"))
    assert paths.count(run) == 2
    assert [args[index + 1] for index, flag in enumerate(args) if flag == "-ss"] == ["8.000000"]
    graph = final_export.build_program_filter(table, ["kept"], 0, None, apply_loudness=False)
    assert "]split=" not in graph
    assert "[0:v]fps=30:start_time=0,select='gte(t\\,-0.016667)*lt(t\\,1.983333)'" in graph
    assert "[1:v]fps=30:start_time=0,select='gte(t\\,-0.016667)*lt(t\\,1.983333)'" in graph


def test_confirmed_command_opens_shared_run_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        table = edl.empty_program("2026-01-02-demo")
        edl.set_source_sync(
            table,
            [{"clip": "2026-01-02-run-a.mp4", "fit": "2026-01-02-run-data.fit", "offset_s": 0.0}],
        )
        edl.upsert_keeps(
            table,
            [
                {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 12.0, "src_end_s": 14.0},
                {"clip": "2026-01-02-run-a.mp4", "src_start_s": 16.0, "src_end_s": 18.0},
                {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
            ],
        )
        edl.record_hud(table, shoe_name="Fly", shoe_km_after=100.0, weather_city="shanghai")
        edl.freeze(table)
        media, episode = _stage(root, table, subs="done")
        plans = hud.plan_alpha_jobs(media, table, {"2026-01-02-run-a.mp4": 100.0})
        assert len(plans) == 2
        for plan in plans:
            plan["dest"].parent.mkdir(parents=True, exist_ok=True)
            plan["dest"].write_bytes(b"alpha")
        hud.write_alpha_manifest(media, table, plans)
        final_export.write_loudness(media, table, dict(MEASURED))
        out = media / "2026-01-02-run-final.mp4"
        with _patches() as (encode, render, measure, _full):
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
        videos, audios, joins = _encode_calls(encode)
        assert len(videos) == 1
        assert len(audios) == 1
        assert len(joins) == 1
        cmd = videos[0]
        run = str((media / "2026-01-02-run-a.mp4").resolve())
        assert _input_paths(cmd).count(run) == 1
        assert cmd[cmd.index("-ss") + 1] == "12.000000"
        run_at = cmd.index(run)
        assert cmd[run_at - 3:run_at] == ["-t", "6.500000", "-i"]
        assert cmd[cmd.index("-filter_complex_threads") + 1] == "3"
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "[1:v]fps=30:start_time=0,select=" in graph
        assert "]split=2" not in graph
        assert "gte(t\\,3.983333)*lt(t\\,5.983333)" in graph
        assert "atrim=" not in graph
        assert "loudnorm=" not in graph
        assert "-an" in cmd
        assert graph.count("overlay=eof_action=pass:shortest=0:format=auto") == 1
        assert "measured_I=-23.4" in audios[0][audios[0].index("-filter_complex") + 1]
        inputs = _input_paths(cmd)
        assert inputs.count(run) == 1
        assert sum(path.endswith(".ffconcat") for path in inputs) == 1
        assert not any(path.endswith(".mov") for path in inputs)
        concat_list = next(path for path in inputs if path.endswith(".ffconcat"))
        assert not Path(concat_list).exists()
        assert "hud-renders/keeps" not in " ".join(cmd)
        assert cmd.count("hevc_videotoolbox") == 1


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
        videos, audios, joins = _encode_calls(encode)
        assert len(videos) == 1
        assert len(audios) == 1
        assert len(joins) == 1
        full_measure.assert_not_called()


def _episode_shape():
    """130 段、7 条原片、118 个 HUD 窗，成片大约 1152.6 秒。时长按已发布那期的各条原片分。"""
    durations = [
        ("2026-11-12-open.mp4", 86.4, 6),
        ("2026-11-12-run-a.mp4", 201.866667, 24),
        ("2026-11-12-run-b.mp4", 111.8, 24),
        ("2026-11-12-run-c.mp4", 113.4, 24),
        ("2026-11-12-run-d.mp4", 116.333333, 23),
        ("2026-11-12-run-e.mp4", 263.933333, 23),
        ("2026-11-12-close.mp4", 259.266667, 6),
    ]
    rows = []
    for name, dur, count in durations:
        for index in range(count):
            rows.append(
                {
                    "clip": name,
                    "src_start_s": dur * index / count,
                    "src_end_s": dur * (index + 1) / count,
                }
            )
    table = edl.empty_program("2026-11-12-8020")
    edl.set_source_sync(
        table,
        [{"clip": name, "fit": "fit.fit", "offset_s": 0.0} for name, _dur, count in durations if count > 6],
    )
    edl.upsert_keeps(table, rows)
    edl.add_close_stats(table, ["2026-11-12-stats-01.jpg", "2026-11-12-stats-02.jpg"])
    edl.add_overlay(
        table,
        {
            "asset": "2026-11-12-16week-zones.jpg",
            "program_start_s": 784.13,
            "program_end_s": 864.90,
            "role": "graphic",
            "x": "W-w-48",
            "y": "(H-h)/2",
            "width": 450,
            "opacity": 0.95,
        },
        expect_duration_s=edl.program_duration(table),
    )
    return table


def test_segments_do_not_cut_wind_or_xfade_and_keep_inputs_small() -> None:
    table = _episode_shape()
    timeline = edl.export_slices(table)
    assert len(timeline) == 130
    assert sum(1 for row in timeline if row["hud"]) == 118
    assert abs(edl.frame_program_duration(table) - 1152.6) < 0.05
    blocked = final_export.segment_blocked_starts(table)
    segments = final_export.plan_confirmed_segments(table)
    assert len(segments) > 1
    assert segments[0].start_frame == 0
    assert segments[-1].end_frame == edl.frame_timeline(table)[-1]["program_start_frame"] + edl.frame_timeline(table)[-1]["frames"]
    assert sum(seg.frames for seg in segments) == segments[-1].end_frame
    for seg in segments[1:]:
        assert seg.start_frame not in blocked
    # 每段不超过大约两分钟，尾巴可以短一点。风刮区间并进来时也不会把整片合成一段。
    assert max(seg.frames for seg in segments) <= 120 * 30 + 60
    alphas = [Path(f"/media/hud-renders/qtrle/{index}.mov") for index in range(118)]
    modes = ["kept"] * 118
    cues = [("0:01:59.00", "0:02:05.00", "跨过两分钟")]
    counts = []
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for index, seg in enumerate(segments):
            cmd = final_export.confirmed_segment_cmd(
                Path("/media"), table, seg, alphas, modes, cues, dict(MEASURED),
                work, index, work / f"seg-{index}.mp4",
            )
            inputs = _input_paths(cmd)
            counts.append(len(inputs))
            assert len(inputs) <= 8
            assert len(inputs) < 118
            assert not any(path.endswith(".mov") for path in inputs)
            assert "hud-renders/keeps" not in " ".join(cmd)
            assert cmd.count("hevc_videotoolbox") == 1
            assert "libx265" not in cmd
            assert cmd[cmd.index("-filter_complex_threads") + 1] == "3"
            assert cmd.index("-filter_complex_threads") < cmd.index("-i")
            assert "-threads" not in cmd
            graph = cmd[cmd.index("-filter_complex") + 1]
            assert "]split=24" not in graph
            assert "]split=23" not in graph
            assert "loudnorm=" not in graph
            assert "fps=30:start_time=0" in graph
            assert "-an" in cmd
            assert "subtitles=" in graph
            ass = (work / f"seg-{index:03d}.ass").read_text(encoding="utf-8")
            # 119s–125s 的一句跨过 120s 的段界。前一段只留到段尾，后一段从 0 起算。
            if seg.start_frame == 0:
                assert "0:01:59.00" in ass
                assert "0:02:00.00" in ass
                assert "跨过两分钟" in ass
            if seg.start_frame == 120 * 30:
                assert "Dialogue: 0,0:00:00.00,0:00:05.00,Default" in ass
                assert "0:01:59.00" not in ass
        audio = final_export.program_audio_cmd(
            Path("/media"), table, dict(MEASURED), work / "program-audio.m4a",
        )
        audio_graph = audio[audio.index("-filter_complex") + 1]
        assert "measured_I=-23.4" in audio_graph
        assert "measured_TP=-3.1" in audio_graph
        assert "offset=1.2" in audio_graph
        assert "subtitles=" not in audio_graph
        assert "-vn" in audio
        join = final_export.mux_final_cmd(work / "segments.ffconcat", work / "program-audio.m4a", Path("/tmp/final.mp4"))
        assert join[join.index("-c") + 1] == "copy"
        assert "hevc_videotoolbox" not in join
        assert "-filter_complex" not in join
        assert join[join.index("-map") + 1] == "0:v:0"
    # 这一期的切法：一段最多两条原片加透明层、whoosh 和贴图。
    assert counts == [3, 2, 5, 5, 5, 5, 3, 5, 3, 2]
    assert max(counts) == 5


def test_segment_boundary_keeps_wind_and_xfade_intact() -> None:
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
            {"clip": "2026-01-02-open.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
            {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 10.0},
            {"clip": "2026-01-02-run-b.mp4", "src_start_s": 0.0, "src_end_s": 10.0},
            {"clip": "2026-01-02-close.mp4", "src_start_s": 0.0, "src_end_s": 4.0},
        ],
    )
    for seg in table["program"]:
        if seg["type"] != "run":
            seg["hud"] = False
    blocked = final_export.segment_blocked_starts(table, 30)
    # 目标段长 4 秒，短于每一条。接缝仍必须整段留在同一边。
    segments = final_export.plan_confirmed_segments(table, max_s=4)
    assert len(segments) > 2
    for seg in segments[1:]:
        assert seg.start_frame not in blocked
    timeline = edl.frame_timeline(table)
    wind = next(sl for sl in timeline if sl["id"] in {item["before_id"] for item in edl.wind_transitions(table)})
    seam = int(wind["program_start_frame"])
    owner = next(seg for seg in segments if seg.start_frame <= seam < seg.end_frame)
    assert owner.start_frame < seam < owner.end_frame
    xfade = next(sl for sl in timeline if sl["fade_frames"])
    fade_at = int(xfade["program_start_frame"])
    fade_owner = next(seg for seg in segments if seg.start_frame <= fade_at < seg.end_frame)
    assert fade_owner.start_frame <= fade_at
    assert fade_owner.end_frame >= fade_at + int(xfade["fade_frames"])
    # 段与段的帧数加起来等于成片，没有把叠化算两遍。
    total = timeline[-1]["program_start_frame"] + timeline[-1]["frames"]
    assert sum(seg.frames for seg in segments) == total


def test_subtitle_times_are_local_on_each_side_of_a_cut() -> None:
    cues = [("0:00:08.00", "0:00:12.50", "跨段")]
    first = final_export.cues_for_segment(cues, 0.0, 10.0)
    second = final_export.cues_for_segment(cues, 10.0, 20.0)
    assert first == [("0:00:08.00", "0:00:10.00", "跨段")]
    assert second == [("0:00:00.00", "0:00:02.50", "跨段")]
    assert final_export.cues_for_segment(cues, 20.0, 30.0) == []


def _fake_proc(code: int):
    def _popen(cmd, **_kwargs):
        proc = type("Proc", (), {})()
        proc.args = list(cmd)
        proc.pid = 4242
        proc.returncode = None
        proc._code = code

        def wait(timeout=None):
            del timeout
            proc.returncode = proc._code
            return proc.returncode

        def poll():
            return proc.returncode

        def kill():
            proc.returncode = -9

        proc.wait = wait
        proc.poll = poll
        proc.kill = kill
        _popen.cmds.append(list(cmd))
        return proc

    _popen.cmds = []
    return _popen


def test_fast_init_failure_retries_once_with_one_filter_thread() -> None:
    popen = _fake_proc(1)
    real_code = popen

    def _popen(cmd, **kwargs):
        proc = real_code(cmd, **kwargs)
        proc._code = 1 if len(real_code.cmds) == 1 else 0
        return proc

    with (
        patch.object(final_export.subprocess, "Popen", side_effect=_popen),
        patch.object(final_export, "_process_memory_gb", return_value=(0.1, "rss")),
    ):
        final_export._run_segment_encode(["ffmpeg", "-filter_complex_threads", "3", "-i", "clip.mp4"])
    assert [cmd[cmd.index("-filter_complex_threads") + 1] for cmd in real_code.cmds] == ["3", "1"]

    killed = _fake_proc(-9)
    with (
        patch.object(final_export.subprocess, "Popen", side_effect=killed),
        patch.object(final_export, "_process_memory_gb", return_value=(0.1, "rss")),
    ):
        try:
            final_export._run_segment_encode(["ffmpeg", "-filter_complex_threads", "3", "-i", "clip.mp4"])
        except subprocess.CalledProcessError as exc:
            assert exc.returncode == -9
        else:
            raise AssertionError("SIGKILL should not be retried")
    assert len(killed.cmds) == 1


def test_memory_cap_kills_the_segment_without_retry() -> None:
    popen = _fake_proc(0)

    def _slow(cmd, **kwargs):
        proc = popen(cmd, **kwargs)

        def wait(timeout=None):
            del timeout
            if proc.returncode is None:
                raise subprocess.TimeoutExpired(cmd, 2)
            return proc.returncode

        proc.wait = wait
        return proc

    with (
        patch.object(final_export.subprocess, "Popen", side_effect=_slow),
        patch.object(final_export, "_process_memory_gb", return_value=(9.0, "footprint")),
    ):
        try:
            final_export._run_segment_encode(["ffmpeg", "-filter_complex_threads", "3", "-i", "clip.mp4"])
        except SystemExit as exc:
            assert "not retrying" in str(exc)
        else:
            raise AssertionError("over-cap export should stop")
    assert len(popen.cmds) == 1


def test_footprint_text_is_phys_footprint_in_gb() -> None:
    assert final_export.parse_footprint_gb("phys_footprint: 512 MB\n") == 512 / 1024
    assert abs(final_export.parse_footprint_gb("phys_footprint: 1.5 GB\n") - 1.5) < 1e-9
    text = "phys_footprint_peak: 9 GB\nphys_footprint: 2147483648\n"
    assert abs(final_export.parse_footprint_gb(text) - 2) < 0.01
    assert final_export.parse_footprint_gb("nothing here") is None
    assert abs(final_export.parse_footprint_gb("phys_footprint: 1,024 MiB\n") - 1.0) < 1e-9
    assert abs(final_export.parse_footprint_gb("phys_footprint: 2 GiB\n") - 2.0) < 1e-9
    assert abs(final_export.parse_footprint_gb("phys_footprint: 512 KB\n") - 512 / 1024 / 1024) < 1e-9
    assert final_export.parse_footprint_gb("phys_footprint: 0 B\n") == 0.0
    with (
        patch.object(final_export, "_footprint_gb", return_value=0.0),
        patch.object(final_export, "_rss_gb", return_value=1.25),
    ):
        assert final_export._process_memory_gb(1) == (1.25, "rss")
    with (
        patch.object(final_export, "_footprint_gb", return_value=None),
        patch.object(final_export, "_rss_gb", return_value=0.5),
    ):
        assert final_export._process_memory_gb(1) == (0.5, "rss")
    with (
        patch.object(final_export, "_footprint_gb", return_value=1.5),
        patch.object(final_export, "_rss_gb", side_effect=AssertionError("rss fallback")),
    ):
        assert final_export._process_memory_gb(1) == (1.5, "footprint")


def test_thread_retry_times_the_segment_not_its_audio_companion() -> None:
    popen = _fake_proc(1)

    def _popen(cmd, **kwargs):
        proc = popen(cmd, **kwargs)
        proc._code = 1 if len(popen.cmds) == 1 else 0
        return proc

    companion = type("Companion", (), {})()
    companion.pid = 99
    companion.returncode = None
    companion.wait_calls = 0

    def wait(timeout=None):
        del timeout
        companion.wait_calls += 1
        raise AssertionError("audio companion should not be waited on")

    def poll():
        return None

    def kill():
        companion.returncode = -9

    companion.wait = wait
    companion.poll = poll
    companion.kill = kill
    with (
        patch.object(final_export.subprocess, "Popen", side_effect=_popen),
        patch.object(final_export, "_process_memory_gb", return_value=(0.1, "rss")),
    ):
        final_export._run_segment_encode(
            ["ffmpeg", "-filter_complex_threads", "3", "-i", "clip.mp4"],
            companions=[(companion, "program audio")],
        )
    assert companion.wait_calls == 0
    assert [cmd[cmd.index("-filter_complex_threads") + 1] for cmd in popen.cmds] == ["3", "1"]


def test_frame_count_uses_header_only_after_segment_one_agrees() -> None:
    final_export._FRAME_COUNT_MODE = None
    assert final_export.decide_frame_probe(360, 360, None) == (360, "header")
    assert final_export.decide_frame_probe(359, 360, None) == (360, "count")
    assert final_export.decide_frame_probe(None, 360, None) == (360, "count")
    assert final_export.decide_frame_probe(360, None, "header") == (360, "header")
    assert final_export.decide_frame_probe(None, 12, "header") == (12, "count")
    path = Path("/tmp/seg.mp4")
    with (
        patch.object(final_export, "_header_nb_frames", return_value=360),
        patch.object(final_export, "_count_frames", return_value=360) as counted,
    ):
        assert final_export.probe_video_frames(path, first=True) == 360
        counted.assert_called_once()
    with (
        patch.object(final_export, "_header_nb_frames", return_value=360),
        patch.object(final_export, "_count_frames", side_effect=AssertionError("later segment should not decode")),
    ):
        assert final_export.probe_video_frames(path) == 360
    final_export._FRAME_COUNT_MODE = None
    with (
        patch.object(final_export, "_header_nb_frames", return_value=359),
        patch.object(final_export, "_count_frames", return_value=360) as counted,
    ):
        assert final_export.probe_video_frames(path, first=True) == 360
        assert final_export._FRAME_COUNT_MODE == "count"
    with (
        patch.object(final_export, "_header_nb_frames", return_value=359),
        patch.object(final_export, "_count_frames", return_value=360) as counted,
    ):
        assert final_export.probe_video_frames(path) == 360
        counted.assert_called_once()
    final_export._FRAME_COUNT_MODE = None


def test_wind_chain_keeps_every_wipe_frame() -> None:
    chain = final_export.wind_chain("src", "dst", 2 / 30, 1920, 1080, 30, "out")
    assert "trim=end_frame=2" in chain
    assert "fps=30,settb" not in chain
    assert chain.endswith("format=yuv420p[dst]")


def test_still_insert_loops_picture_and_feeds_silence() -> None:
    table = edl.empty_program("2026-01-02-demo")
    edl.set_source_sync(
        table,
        [{"clip": "2026-01-02-run-a.mp4", "fit": "run.fit", "offset_s": 0.0}],
    )
    edl.upsert_keeps(
        table,
        [
            {"clip": "2026-01-02-run-a.mp4", "src_start_s": 0.0, "src_end_s": 2.0},
            {"clip": "2026-01-02-run-b.mp4", "src_start_s": 0.0, "src_end_s": 2.0},
        ],
    )
    edl.add_insert(
        table,
        {
            "id": "card",
            "clip": "card.jpg",
            "src_start_s": 0.0,
            "src_end_s": 1.0,
            "after_id": table["program"][0]["id"],
            "transition": "cut",
        },
    )
    for seg in table["program"]:
        seg["hud"] = False
    video = final_export.program_input_args(Path("/media"), table, [])
    card = str(Path("/media") / "card.jpg")
    at = video.index(card)
    assert video[at - 7:at] == ["-loop", "1", "-framerate", "30", "-t", "1.000000", "-i"]
    assert "-ss" not in video[at - 7:at]
    audio = final_export.program_audio_input_args(Path("/media"), table)
    assert any(item.startswith("anullsrc=") for item in audio)
    assert card not in audio
    graph = final_export.build_program_audio_filter(table, apply_loudness=False)
    assert "[1:a]" in graph


def test_failed_segment_cleans_temp_files_and_partial_output() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media, episode = _stage(root, _table(partial=True), subs="done")
        plans = hud.plan_alpha_jobs(media, _table(partial=True), {"2026-01-02-run-a.mp4": 100.0})
        for plan in plans:
            plan["dest"].parent.mkdir(parents=True, exist_ok=True)
            plan["dest"].write_bytes(b"alpha")
        hud.write_alpha_manifest(media, edl.load_media(media), plans)
        final_export.write_loudness(media, edl.load_media(media), dict(MEASURED))
        out = media / "2026-01-02-run-final.mp4"
        dirs: list[Path] = []
        real = tempfile.TemporaryDirectory

        class _Dir(real):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                dirs.append(Path(self.name))

        def _popen(cmd, **_kwargs):
            out.write_bytes(b"partial")
            proc = type("Proc", (), {})()
            proc.args = list(cmd)
            proc.pid = 4242
            proc.returncode = None

            def wait(timeout=None):
                del timeout
                proc.returncode = 1
                return 1

            def poll():
                return proc.returncode

            def kill():
                proc.returncode = -9

            proc.wait = wait
            proc.poll = poll
            proc.kill = kill
            return proc

        from contextlib import ExitStack

        contexts = (
            patch.object(tempfile, "TemporaryDirectory", _Dir),
            patch.object(final_export.subprocess, "Popen", side_effect=_popen),
            patch.object(final_export, "_process_memory_gb", return_value=(0.1, "rss")),
            *_qc_ok(),
        )
        with ExitStack() as stack:
            for item in contexts:
                stack.enter_context(item)
            try:
                final_export.main(
                    [
                        "--media-dir", str(media),
                        "--episode-dir", str(episode),
                        "--out", str(out),
                        "--confirmed",
                    ]
                )
            except subprocess.CalledProcessError:
                pass
            else:
                raise AssertionError("encode failure should surface")
        assert dirs and all(not path.exists() for path in dirs)
        assert not out.exists()


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
    test_confirmed_input_plan_opens_shared_clip_once()
    test_rewound_source_opens_a_second_decoder()
    test_confirmed_command_opens_shared_run_once()
    test_confirmed_export_backfill_respects_jobs()
    test_segments_do_not_cut_wind_or_xfade_and_keep_inputs_small()
    test_segment_boundary_keeps_wind_and_xfade_intact()
    test_subtitle_times_are_local_on_each_side_of_a_cut()
    test_fast_init_failure_retries_once_with_one_filter_thread()
    test_memory_cap_kills_the_segment_without_retry()
    test_footprint_text_is_phys_footprint_in_gb()
    test_thread_retry_times_the_segment_not_its_audio_companion()
    test_frame_count_uses_header_only_after_segment_one_agrees()
    test_wind_chain_keeps_every_wipe_frame()
    test_still_insert_loops_picture_and_feeds_silence()
    test_failed_segment_cleans_temp_files_and_partial_output()
    print("ok")
