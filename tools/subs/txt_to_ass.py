#!/usr/bin/env python3
"""把 subtitles.txt 收成烧字 ASS。

样式与已烧进成片的各期 subtitles.ass 相同（Source Han Sans SC Heavy / 72 / Outline 3 / MarginV 100），不另起一套。
不进 git。默认写在 txt 旁边。--media-dir 再拷到媒体目录。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from txt_to_subs import parse_txt  # noqa: E402


# 与 episodes/*/subtitles.ass（2026-10-11 起已烧字各期）文件头逐字相同。
HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Source Han Sans SC Heavy,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,2,80,80,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def render_ass(cues: list[tuple[str, str, str]]) -> str:
    lines = [
        f"Dialogue: 0,{start},{end},Default,,0,0,0,,{escape_ass_text(text)}"
        for start, end, text in cues
    ]
    return HEADER + "\n".join(lines) + "\n"


def write_ass(path: Path, cues: list[tuple[str, str, str]]) -> None:
    path.write_text(render_ass(cues), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert subtitles.txt into burn-in ASS (existing episode style).")
    parser.add_argument("--txt", required=True, help="episodes/.../subtitles.txt")
    parser.add_argument("--ass", help="输出 ASS。默认写在 txt 旁边（本地导出，不进 git）")
    parser.add_argument("--media-dir", help="再拷一份到媒体目录 subtitles.ass。"
                        "传 auto = ~/Movies/running-content/<期名>")
    args = parser.parse_args()

    txt = Path(args.txt).expanduser().resolve()
    if not txt.is_file():
        raise SystemExit(f"txt not found: {txt}")
    cues = parse_txt(txt)
    ass_path = Path(args.ass).expanduser().resolve() if args.ass else txt.with_suffix(".ass")
    write_ass(ass_path, cues)
    print(f"cues={len(cues)}")
    print(f"Wrote {ass_path}")
    if args.media_dir:
        media = (Path.home() / "Movies/running-content" / txt.parent.name if args.media_dir == "auto"
                 else Path(args.media_dir).expanduser().resolve())
        if not media.is_dir():
            raise SystemExit(f"media dir not found: {media}")
        target = media / "subtitles.ass"
        if target.resolve() != ass_path:
            shutil.copyfile(ass_path, target)
            print(f"Copied {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
