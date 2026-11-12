#!/usr/bin/env python3
"""统一规格、预览滤镜和最终导出门闩的纯 Python 自测。"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "assemble"))
sys.path.insert(0, str(ROOT.parent))

import assemble_episode as assemble
import final_export as final
from export_spec import (
    FINAL_SPEC,
    PREVIEW_SPEC,
    SPEC_PATH,
    audio_codec_args,
    load_export_specs,
    video_codec_args,
)

from tools.hud import render_running_hud as hud


def expect_exit(call, fragment: str) -> None:
    try:
        call()
    except SystemExit as exc:
        assert fragment in str(exc), (fragment, exc)
    else:
        raise AssertionError(f"expected SystemExit containing {fragment!r}")


def test_specs() -> None:
    assert (FINAL_SPEC.timeline.width, FINAL_SPEC.timeline.height, FINAL_SPEC.timeline.fps) == (1920, 1080, 30)
    assert FINAL_SPEC.vcodec == "hevc_videotoolbox"
    assert FINAL_SPEC.tag == "hvc1"
    assert audio_codec_args(FINAL_SPEC) == ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    assert video_codec_args(FINAL_SPEC) == ["-c:v", "hevc_videotoolbox", "-b:v", "28M", "-tag:v", "hvc1"]
    assert video_codec_args(FINAL_SPEC, test_codec="libx264") == ["-c:v", "libx264", "-preset", "veryfast"]
    assert video_codec_args(PREVIEW_SPEC) == ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    assert PREVIEW_SPEC.assembly == "concat-copy"
    assert FINAL_SPEC.assembly is None


def test_4k_timeline_loads_from_config() -> None:
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    payload["timeline"]["width"] = 3840
    payload["timeline"]["height"] = 2160
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export-spec.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        specs = load_export_specs(path)
    assert (specs["final"].timeline.width, specs["final"].timeline.height) == (3840, 2160)


def _sources(root: Path, *, run_name: str = "run-a.mp4") -> final.SourceSet:
    run = root / run_name
    return final.SourceSet(
        root / "open.mp4",
        (run,),
        root / "close.mp4",
        (root / f"{Path(run_name).stem}-hud-alpha.mov",),
        (root / "2026-01-01-stats-01.png",),
    )


def _done_assets(episode: Path, *, subs: str = "done") -> None:
    (episode / "assets.md").write_text(
        "## 制作状态\n- preview: done\n- qc: done\n- subs: " + subs + "\n",
        encoding="utf-8",
    )
    (episode / "subtitles.txt").write_text("0:00:00.00–0:00:01.00  hi\n", encoding="utf-8")


def test_final_gate_and_source_rejection() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        episode = root / "episode"
        episode.mkdir()
        sources = _sources(root)
        _done_assets(episode, subs="waiting-review")
        expect_exit(lambda: final.validate_gate(episode, episode / "subtitles.txt", False, sources), "confirmed")
        expect_exit(lambda: final.validate_gate(episode, episode / "subtitles.txt", True, sources), "subs: done")

        _done_assets(episode)
        expect_exit(
            lambda: final.validate_gate(episode, episode / "subtitles.txt", True, _sources(root, run_name="run-a-hud-preview.mp4")),
            "encoded preview",
        )
        preview_source = final.SourceSet(
            sources.open_clip, sources.runs, root / "2026-01-01-close-stats.mp4", sources.hud_alpha, sources.stats
        )
        expect_exit(
            lambda: final.validate_gate(episode, episode / "subtitles.txt", True, preview_source),
            "encoded preview",
        )
        expect_exit(
            lambda: final.validate_gate(
                episode,
                episode / "subtitles.txt",
                True,
                _sources(root, run_name="2026-01-01-run-final.mp4"),
            ),
            "run-final",
        )
        _done_assets(episode)
        final.validate_gate(episode, episode / "subtitles.txt", True, sources)


def test_final_discovery_rejects_legacy_close_stats() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        (media / "2026-01-01-run-a.mp4").touch()
        (media / "2026-01-01-close-stats.mp4").touch()
        expect_exit(lambda: final.discover_sources(media), "legacy preview only")


def test_preview_assembly_rejects_restack() -> None:
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    payload["preview"]["assembly"] = "restack"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export-spec.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            load_export_specs(path)
        except ValueError as exc:
            assert "concat-copy" in str(exc)
        else:
            raise AssertionError("restack assembly should be rejected")


def test_final_graph_still_composites_alpha_stats_and_transitions() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sources = final.SourceSet(
            root / "open.mp4",
            (root / "run-a.mp4", root / "run-b.mp4"),
            root / "close.mp4",
            (root / "run-a-hud-alpha.mov", root / "run-b-hud-alpha.mov"),
            (root / "2026-01-01-stats-01.png", root / "2026-01-01-stats-02.png"),
        )
        durations = [1.0, 2.0, 2.0, 2.0]
        final_plan = final.build_input_plan(sources, durations, FINAL_SPEC)
        ass = root / "subtitles.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        final_graph = final.build_filter_graph(sources, durations, final_plan, ass)
        for token in ("xfade=transition=fade:duration=0.2", "acrossfade=d=0.2", "dblur=angle=0:radius=46", "adelay="):
            assert token in final_graph, token
        assert "overlay=x=40" in final_graph and "stats" in final_graph
        assert all(str(path) in " ".join(final_plan.args) for path in (*sources.clips, *sources.hud_alpha, *sources.stats))
        assert f"fontsdir={final.escape_filter_path(final.SUBTITLE_FONTS_DIR)}" in final_graph
        assert final.SUBTITLE_FONT_FILE.name == "SourceHanSansSC-Heavy.otf"
        assert final.SUBTITLE_FONT_FILE.is_file()


def test_hud_preview_uses_export_profile() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with patch.object(hud, "run") as mocked:
            hud.bake_matched_preview(root / "run.mp4", root / "alpha.mov", root / "preview.mp4", dry_run=True)
        cmd = mocked.call_args.args[0]
        assert hud.video_codec_args(PREVIEW_SPEC) == cmd[cmd.index("-c:v") : cmd.index("-pix_fmt")]
        assert "-crf" in cmd and "23" in cmd




def test_audio_graph_uses_asetpts() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sources = _sources(root)
        durations = [2.0, 3.0, 3.0]
        plan = final.build_input_plan(sources, durations, FINAL_SPEC)
        graph = final.build_filter_graph(
            sources, durations, plan, ass=None, spec=FINAL_SPEC, apply_loudness=False
        )
        assert "asetpts=PTS-STARTPTS" in graph
        assert "atrim=0:" in graph
        for part in graph.split(";"):
            if "atrim=" in part:
                assert ",setpts=" not in part, part


def test_mid_timeline_overlay_in_final_graph_only() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        image = root / "still.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        (root / "overlays.json").write_text(
            json.dumps({"overlays": [{
                "file": "still.png",
                "start": 5,
                "hold_until": 8,
                "x": 48,
                "y": 120,
                "width": 560,
                "opacity": 0.95,
                "fade_in": 0.35,
                "fade_out": 0.35,
            }]}),
            encoding="utf-8",
        )
        sources = final.SourceSet(
            root / "open.mp4",
            (root / "run-a.mp4",),
            root / "close.mp4",
            (root / "run-a-hud-alpha.mov",),
            (root / "2026-01-01-stats-01.png",),
        )
        durations = [2.0, 10.0, 4.0]
        overlays = final.load_timeline_overlays(root, durations, has_open=True, has_close=True)
        assert len(overlays) == 1
        ov = overlays[0]
        assert ov["is_image"] and ov["t0"] == 5.0 and ov["t1"] == 8.0
        assert 1.8 < ov["t0"] < ov["t1"] < 11.6

        bare_plan = final.build_input_plan(sources, durations, FINAL_SPEC)
        bare_graph = final.build_filter_graph(sources, durations, bare_plan, ass=None, apply_loudness=False)
        assert "yuva420p" not in bare_graph

        for spec in (FINAL_SPEC, replace(FINAL_SPEC, timeline=replace(FINAL_SPEC.timeline, fps=24))):
            plan = final.build_input_plan(sources, durations, spec, overlays)
            graph = final.build_filter_graph(
                sources, durations, plan, ass=None, spec=spec, apply_loudness=False, overlays=overlays,
            )
            fps = spec.timeline.fps
            chain = (
                f"[{plan.overlay_indices[0]}:v]fps={fps},format=yuva420p,scale=560:-2,"
                "trim=duration=3.000000,fade=t=in:st=0:d=0.350:alpha=1,"
                "fade=t=out:st=2.650000:d=0.350:alpha=1,colorchannelmixer=aa=0.950,"
                "setpts=PTS-STARTPTS+5.000000/TB[ol0]"
            )
            assert chain in graph, graph
            assert "overlay=x=48:y=120:eof_action=pass:format=auto:enable='between(t,5.000000,8.000000)'[vov0]" in graph
            assert graph.rindex("xfade=") < graph.index(chain)
            assert graph.index(chain) < graph.index("format=yuv420p[v]")
            args = list(plan.args)
            image_at = args.index(str(ov["file"]))
            assert args[image_at - 7:image_at] == ["-loop", "1", "-framerate", str(fps), "-t", "3.000000", "-i"]
            if fps != 60:
                assert "fps=60,format=yuva420p" not in graph

        ass = root / "subtitles.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        final_plan = final.build_input_plan(sources, durations, FINAL_SPEC, overlays)
        final_graph = final.build_filter_graph(sources, durations, final_plan, ass, overlays=overlays)
        assert final_graph.index("scale=560:-2") < final_graph.index("subtitles=")
        assert "loudnorm=" in final_graph and "overlay=x=40" in final_graph
        assert video_codec_args(FINAL_SPEC) == ["-c:v", "hevc_videotoolbox", "-b:v", "28M", "-tag:v", "hvc1"]

        empty_plan = final.build_input_plan(sources, durations, FINAL_SPEC, [])
        assert bare_plan.args == empty_plan.args
        assert final.build_filter_graph(sources, durations, empty_plan, ass, overlays=[]) == final.build_filter_graph(
            sources, durations, bare_plan, ass
        )


def test_review_preview_rejected_as_source_and_overlay() -> None:
    names = (
        "2026-01-02-review-preview.mp4",
        "review-preview-with-shoes.mp4",
        "review-preview-fast.mp4",
    )
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        (media / "2026-01-02-run-a.mp4").touch()
        (media / "2026-01-02-run-review-preview.mp4").touch()
        (media / "2026-01-02-open-review-preview.mp4").touch()
        (media / "hud-renders").mkdir()
        (media / "hud-renders/2026-01-02-run-a-hud-alpha.mov").touch()
        (media / "hud-renders/2026-01-02-run-review-preview-hud-alpha.mov").touch()
        for name in names:
            (media / name).touch()
        sources = final.discover_sources(media)
        selected = [p.name for p in (*sources.clips, *sources.hud_alpha, *sources.stats)]
        assert selected == ["2026-01-02-run-a.mp4", "2026-01-02-run-a-hud-alpha.mov"]
        assert all("review-preview" not in name for name in selected)

        episode = media / "episode"
        episode.mkdir()
        _done_assets(episode)
        for name in names:
            bad = final.SourceSet(media / name, sources.runs, None, sources.hud_alpha, ())
            expect_exit(
                lambda bad=bad: final.validate_gate(episode, episode / "subtitles.txt", True, bad),
                "encoded preview",
            )
            (media / "overlays.json").write_text(
                json.dumps({"overlays": [{"file": name, "start": 1, "hold_until": 2}]}),
                encoding="utf-8",
            )
            expect_exit(
                lambda: final.load_timeline_overlays(media, [4.0], has_open=False, has_close=False),
                "review-preview",
            )


def test_final_rejects_intermediate_overlays_before_input_plan() -> None:
    bad_names = (
        "2026-01-01-run-a-hud-preview.mp4",
        "2026-01-01-close-stats.mp4",
        "2026-01-01-run-final.mp4",
        "2026-01-01-review-preview.mp4",
        "review-preview-with-shoes.mp4",
        "review-preview-fast.mp4",
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media = root / "2026-01-01-topic"
        episode = root / "episode"
        (media / "hud-renders").mkdir(parents=True)
        episode.mkdir()
        for name in (
            "2026-01-01-open.mp4",
            "2026-01-01-run-a.mp4",
            "2026-01-01-close.mp4",
            "2026-01-01-stats-01.png",
        ):
            (media / name).touch()
        (media / "hud-renders" / "2026-01-01-run-a-hud-alpha.mov").touch()
        _done_assets(episode)
        for name in bad_names:
            (media / name).write_bytes(b"intermediate")
            (media / "overlays.json").write_text(
                json.dumps({"overlays": [{"file": name, "start": 1, "hold_until": 2}]}),
                encoding="utf-8",
            )
            planned = {"hit": False}

            def fail_plan(*args, **kwargs):
                planned["hit"] = True
                raise AssertionError(f"build_input_plan should not run: {args} {kwargs}")

            with (
                patch.object(final, "probe_duration", return_value=3.0),
                patch.object(final, "build_input_plan", fail_plan),
            ):
                expect_exit(
                    lambda: final.main(
                        [
                            "--media-dir",
                            str(media),
                            "--episode-dir",
                            str(episode),
                            "--out",
                            str(root / "out.mp4"),
                            "--confirmed",
                            "--dry-run",
                        ]
                    ),
                    name,
                )
            assert planned["hit"] is False, name


def test_overlay_time_rejects_nonfinite_and_negative() -> None:
    bad_values = (
        -1,
        -0.5,
        float("nan"),
        float("inf"),
        float("-inf"),
        "nan",
        "inf",
        "-inf",
        "Infinity",
        "-1",
        "-1:00",
    )
    for bad in bad_values:
        try:
            assemble.parse_time(bad)
        except ValueError as exc:
            assert "finite" in str(exc), (bad, exc)
        else:
            raise AssertionError(f"accepted bad time {bad!r}")
    assert assemble.parse_time(0) == 0.0
    assert assemble.parse_time("0:00.0") == 0.0
    assert assemble.parse_time("5:50") == 350

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "still.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        cfg = root / "overlays.json"
        cases = (
            {"start": -1, "hold_until": 2},
            {"start": float("nan"), "hold_until": 2},
            {"start": float("inf"), "hold_until": 2},
            {"start": 1, "hold_until": float("nan")},
            {"start": 1, "hold_until": float("-inf")},
            {"start": "nan", "hold_until": 2},
            {"start": "-3", "hold_until": 2},
            {"start": 1, "hold_until": "inf"},
        )
        for raw_times in cases:
            cfg.write_text(
                json.dumps({"overlays": [{"file": "still.png", **raw_times}]}),
                encoding="utf-8",
            )
            expect_exit(lambda: assemble.load_overlays(cfg, root), "finite")

    nan_start = {"n": 1, "anchor": "final", "start": float("nan"), "until": 2.0, "is_image": True, "src_dur": None}
    expect_exit(lambda: assemble.resolve_overlays([nan_start], None, 10), "finite")
    inf_until = {"n": 1, "anchor": "final", "start": 1.0, "until": float("inf"), "is_image": False, "src_dur": 1.0}
    expect_exit(lambda: assemble.resolve_overlays([inf_until], None, 10), "finite")
    neg_dur = {"n": 1, "anchor": "final", "start": 1.0, "until": None, "is_image": False, "src_dur": float("-inf")}
    expect_exit(lambda: assemble.resolve_overlays([neg_dur], None, 10), "finite")
    slipped = {"n": 1, "anchor": "close", "start": -1.0, "until": 1.0, "is_image": True, "src_dur": None}
    expect_exit(lambda: assemble.resolve_overlays([slipped], 12.0, 20.0), "finite")
    ok = assemble.resolve_overlays(
        [{"n": 1, "anchor": "final", "start": 1, "until": 2, "is_image": True, "src_dur": None}],
        None,
        10,
    )[0]
    assert ok["t0"] == 1.0 and ok["t1"] == 2.0



def test_wind_and_xfade_snap_to_whole_frames() -> None:
    assert final.snap_frames(0.08, 30) == 2
    assert final.wind_frames(30) == 2
    assert final.format_frames(2, 30) == "0.066667"
    assert final.xfade_frames(30) == 6
    assert final.format_frames(6, 30) == "0.200000"
    # 24fps overlay tests already exist; 0.08s -> 2 frames there too
    assert final.wind_frames(24) == 2
    assert final.xfade_frames(24) == 5


def test_five_run_close_xfade_keeps_full_close() -> None:
    # 2026-11-12-8020 durations: 0.08s wind at 30fps used to shrink vpre by 0.4s,
    # so close xfade offset sat past the first input and close was dropped.
    durations = [86.4, 201.866667, 111.8, 113.4, 116.333333, 263.933333, 259.266667]
    vpre, close_at, total = final.pre_close_timeline(durations, True, True, 30)
    fade = final.xfade_frames(30)
    assert vpre == close_at + fade
    assert close_at == 26800
    assert vpre == 26806
    assert total == 34578
    assert abs(total / 30 - 1152.6) < 1e-9


def test_five_run_graph_uses_frame_aligned_winds() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runs = tuple(root / f"run-{name}.mp4" for name in "abcde")
        sources = final.SourceSet(
            root / "open.mp4",
            runs,
            root / "close.mp4",
            tuple(root / f"run-{name}-hud-alpha.mov" for name in "abcde"),
            (root / "2026-01-01-stats-01.png",),
        )
        durations = [86.4, 201.866667, 111.8, 113.4, 116.333333, 263.933333, 259.266667]
        plan = final.build_input_plan(sources, durations, FINAL_SPEC)
        graph = final.build_filter_graph(sources, durations, plan, ass=None, apply_loudness=False)
        assert "trim=duration=0.080000" not in graph
        assert "d=0.080000" not in graph
        assert "trim=duration=0.066667" in graph
        assert "xfade=transition=fade:duration=0.200000:offset=893.333333" in graph
        # first run out-only tail starts at (6056-2)/30
        assert "trim=start=201.800000" in graph


if __name__ == "__main__":
    test_specs()
    test_4k_timeline_loads_from_config()
    test_final_gate_and_source_rejection()
    test_final_discovery_rejects_legacy_close_stats()
    test_preview_assembly_rejects_restack()
    test_final_graph_still_composites_alpha_stats_and_transitions()
    test_hud_preview_uses_export_profile()
    test_audio_graph_uses_asetpts()
    test_mid_timeline_overlay_in_final_graph_only()
    test_review_preview_rejected_as_source_and_overlay()
    test_final_rejects_intermediate_overlays_before_input_plan()
    test_overlay_time_rejects_nonfinite_and_negative()
    test_wind_and_xfade_snap_to_whole_frames()
    test_five_run_close_xfade_keeps_full_close()
    test_five_run_graph_uses_frame_aligned_winds()
    print("ok test_export_spec")
