#!/usr/bin/env python3
"""统一规格、预览滤镜和最终导出门闩的纯 Python 自测。"""

from __future__ import annotations

import json
import sys
import tempfile
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


if __name__ == "__main__":
    test_specs()
    test_4k_timeline_loads_from_config()
    test_final_gate_and_source_rejection()
    test_final_discovery_rejects_legacy_close_stats()
    test_final_and_preview_share_transitions_and_stats_source()
    test_hud_preview_uses_export_profile()
    print("ok test_export_spec")
