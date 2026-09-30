#!/usr/bin/env python3
"""把 subtitles.txt 收成 SRT（B 站 / YouTube 外挂）。只换时间和字。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


CUE_RE = re.compile(r"^(\d+:\d{2}:\d{2}\.\d{2})[–-](\d+:\d{2}:\d{2}\.\d{2})\s+(.*)$")


def parse_txt(path: Path) -> list[tuple[str, str, str]]:
    cues: list[tuple[str, str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = CUE_RE.match(line)
        if not m:
            raise SystemExit(f"unparsed line in {path}: {raw!r}")
        start, end, text = m.group(1), m.group(2), m.group(3).strip()
        if not text:
            raise SystemExit(f"empty text in {path}: {raw!r}")
        if "\\N" in text or "\n" in text:
            raise SystemExit(f"multi-line cue in {path}: {text!r}")
        cues.append((start, end, text))
    if not cues:
        raise SystemExit(f"no cues in {path}")
    return cues


def txt_to_srt_time(t: str) -> str:
    h, m, rest = t.split(":")
    s, cs = rest.split(".")
    return f"{int(h):02d}:{m}:{s},{int(cs) * 10:03d}"


def write_srt(path: Path, cues: list[tuple[str, str, str]]) -> None:
    blocks = [
        f"{i}\n{txt_to_srt_time(start)} --> {txt_to_srt_time(end)}\n{text}\n"
        for i, (start, end, text) in enumerate(cues, 1)
    ]
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert subtitles.txt into SRT for Bilibili and YouTube.")
    parser.add_argument("--txt", required=True, help="episodes/.../subtitles.txt")
    parser.add_argument("--srt", help="Output SRT. Default: next to txt")
    args = parser.parse_args()

    txt = Path(args.txt).expanduser().resolve()
    if not txt.is_file():
        raise SystemExit(f"txt not found: {txt}")
    cues = parse_txt(txt)
    srt_path = Path(args.srt).expanduser().resolve() if args.srt else txt.with_suffix(".srt")
    write_srt(srt_path, cues)
    print(f"cues={len(cues)}")
    print(f"Wrote {srt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
