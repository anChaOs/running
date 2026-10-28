#!/usr/bin/env python3
"""assemble 自测：两遍 loudnorm + 叠加层停住。

合成素材（lavfi 色块 + 正弦），ASSEMBLE_VCODEC=libx264 代替 videotoolbox，抽单像素判断叠加层在不在。
不开任何播放器。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import assemble_episode as asm  # noqa: E402

D = "2026-01-02"


def test_units() -> None:
    assert asm.LOUDNESS_AF == (
        "highpass=f=90,afftdn=nf=-25,equalizer=f=3500:t=q:w=1.2:g=2.5,"
        "dynaudnorm=f=250:g=15:p=0.9:m=8,"
        "acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
        "loudnorm=I=-16:TP=-1.5:LRA=7,aformat=sample_rates=48000:channel_layouts=stereo"
    )
    m = {"input_i": "-30.1", "input_tp": "-9.2", "input_lra": "3.0", "input_thresh": "-40.5", "target_offset": "0.3"}
    af = asm.loudness_af_two_pass(m)
    assert af.startswith(asm.LOUDNESS_PRE + "loudnorm=I=-16:TP=-1.5:LRA=7:measured_I=-30.1:measured_TP=-9.2")
    assert "linear=true" in af and af.endswith("aformat=sample_rates=48000:channel_layouts=stereo")
    good = 'junk\n[Parsed_loudnorm_4 @ 0x1]\n{\n"input_i" : "-30.1",\n"input_tp" : "-9.2",\n"input_lra" : "3.0",\n' \
           '"input_thresh" : "-40.5",\n"target_offset" : "0.3"\n}\n'
    assert asm.parse_loudnorm_json(good)["input_i"] == "-30.1"
    assert asm.parse_loudnorm_json(good.replace('"-30.1"', '"-inf"')) is None
    assert asm.parse_loudnorm_json("no json here") is None
    assert asm.parse_time("5:50") == 350 and asm.parse_time("1:00:01.5") == 3601.5 and asm.parse_time(7) == 7
    cs, total = asm.timeline([3, 4, 4, 3], True, True)
    assert abs(cs - 10.6) < 1e-9 and abs(total - 13.6) < 1e-9
    ov = {"n": 1, "anchor": "close", "start": 1.0, "until": 2.0, "is_image": False, "src_dur": 0.5}
    r = asm.resolve_overlays([ov], cs, total)[0]
    assert abs(r["t0"] - 11.6) < 1e-9 and abs(r["hold"] - 0.5) < 1e-9
    f = asm.build_filter(4, [3, 4, 4, 3], True, True, None, None, "wind", 0.08, 320, 240, 4, 0.85,
                         loudness_af=asm.LOUDNESS_MEASURE_AF, audio_only=True)
    assert ":v]" not in f and "xfade" not in f and f.endswith("print_format=json[a]"), f


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def clip(path: Path, color: str, dur: float, size: str = "320x240", vol: float = 0.05) -> None:
    ff("-f", "lavfi", "-i", f"color=c={color}:s={size}:r=60:d={dur}",
       "-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={dur}",
       "-af", f"volume={vol}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path))


def pixel(video: Path, t: float, x: int, y: int) -> tuple[int, int, int]:
    raw = subprocess.check_output(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
         "-vf", f"crop=4:4:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return raw[0], raw[1], raw[2]


def is_color(px: tuple[int, int, int], name: str) -> bool:
    r, g, b = px
    return {"red": r > 180 and g < 80 and b < 80, "blue": b > 180 and r < 80 and g < 80,
            "green": g > 100 and r < 80 and b < 80}[name]


def test_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as d:
        m = Path(d, f"{D}-test")
        (m / "hud-renders").mkdir(parents=True)
        clip(m / f"{D}-open.mp4", "gray", 3)
        clip(m / "hud-renders" / f"{D}-run-a-hud-preview.mp4", "gray", 4)
        clip(m / "hud-renders" / f"{D}-run-b-hud-preview.mp4", "gray", 4, vol=0.02)
        clip(m / f"{D}-close.mp4", "gray", 3)
        ff("-f", "lavfi", "-i", "color=c=red:s=64x64:r=30:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           str(m / "lt-01.mp4"))
        ff("-f", "lavfi", "-i", "color=c=0x00a000:s=48x48:r=30:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           str(m / "lt-02.mp4"))
        ff("-f", "lavfi", "-i", "color=c=blue:s=32x32", "-frames:v", "1", str(m / "badge.png"))
        (m / "overlays.json").write_text(json.dumps({"overlays": [
            {"file": "lt-01.mp4", "start": "0:02", "hold_until": "0:04", "x": 10, "y": 10},
            {"file": "badge.png", "start": 7, "hold_until": 8, "x": 200, "y": 10},
            {"file": "lt-02.mp4", "anchor": "close", "start": 0.5, "hold_until": 2.0, "x": 10, "y": 150},
        ]}), encoding="utf-8")
        env = {**os.environ, "ASSEMBLE_VCODEC": "libx264"}
        dry = subprocess.run([sys.executable, str(HERE / "assemble_episode.py"), "--media-dir", str(m), "--dry-run"],
                             capture_output=True, text=True, env=env)
        assert dry.returncode == 0 and "two-pass" in dry.stdout and "#3 lt-02.mp4  0:11.10 → 0:12.60" in dry.stdout, \
            dry.stdout + dry.stderr
        assert not (m / f"{D}-run-final.mp4").exists()
        proc = subprocess.run([sys.executable, str(HERE / "assemble_episode.py"), "--media-dir", str(m)],
                              capture_output=True, text=True, env=env)
        assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
        out = proc.stdout
        assert "Loudnorm pass 1" in out and "linear=true" in out and "成片实测" in out, out
        final = m / f"{D}-run-final.mp4"
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(final)], text=True))
        assert abs(dur - 13.6) < 0.15, dur
        checks = [(1.5, 30, 30, "red", False), (2.5, 30, 30, "red", True), (3.7, 30, 30, "red", True),
                  (4.4, 30, 30, "red", False), (7.5, 210, 20, "blue", True), (8.4, 210, 20, "blue", False),
                  (11.4, 30, 170, "green", True), (12.4, 30, 170, "green", True), (13.0, 30, 170, "green", False)]
        for t, x, y, color, want in checks:
            px = pixel(final, t, x, y)
            assert is_color(px, color) == want, (t, color, want, px)
        got = asm.measure_output(final)
        assert got is not None and abs(float(got["input_i"]) + 16) < 1.5, got
        assert float(got["input_tp"]) <= -1.0, got
        print(f"  final I={got['input_i']} TP={got['input_tp']} LRA={got['input_lra']}")
        # 单遍开关 / 测量失败退回
        proc = subprocess.run([sys.executable, str(HERE / "assemble_episode.py"), "--media-dir", str(m),
                               "--single-pass-loudnorm", "--no-overlays", "--out", str(m / "sp.mp4")],
                              capture_output=True, text=True, env=env)
        assert proc.returncode == 0 and "Loudnorm pass 1" not in proc.stdout and "Overlays: none" in proc.stdout


if __name__ == "__main__":
    test_units()
    test_end_to_end()
    print("ok: assemble overlays + two-pass loudnorm")
