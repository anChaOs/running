#!/usr/bin/env python3
"""loudness_only / burn_ass 轻量自测（不依赖 videotoolbox）。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import burn_ass as burn  # noqa: E402
import loudness_only as loud  # noqa: E402


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def test_discovery_and_escape() -> None:
    with tempfile.TemporaryDirectory() as d:
        m = Path(d)
        (m / "2026-01-02-run-final.mp4").write_bytes(b"x")
        (m / "2026-01-02-run-final-no-burn.mp4").write_bytes(b"x")
        (m / "2026-01-02-run-final-pre-coldopen.mp4").write_bytes(b"x")
        assert loud.find_run_final(m).name == "2026-01-02-run-final.mp4"
        assert burn.find_run_final(m).name == "2026-01-02-run-final.mp4"
        esc = burn.escape_subtitles_path(Path("/tmp/foo:bar.ass"))
        assert "\\:" in esc
        assert burn.escape_subtitles_path(Path("/tmp/a'b.ass")).count("\\'") == 1


def test_loudness_dry_and_e2e_libx264() -> None:
    with tempfile.TemporaryDirectory() as d:
        m = Path(d)
        src = m / "2026-01-02-run-final.mp4"
        out = m / "out.mp4"
        ff(
            "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=30:d=1.5",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src),
        )
        # dry-run
        r = subprocess.run(
            [sys.executable, str(HERE / "loudness_only.py"), "--input", str(src), "--out", str(out), "--dry-run"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert " -c:v copy " in r.stdout or "-c:v copy" in r.stdout
        # real encode (copy video)
        r = subprocess.run(
            [sys.executable, str(HERE / "loudness_only.py"), "--input", str(src), "--out", str(out),
             "--single-pass-loudnorm"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert out.is_file() and out.stat().st_size > 1000


def test_burn_dry_run() -> None:
    with tempfile.TemporaryDirectory() as d:
        m = Path(d)
        src = m / "clip.mp4"
        ass = m / "t.ass"
        ass.write_text(
            "[Script Info]\nScriptType: v4.00+\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,20,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,hi\n",
            encoding="utf-8",
        )
        ff(
            "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=30:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src),
        )
        import os
        env = os.environ.copy()
        env["ASSEMBLE_VCODEC"] = "libx264"
        r = subprocess.run(
            [sys.executable, str(HERE / "burn_ass.py"), "--input", str(src), "--ass", str(ass),
             "--out", str(m / "burned.mp4"), "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, r.stderr
        assert "subtitles=" in r.stdout
        assert "-c:a copy" in r.stdout


if __name__ == "__main__":
    test_discovery_and_escape()
    test_loudness_dry_and_e2e_libx264()
    test_burn_dry_run()
    print("ok")
