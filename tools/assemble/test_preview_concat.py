#!/usr/bin/env python3
"""审片预览拼接自测。合成短片，不依赖真实素材。"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import final_export as final
import preview_episode as preview
from export_spec import FINAL_SPEC, PREVIEW_SPEC, SPEC_PATH


D = "2026-01-02"


def expect_exit(call, fragment: str) -> None:
    try:
        call()
    except SystemExit as exc:
        assert fragment in str(exc), (fragment, exc)
    else:
        raise AssertionError(f"expected SystemExit containing {fragment!r}")


def stream(**overrides: object) -> preview.StreamInfo:
    base: dict[str, object] = dict(
        vcodec="h264",
        width=320,
        height=240,
        pix_fmt="yuv420p",
        fps=30.0,
        profile="high",
        sar="1:1",
        acodec="aac",
        sample_rate=48000,
        channels=2,
        n_streams=2,
        n_video=1,
        n_audio=1,
    )
    base.update(overrides)
    if "fps_rate" not in base:
        base["fps_rate"] = preview._rate_key(float(base["fps"]))
    return preview.StreamInfo(**base)  # type: ignore[arg-type]


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error", *args], check=True)


def write_clip(
    path: Path,
    *,
    color: str,
    dur: float,
    size: str = "320x240",
    fps: int = 30,
    sample_rate: int = 48000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ff(
        "-f", "lavfi", "-i", f"color=c={color}:s={size}:r={fps}:d={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={sample_rate}:duration={dur}",
        "-t", f"{dur}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-ar", str(sample_rate), "-ac", "2",
        str(path),
    )


def probe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True,
    ).strip()
    return float(raw)


def probe_fps(path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", str(path),
        ],
        text=True,
    ).strip()
    num, den = raw.split("/")
    return float(num) / float(den)


def probe_size(path: Path) -> tuple[int, int]:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        text=True,
    ).strip()
    width, height = raw.split(",")
    return int(width), int(height)


def stream_types(path: Path) -> list[str]:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        text=True,
    )
    return [stream["codec_type"] for stream in json.loads(raw)["streams"]]


def pixel(video: Path, t: float, x: int, y: int) -> tuple[int, int, int]:
    raw = subprocess.check_output(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
            "-vf", f"crop=4:4:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ]
    )
    return raw[0], raw[1], raw[2]


def is_color(px: tuple[int, int, int], name: str) -> bool:
    red, green, blue = px
    return {
        "red": red > 180 and green < 80 and blue < 80,
        "blue": blue > 180 and red < 80 and green < 80,
        "yellow": red > 180 and green > 180 and blue < 80,
        "green": green > 100 and red < 80 and blue < 80,
    }[name]


def run_preview(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = preview.main(argv)
    return code, buf.getvalue()


def test_preview_source_has_no_restack_path() -> None:
    text = Path(preview.__file__).read_text(encoding="utf-8")
    assert "build_filter_graph" not in text
    assert "build_encode_cmd" not in text
    final_text = Path(final.__file__).read_text(encoding="utf-8")
    assert "def build_filter_graph" in final_text
    assert "def discover_sources" in final_text
    assert "FINAL_SPEC" in final_text
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["final"]["vcodec"] == "hevc_videotoolbox"
    assert spec["final"]["bitrate"] == "28M"
    assert spec["final"]["tag"] == "hvc1"
    assert spec["final"]["abitrate"] == "192k"
    assert spec["timeline"]["fps"] == 30
    assert spec["timeline"]["width"] == 1920
    assert spec["preview"]["assembly"] == "concat-copy"
    assert spec["preview"]["vcodec"] == "libx264"
    assert spec["preview"]["preset"] == "veryfast"
    assert spec["preview"]["crf"] == 23
    assert (FINAL_SPEC.vcodec, FINAL_SPEC.bitrate, FINAL_SPEC.tag, FINAL_SPEC.abitrate) == (
        "hevc_videotoolbox", "28M", "hvc1", "192k",
    )
    assert PREVIEW_SPEC.assembly == "concat-copy"
    assert FINAL_SPEC.assembly is None


def test_matching_plan_stream_copies_without_filtergraph() -> None:
    segments = [
        Path("/media/2026-01-02-open.mp4"),
        Path("/media/hud-renders/2026-01-02-run-a-hud-preview.mp4"),
        Path("/media/2026-01-02-close.mp4"),
    ]
    info = stream()
    plan = preview.plan_preview(segments, [info, info, info], [1.0, 8.0, 2.0])
    assert [action.mode for action in plan.actions] == ["copy", "copy", "copy"]
    commands = preview.commands_for_plan(plan, [info, info, info], Path("/media/out.mp4"), Path("/tmp/work"))
    assert len(commands) == 1
    concat = commands[0]
    assert concat[concat.index("-c") + 1] == "copy"
    flat = " ".join(concat)
    assert "filter_complex" not in flat and "overlay" not in flat and "hud-alpha" not in flat
    text = preview.format_plan(plan)
    assert "concat=-c copy" in text
    assert "hud-renders/2026-01-02-run-a-hud-preview.mp4" in text
    assert "/media/2026-01-02-open.mp4" in text
    assert abs(plan.expected_duration - 11.0) < 1e-9


def test_mismatch_transcodes_only_the_outlier() -> None:
    small = stream(width=160, height=120)
    big = stream()
    segments = [
        Path("/media/2026-01-02-open.mp4"),
        Path("/media/hud-renders/2026-01-02-run-a-hud-preview.mp4"),
    ]
    plan = preview.plan_preview(segments, [small, big], [0.4, 6.0])
    assert plan.actions[0].mode == "transcode"
    assert plan.actions[0].video == "encode"
    assert plan.actions[1].mode == "copy"
    assert plan.target.width == 320 and plan.target.height == 240
    infos = [small, big]
    commands = preview.commands_for_plan(plan, infos, Path("/media/out.mp4"), Path("/tmp/work"))
    assert len(commands) == 2
    transcode = " ".join(commands[0])
    assert "libx264" in transcode and "overlay" not in transcode and "filter_complex" not in transcode
    assert "hud-alpha" not in transcode
    assert commands[1][commands[1].index("-c") + 1] == "copy"
    inputs = preview.concat_inputs(plan, Path("/tmp/work"))
    assert inputs[1] == segments[1]
    assert inputs[0].name.endswith("-norm.mp4")
    assert "run-a.mp4" not in inputs[0].name


def test_non_30fps_is_not_stream_copied() -> None:
    fast = stream(fps=60.0)
    segments = [Path("/media/hud-renders/a-hud-preview.mp4"), Path("/media/hud-renders/b-hud-preview.mp4")]
    plan = preview.plan_preview(segments, [fast, fast], [2.0, 3.0])
    assert plan.target.fps == 30.0
    assert all(action.mode == "transcode" and "fps" in action.reason for action in plan.actions)
    cmd = " ".join(preview.commands_for_plan(plan, [fast, fast], Path("/out.mp4"), Path("/tmp/work"))[0])
    assert "fps=30" in cmd and "-r 30" in cmd
    assert "overlay" not in cmd


def test_extra_streams_are_remuxed_not_reencoded() -> None:
    clean = stream()
    messy = stream(n_streams=3, n_audio=2)
    segments = [Path("/media/open.mp4"), Path("/media/hud-renders/run-a-hud-preview.mp4")]
    plan = preview.plan_preview(segments, [messy, clean], [1.0, 5.0])
    assert plan.actions[0].mode == "remux"
    assert plan.actions[0].video == "copy" and plan.actions[0].audio == "copy"
    assert plan.actions[1].mode == "copy"
    cmd = preview.commands_for_plan(plan, [messy, clean], Path("/out.mp4"), Path("/tmp/work"))[0]
    assert "-c" in cmd and "copy" in cmd
    assert "libx264" not in cmd
    assert cmd[cmd.index("-map") + 1] == "0:v:0"


def test_long_hevc_open_does_not_reencode_h264_preview() -> None:
    hevc = stream(vcodec="hevc", profile="main")
    h264 = stream()
    segments = [Path("/media/open.mp4"), Path("/media/hud-renders/run-a-hud-preview.mp4")]
    plan = preview.plan_preview(segments, [hevc, h264], [30.0, 5.0])
    assert plan.target.vcodec == "h264"
    assert plan.actions[0].mode == "transcode" and plan.actions[0].video == "encode"
    assert plan.actions[1].mode == "copy"
    cmd = " ".join(preview.commands_for_plan(plan, [hevc, h264], Path("/out.mp4"), Path("/tmp/work"))[0])
    assert "libx264" in cmd and "overlay" not in cmd and "filter_complex" not in cmd


def test_long_h264_open_does_not_outrank_hud_previews() -> None:
    """A longer yuv420p 30/1 open must not become the copy target over HUD previews."""
    ntsc = 30000 / 1001
    boundary = stream(pix_fmt="yuv420p", fps=30.0, profile="high")
    hud = stream(pix_fmt="yuvj420p", fps=ntsc, profile="high")
    segments = [
        Path("/media/2026-01-02-open.mp4"),
        Path("/media/hud-renders/2026-01-02-run-a-hud-preview.mp4"),
        Path("/media/hud-renders/2026-01-02-run-b-hud-preview.mp4"),
        Path("/media/2026-01-02-close.mp4"),
    ]
    plan = preview.plan_preview(
        segments, [boundary, hud, hud, boundary], [500.0, 40.0, 40.0, 200.0],
    )
    assert plan.target.pix_fmt == "yuvj420p"
    assert plan.target.vcodec == "h264"
    assert plan.target.fps_rate == "30000/1001"
    assert abs(plan.target.fps - ntsc) <= 0.001
    assert [action.mode for action in plan.actions] == ["transcode", "copy", "copy", "transcode"]
    assert "yuv420p!=yuvj420p" in plan.actions[0].reason
    assert "30.000!=29.970" in plan.actions[0].reason
    assert plan.actions[1].source.name.endswith("-hud-preview.mp4")
    assert plan.actions[2].mode == "copy"


def test_phone_full_range_ntsc_hud_previews_are_copied() -> None:
    """yuvj420p + 30000/1001 HUD previews stay copy. HEVC 30/1 open/close transcode onto them."""
    ntsc = 30000 / 1001
    assert preview._is_30(ntsc)
    assert not preview._rates_match(30.0, ntsc)
    hud = stream(pix_fmt="yuvj420p", fps=ntsc, profile="high")
    hevc = stream(vcodec="hevc", pix_fmt="yuvj420p", fps=30.0, profile="main")
    segments = [
        Path("/media/2026-01-02-open.mp4"),
        Path("/media/hud-renders/2026-01-02-run-a-hud-preview.mp4"),
        Path("/media/hud-renders/2026-01-02-run-b-hud-preview.mp4"),
        Path("/media/2026-01-02-close.mp4"),
    ]
    infos = [hevc, hud, hud, hevc]
    durations = [12.0, 300.0, 400.0, 20.0]
    plan = preview.plan_preview(
        segments, infos, durations, has_open=True, has_close=True,
    )
    assert [action.mode for action in plan.actions] == ["transcode", "copy", "copy", "transcode"]
    assert plan.target.pix_fmt == "yuvj420p"
    assert plan.target.vcodec == "h264"
    assert plan.target.fps_rate == "30000/1001"
    assert abs(plan.target.fps - ntsc) <= 0.001
    assert plan.actions[0].trim_end == preview.XFADE and plan.actions[0].trim_start == 0
    assert plan.actions[1].trim_start == 0 and plan.actions[1].trim_end == 0
    assert plan.actions[2].trim_start == 0 and plan.actions[2].trim_end == 0
    assert plan.actions[3].trim_start == preview.XFADE and plan.actions[3].trim_end == 0
    assert "29.970" in plan.actions[0].reason
    assert "yuv420p" not in plan.actions[0].reason
    assert abs(plan.expected_duration - (sum(durations) - 2 * preview.XFADE)) < 1e-9
    commands = preview.commands_for_plan(plan, infos, Path("/tmp/out.mp4"), Path("/tmp/work"))
    assert len(commands) == 3
    open_cmd = " ".join(commands[0])
    close_cmd = " ".join(commands[1])
    assert "-pix_fmt yuvj420p" in open_cmd and "-pix_fmt yuvj420p" in close_cmd
    assert "-r 30000/1001" in open_cmd and "fps=30000/1001" in open_cmd
    assert "trim=start=0.000000" in open_cmd
    assert "trim=start=0.200000" in close_cmd
    assert "-pix_fmt yuv420p" not in open_cmd and "-r 30/1" not in open_cmd
    encoded = open_cmd + " " + close_cmd
    assert "run-a-hud-preview" not in encoded and "run-b-hud-preview" not in encoded
    assert commands[2][commands[2].index("-c") + 1] == "copy"


def test_xfade_trim_does_not_reencode_matching_middle_segments() -> None:
    info = stream()
    segments = [
        Path("/media/open.mp4"),
        Path("/media/hud-renders/run-a-hud-preview.mp4"),
        Path("/media/hud-renders/run-b-hud-preview.mp4"),
        Path("/media/close.mp4"),
    ]
    plan = preview.plan_preview(
        segments, [info, info, info, info], [2.0, 8.0, 9.0, 3.0], has_open=True, has_close=True,
    )
    assert [action.mode for action in plan.actions] == ["transcode", "copy", "copy", "transcode"]
    assert plan.actions[1].trim_start == plan.actions[1].trim_end == 0
    assert abs(plan.expected_duration - (22.0 - 2 * preview.XFADE)) < 1e-9
    encoded = " ".join(" ".join(cmd) for cmd in preview.commands_for_plan(
        plan, [info, info, info, info], Path("/out.mp4"), Path("/tmp/work"),
    ))
    assert "run-a-hud-preview" not in encoded and "run-b-hud-preview" not in encoded
    assert "xfade trim tail" in preview.format_plan(plan)


def test_audio_mismatch_copies_video() -> None:
    phone = stream(sample_rate=44100)
    hud = stream()
    segments = [Path("/media/open.mp4"), Path("/media/hud-renders/run-a-hud-preview.mp4")]
    plan = preview.plan_preview(segments, [phone, hud], [1.0, 10.0])
    assert plan.actions[0].video == "copy" and plan.actions[0].audio == "encode"
    assert plan.actions[1].mode == "copy"
    cmd = " ".join(preview.commands_for_plan(plan, [phone, hud], Path("/out.mp4"), Path("/tmp/work"))[0])
    assert "-c:v copy" in cmd
    assert "libx264" not in cmd
    assert "-c:a aac" in cmd and "-ar 48000" in cmd


def test_larger_frame_wins_a_duration_tie() -> None:
    small = stream(width=160, height=120)
    big = stream()
    segments = [Path("/a-open.mp4"), Path("/hud-renders/a-run-a-hud-preview.mp4")]
    plan = preview.plan_preview(segments, [small, big], [2.0, 2.0])
    assert plan.target.width == 320
    assert plan.actions[0].mode == "transcode"
    assert plan.actions[1].mode == "copy"


def test_reject_final_paths() -> None:
    expect_exit(lambda: preview.reject_preview_output(Path("/tmp/upload/x.mp4")), "upload")
    expect_exit(lambda: preview.reject_preview_output(Path("/tmp/2026-01-02-run-final.mp4")), "run-final")


def test_missing_hud_preview_fails_without_restack() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        (media / "hud-renders").mkdir()
        (media / f"{D}-run-a.mp4").touch()
        (media / f"{D}-run-b.mp4").touch()
        (media / "hud-renders" / f"{D}-run-a-hud-preview.mp4").touch()
        (media / "hud-renders" / f"{D}-run-b-hud-preview-raw.mp4").touch()
        (media / "hud-renders" / f"{D}-run-a-hud-alpha.mov").touch()

        def call() -> None:
            with patch.object(final, "build_filter_graph", side_effect=AssertionError("restack")):
                preview.discover_preview_cut(media)

        try:
            call()
        except SystemExit as exc:
            message = str(exc)
            assert f"{D}-run-b-hud-preview.mp4" in message
            assert "does not restack" in message
            assert "run-b-hud-preview-raw" not in message
        else:
            raise AssertionError("missing HUD preview should fail")


def test_missing_close_stats_fails_without_restack() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        (media / "hud-renders").mkdir()
        (media / f"{D}-run-a.mp4").touch()
        (media / "hud-renders" / f"{D}-run-a-hud-preview.mp4").touch()
        (media / f"{D}-close.mp4").touch()
        (media / f"{D}-stats-01.png").touch()
        expect_exit(lambda: preview.discover_preview_cut(media), "overlay_close_stats.py")
        expect_exit(lambda: preview.discover_preview_cut(media), "does not restack")


def test_leftover_close_stats_without_stills_uses_raw_close() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        (media / f"{D}-run-a.mp4").touch()
        (hud / f"{D}-run-a-hud-preview.mp4").touch()
        raw = media / f"{D}-close.mp4"
        leftover = media / f"{D}-close-stats.mp4"
        raw.touch()
        leftover.touch()
        cut = preview.discover_preview_cut(media)
        assert cut.close_clip == raw
        assert leftover not in cut.segments
        plan = preview.plan_preview(
            cut.segments,
            [stream(), stream()],
            [4.0, 2.0],
            has_close=cut.close_clip is not None,
        )
        assert [path.name for path in cut.segments] == [
            f"{D}-run-a-hud-preview.mp4",
            f"{D}-close.mp4",
        ]
        assert plan.actions[-1].source == raw
        assert "close-stats" not in plan.actions[-1].source.name
        raw.unlink()
        expect_exit(lambda: preview.discover_preview_cut(media), "not a preview segment")
        expect_exit(lambda: preview.discover_preview_cut(media), leftover.name)


def test_orphan_preview_is_not_a_segment() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        (media / f"{D}-run-a.mp4").touch()
        (hud / f"{D}-run-a-hud-preview.mp4").touch()
        (hud / f"{D}-run-z-hud-preview.mp4").touch()
        cut = preview.discover_preview_cut(media)
        assert [path.name for path in cut.runs] == [f"{D}-run-a-hud-preview.mp4"]


def _layout(media: Path) -> dict[str, Path]:
    hud = media / "hud-renders"
    hud.mkdir()
    paths = {
        "open": media / f"{D}-open.mp4",
        "run_original": media / f"{D}-run-a.mp4",
        "alpha": hud / f"{D}-run-a-hud-alpha.mov",
        "preview": hud / f"{D}-run-a-hud-preview.mp4",
        "close": media / f"{D}-close.mp4",
        "out": media / f"{D}-review-preview.mp4",
    }
    return paths


def test_concat_copy_keeps_duration_fps_and_pictures() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        paths = _layout(media)
        write_clip(paths["open"], color="blue", dur=1.0)
        write_clip(paths["run_original"], color="green", dur=1.2)
        write_clip(paths["alpha"], color="green", dur=1.2)
        write_clip(paths["preview"], color="red", dur=1.2)
        write_clip(paths["close"], color="yellow", dur=1.0)
        subs = media / "subtitles.txt"
        subs.write_text("0:00:00.00–0:00:01.00  开头\n", encoding="utf-8")
        argv = ["--media-dir", str(media), "--out", str(paths["out"]), "--subtitles", str(subs)]

        with patch.object(final, "build_filter_graph", side_effect=AssertionError("restack")):
            code, text = run_preview([*argv, "--dry-run"])
        assert code == 0
        assert not paths["out"].exists()
        assert not paths["out"].with_suffix(".srt").exists()
        assert "concat=-c copy" in text
        assert f"copy {paths['preview']}" in text
        assert f"transcode {paths['open']}" in text and "xfade trim tail" in text
        assert f"transcode {paths['close']}" in text and "xfade trim head" in text
        assert "filter_complex" not in text and "overlay" not in text
        assert str(paths["preview"]) in text
        assert str(paths["run_original"]) not in text
        assert str(paths["alpha"]) not in text
        assert "hud-alpha" not in text

        with patch.object(final, "build_filter_graph", side_effect=AssertionError("restack")):
            code, text = run_preview(argv)
        assert code == 0, text
        expected = (
            probe_duration(paths["open"])
            + probe_duration(paths["preview"])
            + probe_duration(paths["close"])
            - 2 * preview.XFADE
        )
        actual = probe_duration(paths["out"])
        assert abs(actual - expected) <= preview.duration_slack(3), (actual, expected)
        assert abs(probe_fps(paths["out"]) - 30) <= 0.02
        assert probe_size(paths["out"]) == (320, 240)
        assert set(stream_types(paths["out"])) == {"video", "audio"}
        open_out = probe_duration(paths["open"]) - preview.XFADE
        run_d = probe_duration(paths["preview"])
        checks = [
            (0.2, "blue"),
            (open_out - 0.08, "blue"),
            (open_out + 0.15, "red"),
            (open_out + run_d + 0.15, "yellow"),
        ]
        for t, color in checks:
            px = pixel(paths["out"], t, 30, 30)
            assert is_color(px, color), (t, color, px)
        srt = paths["out"].with_suffix(".srt").read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:01,000" in srt
        assert "开头" in srt


def test_outlier_is_light_transcoded_and_duration_holds() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        paths = _layout(media)
        write_clip(paths["open"], color="blue", dur=0.6, size="160x120")
        write_clip(paths["run_original"], color="green", dur=1.2)
        write_clip(paths["preview"], color="red", dur=1.2)
        write_clip(paths["close"], color="yellow", dur=0.8)
        with patch.object(final, "build_filter_graph", side_effect=AssertionError("restack")):
            code, text = run_preview(["--media-dir", str(media), "--out", str(paths["out"])])
        assert code == 0, text
        assert f"transcode {paths['open']}" in text
        assert f"copy {paths['preview']}" in text
        assert f"transcode {paths['close']}" in text and "xfade trim head" in text
        assert str(paths["run_original"]) not in text
        assert "overlay" not in text and "filter_complex" not in text
        assert probe_size(paths["out"]) == (320, 240)
        assert abs(probe_fps(paths["out"]) - 30) <= 0.02
        expected = sum(probe_duration(paths[name]) for name in ("open", "preview", "close")) - 2 * preview.XFADE
        actual = probe_duration(paths["out"])
        assert abs(actual - expected) <= preview.duration_slack(3), (actual, expected)
        open_out = probe_duration(paths["open"]) - preview.XFADE
        run_d = probe_duration(paths["preview"])
        for t, color in ((0.15, "blue"), (open_out + 0.15, "red"), (open_out + run_d + 0.15, "yellow")):
            px = pixel(paths["out"], t, 80, 60)
            assert is_color(px, color), (t, color, px)


def test_sixty_fps_sources_become_thirty() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        run = media / f"{D}-run-a.mp4"
        preview_path = hud / f"{D}-run-a-hud-preview.mp4"
        close = media / f"{D}-close.mp4"
        out = media / f"{D}-review-preview.mp4"
        write_clip(run, color="green", dur=0.5, fps=60)
        write_clip(preview_path, color="red", dur=0.5, fps=60)
        write_clip(close, color="blue", dur=0.5, fps=60)
        code, text = run_preview(["--media-dir", str(media), "--out", str(out)])
        assert code == 0, text
        assert "fps" in text and "transcode" in text
        assert str(run) not in text
        assert abs(probe_fps(out) - 30) <= 0.02
        assert is_color(pixel(out, 0.15, 30, 30), "red")
        expected = probe_duration(preview_path) + probe_duration(close) - preview.XFADE
        actual = probe_duration(out)
        assert abs(actual - expected) <= preview.duration_slack(2), (actual, expected)


def test_close_stats_is_the_data_segment() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        (media / f"{D}-run-a.mp4").touch()
        preview_path = hud / f"{D}-run-a-hud-preview.mp4"
        close = media / f"{D}-close.mp4"
        stats = media / f"{D}-close-stats.mp4"
        image = media / f"{D}-stats-01.png"
        out = media / f"{D}-review-preview.mp4"
        write_clip(preview_path, color="red", dur=0.8)
        write_clip(close, color="green", dur=0.8)
        write_clip(stats, color="blue", dur=0.8)
        ff("-f", "lavfi", "-i", "color=c=white:s=32x32", "-frames:v", "1", str(image))
        code, text = run_preview(["--media-dir", str(media), "--out", str(out)])
        assert code == 0, text
        assert str(stats) in text
        assert str(close) not in text
        assert abs(probe_fps(out) - 30) <= 0.02
        px = pixel(out, probe_duration(preview_path) + 0.2, 30, 30)
        assert is_color(px, "blue"), px
        assert not is_color(px, "green")


def write_hevc(path: Path, *, color: str, dur: float, fps: int, size: str = "320x240") -> None:
    ff(
        "-f", "lavfi", "-i", f"color=c={color}:s={size}:r={fps}:d={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
        "-t", f"{dur}",
        "-c:v", "libx265", "-preset", "ultrafast", "-tag:v", "hvc1", "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        str(path),
    )


def test_hevc_open_and_60fps_stats_leave_hud_preview_copied() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        run = media / f"{D}-run-a.mp4"
        preview_path = hud / f"{D}-run-a-hud-preview.mp4"
        stats = media / f"{D}-close-stats.mp4"
        out = media / f"{D}-review-preview.mp4"
        write_hevc(media / f"{D}-open.mp4", color="blue", dur=0.6, fps=30)
        write_clip(run, color="green", dur=1.0)
        write_clip(preview_path, color="red", dur=1.0)
        write_hevc(stats, color="yellow", dur=0.6, fps=60)
        (media / f"{D}-stats-01.png").touch()
        code, text = run_preview(["--media-dir", str(media), "--out", str(out)])
        assert code == 0, text
        assert f"copy {preview_path}" in text
        assert str(run) not in text
        assert "overlay" not in text and "filter_complex" not in text and "hud-alpha" not in text
        assert probe_size(out) == (320, 240)
        assert abs(probe_fps(out) - 30) <= 0.02
        expected = (
            probe_duration(media / f"{D}-open.mp4")
            + probe_duration(preview_path)
            + probe_duration(stats)
            - 2 * preview.XFADE
        )
        assert abs(probe_duration(out) - expected) <= preview.duration_slack(3)
        open_out = probe_duration(media / f"{D}-open.mp4") - preview.XFADE
        run_d = probe_duration(preview_path)
        for t, color in ((0.15, "blue"), (open_out + 0.15, "red"), (open_out + run_d + 0.12, "yellow")):
            px = pixel(out, t, 30, 30)
            assert is_color(px, color), (t, color, px)


def write_phone(
    path: Path,
    *,
    color: str,
    dur: float,
    codec: str,
    rate: str,
    pix_fmt: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    video = (
        ["-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast"]
        if codec == "h264"
        else ["-c:v", "libx265", "-preset", "ultrafast", "-tag:v", "hvc1"]
    )
    ff(
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r={rate}:d={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
        "-t", f"{dur}",
        *video,
        "-pix_fmt", pix_fmt,
        "-r", rate,
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        str(path),
    )


def probe_pix_fmt(path: Path) -> str:
    return subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=pix_fmt", "-of", "default=nw=1:nk=1", str(path),
        ],
        text=True,
    ).strip()


def test_real_phone_yuvj420p_ntsc_copies_hud_previews() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        open_path = media / f"{D}-open.mp4"
        close = media / f"{D}-close.mp4"
        run_a = media / f"{D}-run-a.mp4"
        run_b = media / f"{D}-run-b.mp4"
        prev_a = hud / f"{D}-run-a-hud-preview.mp4"
        prev_b = hud / f"{D}-run-b-hud-preview.mp4"
        out = media / f"{D}-review-preview.mp4"
        write_phone(open_path, color="blue", dur=0.8, codec="hevc", rate="30/1", pix_fmt="yuvj420p")
        write_phone(close, color="yellow", dur=0.8, codec="hevc", rate="30/1", pix_fmt="yuvj420p")
        write_phone(run_a, color="green", dur=0.7, codec="h264", rate="30000/1001", pix_fmt="yuvj420p")
        write_phone(prev_a, color="red", dur=0.7, codec="h264", rate="30000/1001", pix_fmt="yuvj420p")
        write_phone(run_b, color="green", dur=0.7, codec="h264", rate="30000/1001", pix_fmt="yuvj420p")
        write_phone(prev_b, color="green", dur=0.7, codec="h264", rate="30000/1001", pix_fmt="yuvj420p")
        code, text = run_preview(["--media-dir", str(media), "--out", str(out), "--dry-run"])
        assert code == 0, text
        assert f"copy {prev_a}" in text and f"copy {prev_b}" in text
        assert f"transcode {open_path}" in text and f"transcode {close}" in text
        assert "yuvj420p" in text and "30000/1001" in text
        assert "29.970" in text
        assert str(run_a) not in text and str(run_b) not in text
        assert "filter_complex" not in text and "overlay" not in text
        code, text = run_preview(["--media-dir", str(media), "--out", str(out)])
        assert code == 0, text
        assert probe_pix_fmt(out) == "yuvj420p"
        assert abs(probe_fps(out) - (30000 / 1001)) <= 0.001
        expected = (
            probe_duration(open_path)
            + probe_duration(prev_a)
            + probe_duration(prev_b)
            + probe_duration(close)
            - 2 * preview.XFADE
        )
        actual = probe_duration(out)
        assert abs(actual - expected) <= preview.duration_slack(4), (actual, expected)
        open_out = probe_duration(open_path) - preview.XFADE
        run_a_d = probe_duration(prev_a)
        run_b_d = probe_duration(prev_b)
        checks = [
            (0.12, "blue"),
            (open_out + 0.12, "red"),
            (open_out + run_a_d + 0.12, "green"),
            (open_out + run_a_d + run_b_d + 0.12, "yellow"),
        ]
        for t, color in checks:
            px = pixel(out, t, 30, 30)
            assert is_color(px, color), (t, color, px, actual)


def test_remux_drops_extra_audio_without_reencode() -> None:
    with tempfile.TemporaryDirectory() as td:
        media = Path(td)
        hud = media / "hud-renders"
        hud.mkdir()
        run = media / f"{D}-run-a.mp4"
        preview_path = hud / f"{D}-run-a-hud-preview.mp4"
        close = media / f"{D}-close.mp4"
        out = media / f"{D}-review-preview.mp4"
        write_clip(run, color="green", dur=0.6)
        write_clip(preview_path, color="red", dur=1.0)
        write_clip(close, color="blue", dur=0.6)
        extra = media / f"{D}-open.mp4"
        ff(
            "-i", str(close), "-i", str(close),
            "-map", "0:v:0", "-map", "0:a:0", "-map", "1:a:0",
            "-c", "copy", str(extra),
        )
        code, text = run_preview(["--media-dir", str(media), "--out", str(out)])
        assert code == 0, text
        assert f"transcode {extra}" in text and "xfade trim tail" in text
        assert f"copy {preview_path}" in text
        assert "0:a:0" in text
        assert set(stream_types(out)) == {"video", "audio"}
        assert abs(probe_fps(out) - 30) <= 0.02
        expected = (
            probe_duration(extra) + probe_duration(preview_path) + probe_duration(close) - 2 * preview.XFADE
        )
        assert abs(probe_duration(out) - expected) <= preview.duration_slack(3)


if __name__ == "__main__":
    test_preview_source_has_no_restack_path()
    test_matching_plan_stream_copies_without_filtergraph()
    test_mismatch_transcodes_only_the_outlier()
    test_non_30fps_is_not_stream_copied()
    test_extra_streams_are_remuxed_not_reencoded()
    test_long_hevc_open_does_not_reencode_h264_preview()
    test_long_h264_open_does_not_outrank_hud_previews()
    test_phone_full_range_ntsc_hud_previews_are_copied()
    test_xfade_trim_does_not_reencode_matching_middle_segments()
    test_audio_mismatch_copies_video()
    test_larger_frame_wins_a_duration_tie()
    test_reject_final_paths()
    test_missing_hud_preview_fails_without_restack()
    test_missing_close_stats_fails_without_restack()
    test_leftover_close_stats_without_stills_uses_raw_close()
    test_orphan_preview_is_not_a_segment()
    test_concat_copy_keeps_duration_fps_and_pictures()
    test_outlier_is_light_transcoded_and_duration_holds()
    test_sixty_fps_sources_become_thirty()
    test_close_stats_is_the_data_segment()
    test_hevc_open_and_60fps_stats_leave_hud_preview_copied()
    test_real_phone_yuvj420p_ntsc_copies_hud_previews()
    test_remux_drops_extra_audio_without_reencode()
    print("ok test_preview_concat")
