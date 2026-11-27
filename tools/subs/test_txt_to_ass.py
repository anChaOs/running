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


def test_style_is_slightly_larger_and_tracked():
    """官方默认：字号 72→80，字间距 Spacing/\\fsp 0→3。字体、描边、底边距不动。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from export_spec import FINAL_SPEC

    sub = FINAL_SPEC.subtitle
    assert (sub.font_size, sub.spacing, sub.margin_v) == (80, 3, 100)
    cues = [("0:00:02.97", "0:00:05.48", "大家好 我是安超")]
    text = ta.render_ass(cues)
    style = (
        "Style: Default,Source Han Sans SC Heavy,"
        f"{sub.font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,{sub.spacing},0,1,3,0,2,80,80,{sub.margin_v},1\n"
    )
    assert style in text
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




def test_media_sidecar_does_not_sit_beside_the_burned_final():
    import txt_to_subs

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ep = root / "2026-01-02-demo"
        media = root / "media"
        ep.mkdir()
        media.mkdir()
        (media / "2026-01-02-review-preview.mp4").write_bytes(b"preview")
        (media / "2026-01-02-run-final.mp4").write_bytes(b"final")
        (media / "2026-01-02-run-final.srt").write_text("old\n", encoding="utf-8")
        names = [path.name for path in txt_to_subs.media_sidecar_targets(media, ep.name)]
        assert names == ["subtitles.srt", "2026-01-02-review-preview.srt"]
        txt = ep / "subtitles.txt"
        txt.write_text("0:00:00.10–0:00:01.20  只留这一句\n", encoding="utf-8")
        old = sys.argv
        try:
            sys.argv = ["txt_to_subs.py", "--txt", str(txt), "--media-dir", str(media)]
            assert txt_to_subs.main() == 0
        finally:
            sys.argv = old
        assert (media / "subtitles.srt").is_file()
        assert (media / "2026-01-02-review-preview.srt").is_file()
        assert not (media / "2026-01-02-run-final.srt").exists()
        (media / "2026-01-02-review-preview.mp4").unlink()
        (media / "2026-01-02-review-preview.edl").write_bytes(b"edl")
        names = [path.name for path in txt_to_subs.media_sidecar_targets(media, ep.name)]
        assert names == ["subtitles.srt", "2026-01-02-review-preview.srt"]
        (media / "2026-01-02-review-preview.edl").unlink()
        names = [path.name for path in txt_to_subs.media_sidecar_targets(media, ep.name)]
        assert names == ["subtitles.srt"]


def test_header_starts_with_script_info():
    text = ta.render_ass([("0:00:00.00", "0:00:01.00", "hi")])
    assert text.startswith("[Script Info]\n"), text[:40]
    assert not text.startswith("\\"), text[:20]

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
