#!/usr/bin/env python3
"""从原片、HUD alpha、stats 图片和 overlays.json 生成一次整条审片预览。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import final_export as final
from export_spec import PREVIEW_SPEC


def discover(media_dir: Path) -> final.SourceSet:
    """新期只读取最终导出同源素材；close-stats 仅由旧期旁路自行兼容。"""
    return final.discover_sources(media_dir, allow_legacy_close_stats=True)


def build_command(
    sources: final.SourceSet,
    durations: list[float],
    output: Path,
    *,
    media_dir: Path | None = None,
    overlays_path: str | None = None,
    no_overlays: bool = False,
) -> list[str]:
    overlays: list[dict] = []
    if not no_overlays and media_dir is not None:
        overlays = final.load_timeline_overlays(
            media_dir,
            durations,
            has_open=sources.open_clip is not None,
            has_close=sources.close_clip is not None,
            explicit=overlays_path,
        )
    plan = final.build_input_plan(sources, durations, PREVIEW_SPEC, overlays)
    graph = final.build_filter_graph(
        sources,
        durations,
        plan,
        ass=None,
        spec=PREVIEW_SPEC,
        apply_loudness=False,
        overlays=overlays,
    )
    return final.build_encode_cmd(plan, graph, output, spec=PREVIEW_SPEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--out")
    parser.add_argument(
        "--overlays",
        help="叠加层配置 JSON。默认找 <media-dir>/overlays.json，再找 episodes/<媒体目录名>/overlays.json",
    )
    parser.add_argument("--no-overlays", action="store_true", help="有 overlays.json 也不叠")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    media_dir = Path(args.media_dir).expanduser().resolve()
    sources = discover(media_dir)
    durations = [final.probe_duration(path) for path in sources.clips]
    date = sources.clips[0].name[:10]
    output = Path(args.out).expanduser().resolve() if args.out else media_dir / f"{date}-review-preview.mp4"
    if output.name.endswith("-run-final.mp4") or "upload" in output.parts:
        raise SystemExit("Review preview cannot be written as run-final or inside upload/")
    cmd = build_command(
        sources,
        durations,
        output,
        media_dir=media_dir,
        overlays_path=args.overlays,
        no_overlays=args.no_overlays,
    )
    print("$", " ".join(cmd))
    if not args.dry_run:
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
