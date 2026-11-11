#!/usr/bin/env python3
"""从原片、HUD alpha 和 stats 图片生成一次整条审片预览。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import final_export as final
import log_timeline
from export_spec import PREVIEW_SPEC


def discover(media_dir: Path) -> final.SourceSet:
    """新期只读取最终导出同源素材；close-stats 仅由旧期旁路自行兼容。"""
    return final.discover_sources(media_dir, allow_legacy_close_stats=True)


def build_command(
    sources: final.SourceSet,
    durations: list[float],
    output: Path,
) -> list[str]:
    plan = final.build_input_plan(sources, durations, PREVIEW_SPEC)
    graph = final.build_filter_graph(
        sources,
        durations,
        plan,
        ass=None,
        spec=PREVIEW_SPEC,
        apply_loudness=False,
    )
    return final.build_encode_cmd(plan, graph, output, spec=PREVIEW_SPEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--out")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    media_dir = Path(args.media_dir).expanduser().resolve()
    with log_timeline.span(media_dir, "review-preview", enabled=not args.dry_run) as wall:
        wall.rc = _preview(args, media_dir)
        return wall.rc


def _preview(args, media_dir: Path) -> int:
    sources = discover(media_dir)
    durations = [final.probe_duration(path) for path in sources.clips]
    date = sources.clips[0].name[:10]
    output = Path(args.out).expanduser().resolve() if args.out else media_dir / f"{date}-review-preview.mp4"
    if output.name.endswith("-run-final.mp4") or "upload" in output.parts:
        raise SystemExit("Review preview cannot be written as run-final or inside upload/")
    cmd = build_command(sources, durations, output)
    print("$", " ".join(cmd))
    if not args.dry_run:
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
