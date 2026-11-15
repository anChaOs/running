#!/usr/bin/env python3
"""把 subtitles.txt 收成 SRT（B 站 / YouTube 外挂）。只换时间和字。

仓库只跟踪 subtitles.txt。写出的 .srt 是生成文件，不要 git add。
默认写在 txt 旁边（episodes/*/subtitles.srt 已被 .gitignore）。
--media-dir 再拷到媒体目录的 subtitles.srt。审片清单还在时另拷同名 .srt。
不要在烧字成片旁边留同名 .srt。
"""

from __future__ import annotations

import argparse
import re
import shutil
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


def media_sidecar_targets(media: Path, episode_name: str) -> list[Path]:
    """上传用 subtitles.srt。审片清单可以有同名 .srt。烧字成片旁边不留同名 .srt。"""
    date = episode_name[:10]
    targets = [media / "subtitles.srt"]
    preview_names = (f"{date}-review-preview.edl", f"{date}-review-preview.mp4")
    if any((media / name).is_file() for name in preview_names):
        targets.append(media / f"{date}-review-preview.srt")
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert subtitles.txt into SRT for Bilibili and YouTube.")
    parser.add_argument("--txt", required=True, help="episodes/.../subtitles.txt")
    parser.add_argument("--srt", help="输出 SRT。默认写在 txt 旁边（本地导出，不进 git）")
    parser.add_argument("--media-dir", help="同时拷到媒体目录：subtitles.srt（上传用）。"
                        "若有 YYYY-MM-DD-review-preview.edl（或旧的预览 mp4），另拷同名 .srt。"
                        "不在烧字成片旁边留同名 .srt。传 auto = ~/Movies/running-content/<期名>")
    args = parser.parse_args()

    txt = Path(args.txt).expanduser().resolve()
    if not txt.is_file():
        raise SystemExit(f"txt not found: {txt}")
    cues = parse_txt(txt)
    srt_path = Path(args.srt).expanduser().resolve() if args.srt else txt.with_suffix(".srt")
    write_srt(srt_path, cues)
    print(f"cues={len(cues)}")
    print(f"Wrote {srt_path}")
    if args.media_dir:
        media = (Path.home() / "Movies/running-content" / txt.parent.name if args.media_dir == "auto"
                 else Path(args.media_dir).expanduser().resolve())
        if not media.is_dir():
            raise SystemExit(f"media dir not found: {media}")
        targets = media_sidecar_targets(media, txt.parent.name)
        stale = media / f"{txt.parent.name[:10]}-run-final.srt"
        if stale.is_file() and stale.resolve() != srt_path.resolve():
            stale.unlink()
            print(f"Removed {stale} (burned final must not keep a same-name sidecar)")
        for t in targets:
            if t.resolve() != srt_path:
                shutil.copyfile(srt_path, t)
                print(f"Copied {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
