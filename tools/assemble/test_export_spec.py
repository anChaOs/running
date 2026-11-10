#!/usr/bin/env python3
"""统一规格和最终导出门闩的纯 Python 自测。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "assemble"))

from export_spec import FINAL_SPEC, PREVIEW_SPEC, audio_codec_args, video_codec_args  # noqa: E402
import final_export as final  # noqa: E402


def test_specs() -> None:
    assert (FINAL_SPEC.timeline.width, FINAL_SPEC.timeline.height, FINAL_SPEC.timeline.fps) == (1920, 1080, 30)
    assert FINAL_SPEC.vcodec == "hevc_videotoolbox"
    assert FINAL_SPEC.tag == "hvc1"
    assert audio_codec_args(FINAL_SPEC) == ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    assert video_codec_args(FINAL_SPEC) == ["-c:v", "hevc_videotoolbox", "-b:v", "28M", "-tag:v", "hvc1"]
    assert video_codec_args(FINAL_SPEC, test_codec="libx264") == ["-c:v", "libx264", "-preset", "veryfast"]
    assert PREVIEW_SPEC.vcodec == "libx264"


def test_final_gate_and_source_rejection() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media = root / "media"
        episode = root / "episode"
        media.mkdir()
        episode.mkdir()
        (episode / "assets.md").write_text("## 制作状态\n- subs: waiting-review\n- qc: done\n", encoding="utf-8")
        (episode / "subtitles.txt").write_text("0:00:00.00–0:00:01.00  hi\n", encoding="utf-8")
        for name in ("2026-01-01-run-a.mp4", "2026-01-01-run-a-hud-preview.mp4"):
            (media / name).touch()
        sources = final.SourceSet(None, (media / "2026-01-01-run-a.mp4",), None, (), ())
        try:
            final.validate_gate(episode, episode / "subtitles.txt", False, sources)
        except SystemExit as exc:
            assert "confirmed" in str(exc)
        else:
            raise AssertionError("missing confirmation must fail")


def test_final_filter_and_command() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subtitle = root / "subtitles.ass"
        subtitle.write_text("[Script Info]\n", encoding="utf-8")
        sources = final.SourceSet(
            root / "open.mp4",
            (root / "run-a.mp4",),
            root / "close.mp4",
            (root / "run-a-hud-alpha.mov",),
            (root / "2026-01-01-stats-01.png",),
        )
        plan = final.InputPlan(
            args=("-i", "open.mp4", "-i", "run-a.mp4", "-i", "close.mp4", "-i", "run-a-hud-alpha.mov", "-i", "stats.png"),
            clip_count=3,
            alpha_indices=(3,),
            stats_indices=(4,),
            stats_duration=2.0,
        )
        graph = final.build_filter_graph(sources, [1.0, 2.0, 2.0], plan, subtitle)
        assert "overlay" in graph and "subtitles=" in graph and "loudnorm=" in graph
        assert "stats" in graph
        cmd = final.build_encode_cmd(plan, graph, root / "final.mp4", test_codec="libx264")
        assert cmd.count("-c:v") == 1
        assert "-c:a" in cmd and "libx264" in cmd
        assert all("hud-preview" not in value and "close-stats" not in value for value in cmd)


if __name__ == "__main__":
    test_specs()
    test_final_gate_and_source_rejection()
    test_final_filter_and_command()
    print("ok test_export_spec")
