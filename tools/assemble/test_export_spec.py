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

import final_export as final
import preview_episode as preview
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
        _done_assets(episode)
        final.validate_gate(episode, episode / "subtitles.txt", True, sources)


def test_final_discovery_rejects_legacy_close_stats() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        (media / "2026-01-01-run-a.mp4").touch()
        (media / "2026-01-01-close-stats.mp4").touch()
        expect_exit(lambda: final.discover_sources(media), "legacy preview only")


def test_final_and_preview_share_transitions_and_stats_source() -> None:
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
        preview_cmd = preview.build_command(sources, durations, root / "review-preview.mp4")
        preview_text = " ".join(preview_cmd)
        assert "hud-preview" not in preview_text and "close-stats" not in preview_text
        assert all(str(path) in preview_text for path in (*sources.clips, *sources.hud_alpha, *sources.stats))
        assert "-c:v libx264" in preview_text and "-crf 23" in preview_text

        preview_plan = final.build_input_plan(sources, durations, PREVIEW_SPEC)
        preview_graph = final.build_filter_graph(
            sources, durations, preview_plan, ass=None, spec=PREVIEW_SPEC, apply_loudness=False
        )
        final_plan = final.build_input_plan(sources, durations, FINAL_SPEC)
        ass = root / "subtitles.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        final_graph = final.build_filter_graph(sources, durations, final_plan, ass)
        for token in ("xfade=transition=fade:duration=0.2", "acrossfade=d=0.2", "dblur=angle=0:radius=46", "adelay="):
            assert token in preview_graph, token
            assert token in final_graph, token
        assert "overlay=x=40" in preview_graph and "stats" in preview_graph
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
        plan = final.build_input_plan(sources, durations, PREVIEW_SPEC)
        graph = final.build_filter_graph(
            sources, durations, plan, ass=None, spec=PREVIEW_SPEC, apply_loudness=False
        )
        assert "asetpts=PTS-STARTPTS" in graph
        assert "atrim=0:" in graph
        for part in graph.split(";"):
            if "atrim=" in part:
                assert ",setpts=" not in part, part


def _overlay_sources(root: Path) -> final.SourceSet:
    return final.SourceSet(
        root / "open.mp4",
        (root / "run-a.mp4",),
        root / "close.mp4",
        (root / "run-a-hud-alpha.mov",),
        (root / "2026-01-01-stats-01.png",),
    )


def test_mid_timeline_image_overlay_in_final_and_preview_graphs() -> None:
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
        sources = _overlay_sources(root)
        durations = [2.0, 10.0, 4.0]
        overlays = final.load_timeline_overlays(root, durations, has_open=True, has_close=True)
        assert len(overlays) == 1
        ov = overlays[0]
        assert ov["is_image"] and ov["t0"] == 5.0 and ov["t1"] == 8.0
        # open 叠化后 run 从 1.8s 开始，close 从 11.6s 开始；静帧落在跑中。
        assert 1.8 < ov["t0"] < ov["t1"] < 11.6

        specs = (
            FINAL_SPEC,
            PREVIEW_SPEC,
            replace(FINAL_SPEC, timeline=replace(FINAL_SPEC.timeline, fps=24)),
        )
        for spec in specs:
            plan = final.build_input_plan(sources, durations, spec, overlays)
            graph = final.build_filter_graph(
                sources, durations, plan, ass=None, spec=spec, apply_loudness=False, overlays=overlays,
            )
            fps = spec.timeline.fps
            assert plan.overlay_indices
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

        preview_cmd = preview.build_command(sources, durations, root / "review-preview.mp4", media_dir=root)
        preview_text = " ".join(preview_cmd)
        assert str(ov["file"]) in preview_text
        assert f"fps={PREVIEW_SPEC.timeline.fps},format=yuva420p,scale=560:-2" in preview_text
        assert "colorchannelmixer=aa=0.950" in preview_text
        assert "enable='between(t,5.000000,8.000000)'" in preview_text
        assert "subtitles=" not in preview_text
        assert "loudnorm=" not in preview_text

        ass = root / "subtitles.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        final_plan = final.build_input_plan(sources, durations, FINAL_SPEC, overlays)
        final_graph = final.build_filter_graph(sources, durations, final_plan, ass, overlays=overlays)
        assert "scale=560:-2" in final_graph and "colorchannelmixer=aa=0.950" in final_graph
        assert final_graph.index("scale=560:-2") < final_graph.index("subtitles=")
        assert "loudnorm=" in final_graph and "overlay=x=40" in final_graph

        two = final.SourceSet(
            sources.open_clip,
            (root / "run-a.mp4", root / "run-b.mp4"),
            sources.close_clip,
            (root / "run-a-hud-alpha.mov", root / "run-b-hud-alpha.mov"),
            sources.stats,
        )
        longer = [2.0, 6.0, 6.0, 4.0]
        bare = final.build_input_plan(two, longer, FINAL_SPEC)
        covered = final.build_input_plan(two, longer, FINAL_SPEC, overlays)
        assert bare.whoosh_index is not None
        assert covered.whoosh_index == bare.whoosh_index
        assert covered.overlay_indices == (bare.whoosh_index + 1,)

        close_cfg = root / "close-anchor.json"
        close_cfg.write_text(
            json.dumps({"overlays": [{
                "file": "still.png",
                "anchor": "close",
                "start": 0.4,
                "hold_until": 1.4,
                "x": "W-w-48",
                "y": "(H-h)/2",
                "width": 560,
                "opacity": 0.95,
            }]}),
            encoding="utf-8",
        )
        close_ov = final.load_timeline_overlays(
            root, durations, has_open=True, has_close=True, explicit=str(close_cfg),
        )
        assert abs(close_ov[0]["t0"] - 12.0) < 1e-9 and abs(close_ov[0]["t1"] - 13.0) < 1e-9
        close_plan = final.build_input_plan(sources, durations, FINAL_SPEC, close_ov)
        close_graph = final.build_filter_graph(
            sources, durations, close_plan, ass=None, spec=FINAL_SPEC, apply_loudness=False, overlays=close_ov,
        )
        assert "overlay=x=W-w-48:y=(H-h)/2:" in close_graph
        assert "enable='between(t,12.000000,13.000000)'" in close_graph


def test_no_overlays_json_leaves_filter_graph_unchanged() -> None:
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
        assert final.load_timeline_overlays(root, durations, has_open=True, has_close=True) == []
        bare_plan = final.build_input_plan(sources, durations, FINAL_SPEC)
        empty_plan = final.build_input_plan(sources, durations, FINAL_SPEC, [])
        assert bare_plan.args == empty_plan.args
        assert bare_plan.whoosh_index == empty_plan.whoosh_index
        assert bare_plan.overlay_indices == ()
        ass = root / "subtitles.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        bare = final.build_filter_graph(sources, durations, bare_plan, ass)
        empty = final.build_filter_graph(sources, durations, empty_plan, ass, overlays=[])
        assert bare == empty
        assert "yuva420p" not in bare and "vov0" not in bare
        for token in (
            "xfade=transition=fade:duration=0.2",
            "acrossfade=d=0.2",
            "dblur=angle=0:radius=46",
            "overlay=x=40",
            "subtitles=",
            "loudnorm=",
        ):
            assert token in bare, token
        preview_bare = preview.build_command(sources, durations, root / "review-preview.mp4")
        preview_empty = preview.build_command(sources, durations, root / "review-preview.mp4", media_dir=root)
        assert preview_bare == preview_empty
        assert "yuva420p" not in " ".join(preview_bare)


if __name__ == "__main__":
    test_specs()
    test_4k_timeline_loads_from_config()
    test_final_gate_and_source_rejection()
    test_final_discovery_rejects_legacy_close_stats()
    test_final_and_preview_share_transitions_and_stats_source()
    test_hud_preview_uses_export_profile()
    test_audio_graph_uses_asetpts()
    test_mid_timeline_image_overlay_in_final_and_preview_graphs()
    test_no_overlays_json_leaves_filter_graph_unchanged()
    print("ok test_export_spec")
