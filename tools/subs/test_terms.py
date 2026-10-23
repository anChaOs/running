#!/usr/bin/env python3
"""专名表读取 / 英文专名拼写统一自检（无模型、无音频）。

运行：python3 tools/subs/test_terms.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subs_core as sc  # noqa: E402

PROMPT = "高驰、COROS、Personal Agent、VO2max、LetsRun、乳酸阈"


def test_fix_case_and_space():
    t, fx = sc.fix_terms("我用coros看vo2 max", PROMPT)
    assert t == "我用COROS看VO2max", t
    assert ("coros", "COROS") in fx
    t, _ = sc.fix_terms("personal agent和lets run", PROMPT)
    assert t == "Personal Agent和LetsRun", t


def test_no_partial_word():
    t, fx = sc.fix_terms("decorosity COROSX", PROMPT)
    assert t == "decorosity COROSX" and not fx, t


def test_chinese_untouched():
    t, fx = sc.fix_terms("乳酸域高池", PROMPT)
    assert t == "乳酸域高池" and not fx


def test_episode_terms():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "episode.md").write_text("---\ntitle: x\n---\n封面句：y\n专名：高驰，COROS、 乳酸阈\n", encoding="utf-8")
        assert sc.episode_terms(p / "subtitles.txt") == "高驰、COROS、乳酸阈"
        assert sc.resolve_prompt(None, p / "subtitles.txt") == "高驰、COROS、乳酸阈"
        assert sc.resolve_prompt("", p / "subtitles.txt") is None
        assert sc.resolve_prompt("A", p / "subtitles.txt") == "A"
        (p / "episode.md").write_text("专名：（口播会说到的产品名、人名）\n", encoding="utf-8")
        assert sc.episode_terms(p) is None
        (p / "episode.md").write_text("无专名\n", encoding="utf-8")
        assert sc.episode_terms(p) is None


def test_ensure_wav_from_mp4():
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return
    with tempfile.TemporaryDirectory() as d:
        mp4 = Path(d) / "x-run-final.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", str(mp4)], check=True)
        wav = sc.ensure_wav(mp4)
        assert wav == Path(d) / "asr" / "x-run-final.wav" and wav.is_file()
        assert sc.ensure_wav(mp4) == wav  # 第二次复用


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
