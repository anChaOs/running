#!/usr/bin/env python3
"""txt_to_ass 样式与对白格式自检（无模型、无音频）。

运行：python3 tools/subs/test_txt_to_ass.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import txt_to_ass as ta  # noqa: E402


def test_style_matches_burned_episodes():
    cues = [("0:00:02.97", "0:00:05.48", "大家好 我是安超")]
    text = ta.render_ass(cues)
    assert "Style: Default,Source Han Sans SC Heavy,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,2,80,80,100,1\n" in text
    assert "PlayResX: 1920\nPlayResY: 1080\n" in text
    assert text.endswith("Dialogue: 0,0:00:02.97,0:00:05.48,Default,,0,0,0,,大家好 我是安超\n")


def test_escapes_override_tags():
    text = ta.render_ass([("0:00:00.00", "0:00:01.00", r"a{b}\c")])
    assert text.endswith("Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,a\\{b\\}\\\\c\n")


def test_cli_writes_beside_txt_and_media_copy():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ep = root / "2026-01-01-slug"
        media = root / "media"
        ep.mkdir()
        media.mkdir()
        txt = ep / "subtitles.txt"
        txt.write_text("# 注释\n0:00:00.10–0:00:01.20  只留这一句\n", encoding="utf-8")
        old = sys.argv
        try:
            sys.argv = ["txt_to_ass.py", "--txt", str(txt), "--media-dir", str(media)]
            assert ta.main() == 0
        finally:
            sys.argv = old
        ass = (ep / "subtitles.ass").read_text(encoding="utf-8")
        assert ass == (media / "subtitles.ass").read_text(encoding="utf-8")
        assert "只留这一句" in ass
        assert "注释" not in ass




def test_header_starts_with_script_info():
    text = ta.render_ass([("0:00:00.00", "0:00:01.00", "hi")])
    assert text.startswith("[Script Info]\n"), text[:40]
    assert not text.startswith("\\"), text[:20]

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
