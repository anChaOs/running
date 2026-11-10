#!/usr/bin/env python3
"""字幕确认后的唯一最终导出入口。

预览只用于人工检查；本入口直接读取原片和 HUD 透明层，在一次最终编码中完成
转场拼接、数据图叠加、字幕和响度处理。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
SUBS_DIR = TOOLS_DIR / "subs"
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(SUBS_DIR))

from export_spec import FINAL_SPEC, ExportSpec, audio_codec_args, video_codec_args  # noqa: E402
from txt_to_ass import parse_txt, render_ass  # type: ignore[import-not-found]  # noqa: E402


DATE_STATS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-stats-\d+$")
RAW_STATS_HINTS = ("screenshot", "coros", "截图")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
RAW_CLIP_PARTS = ("run-final", "hud-preview", "close-stats", "-raw", "pre-", "-bad", "orient", "transpose")


@dataclass(frozen=True)
class SourceSet:
    open_clip: Path | None
    runs: tuple[Path, ...]
    close_clip: Path | None
    hud_alpha: tuple[Path, ...]
    stats: tuple[Path, ...]

    @property
    def clips(self) -> tuple[Path, ...]:
        return tuple(p for p in (self.open_clip, *self.runs, self.close_clip) if p is not None)


@dataclass(frozen=True)
class InputPlan:
    args: tuple[str, ...]
    clip_count: int
    alpha_indices: tuple[int, ...]
    stats_indices: tuple[int, ...]
    stats_duration: float


def _one(paths: list[Path], label: str) -> Path | None:
    if len(paths) > 1:
        raise SystemExit(f"Multiple {label} candidates: {', '.join(p.name for p in paths)}")
    return paths[0] if paths else None


def _stats_files(media_dir: Path) -> tuple[Path, ...]:
    named = sorted(p for p in media_dir.iterdir() if p.is_file() and DATE_STATS_RE.match(p.stem) and p.suffix.lower() in IMAGE_EXT)
    if named:
        return tuple(named)
    return tuple(
        p for p in sorted(media_dir.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXT
        and not p.name.lower().startswith("cover-")
        and "hud" not in p.name.lower()
        and any(hint in p.name.lower() for hint in RAW_STATS_HINTS)
    )


def discover_sources(media_dir: Path) -> SourceSet:
    open_clip = _one(sorted(media_dir.glob("*-open.mp4")), "open")
    close_clip = _one(
        [p for p in sorted(media_dir.glob("*-close.mp4")) if "stats" not in p.name and "hud" not in p.name],
        "close",
    )
    runs = tuple(
        p for p in sorted(media_dir.glob("*-run-*.mp4"))
        if not any(part in p.stem for part in RAW_CLIP_PARTS)
    )
    if not runs:
        raise SystemExit(f"No original run clips in {media_dir}; final export never consumes HUD previews")
    alpha = tuple(sorted((media_dir / "hud-renders").glob("*-run-*-hud-alpha.mov")))
    if len(alpha) != len(runs):
        raise SystemExit(f"Need one HUD alpha per run: runs={len(runs)} alpha={len(alpha)}")
    for run, layer in zip(runs, alpha, strict=True):
        expected = f"{run.stem}-hud-alpha.mov"
        if layer.name != expected:
            raise SystemExit(f"HUD alpha {layer.name} does not match original run {run.name}")
    return SourceSet(open_clip, runs, close_clip, alpha, _stats_files(media_dir))


def read_status(episode_dir: Path) -> dict[str, str]:
    path = episode_dir / "assets.md"
    if not path.is_file():
        raise SystemExit(f"assets.md not found: {path}")
    text = path.read_text(encoding="utf-8")
    section = text.split("## 制作状态", 1)[-1]
    return {k.lower(): v.strip() for k, v in re.findall(r"^\s*-\s*([A-Za-z]+)\s*:\s*([^\n]+)", section, re.M)}


def validate_gate(episode_dir: Path, subtitles: Path, confirmed: bool, sources: SourceSet) -> None:
    if not confirmed:
        raise SystemExit("Final export requires --confirmed after manual subtitle review")
    if not subtitles.is_file():
        raise SystemExit(f"subtitles.txt not found: {subtitles}")
    parse_txt(subtitles)
    status = read_status(episode_dir)
    if not status.get("subs", "").startswith("done"):
        raise SystemExit("Final export requires assets.md subs: done after user confirmation")
    if not status.get("qc", "").startswith("done"):
        raise SystemExit("Final export requires preview qc: done before final export")
    if any("hud-preview" in p.name or "close-stats" in p.name for p in (*sources.runs, *sources.hud_alpha)):
        raise SystemExit("Final export cannot consume encoded preview intermediates")


def escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def make_ass(subtitles: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix="running-final-", suffix=".ass")
    Path(name).write_text(render_ass(parse_txt(subtitles)), encoding="utf-8")
    # mkstemp 的 fd 不再需要；Python 的 Path 写入会重新打开同一路径。
    import os
    os.close(fd)
    return Path(name)


def build_input_plan(sources: SourceSet, durations: list[float], spec: ExportSpec) -> InputPlan:
    args: list[str] = []
    clip_count = len(sources.clips)
    for clip in sources.clips:
        args.extend(["-i", str(clip)])
    alpha_indices: list[int] = []
    for alpha in sources.hud_alpha:
        alpha_indices.append(clip_count + len(alpha_indices))
        args.extend(["-i", str(alpha)])
    close_duration = durations[-1] if sources.close_clip is not None else 0.0
    stats_indices: list[int] = []
    for image in sources.stats:
        stats_indices.append(clip_count + len(alpha_indices) + len(stats_indices))
        args.extend(["-loop", "1", "-framerate", str(spec.timeline.fps), "-t", f"{close_duration:.6f}", "-i", str(image)])
    return InputPlan(tuple(args), clip_count, tuple(alpha_indices), tuple(stats_indices), close_duration)


def loudness_filter(spec: ExportSpec, measured: dict[str, str] | None = None) -> str:
    loud = spec.loudness
    target = f"loudnorm=I={loud.integrated_lufs:g}:TP={loud.true_peak_db:g}:LRA={loud.lra:g}"
    if measured is not None:
        target += (
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true:print_format=summary"
        )
    else:
        target += ":print_format=json"
    return (
        "highpass=f=90,afftdn=nf=-25,equalizer=f=3500:t=q:w=1.2:g=2.5,"
        "dynaudnorm=f=250:g=15:p=0.9:m=8,"
        "acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
        + target
        + ",aformat=sample_rates=48000:channel_layouts=stereo"
    )


def build_filter_graph(
    sources: SourceSet,
    durations: list[float],
    plan: InputPlan,
    ass: Path,
    spec: ExportSpec = FINAL_SPEC,
    measured: dict[str, str] | None = None,
) -> str:
    """生成最终滤镜图；所有画面改动都在这张图和同一次输出编码内完成。"""
    fps = spec.timeline.fps
    width, height = spec.timeline.width, spec.timeline.height
    parts: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    for i, duration in enumerate(durations):
        v = f"v{i}"
        a = f"a{i}"
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},settb=1/{fps},format=yuv420p,setsar=1[{v}]"
        )
        parts.append(
            f"[{i}:a]aformat=sample_rates={spec.timeline.sample_rate}:channel_layouts=stereo,"
            f"aresample=async=1:first_pts=0,apad=whole_dur={duration:.6f},atrim=0:{duration:.6f},setpts=PTS-STARTPTS[{a}]"
        )
        video_labels.append(v)
        audio_labels.append(a)

    run_start = 1 if sources.open_clip is not None else 0
    for pos, alpha_index in enumerate(plan.alpha_indices):
        run_index = run_start + pos
        alpha = f"ha{pos}"
        out = f"vh{pos}"
        parts.append(f"[{alpha_index}:v]fps={fps},settb=1/{fps},format=rgba[{alpha}]")
        parts.append(f"[{video_labels[run_index]}][{alpha}]overlay=eof_action=pass:shortest=0:format=auto[{out}]")
        video_labels[run_index] = out

    if sources.stats and sources.close_clip is not None:
        close_i = len(sources.clips) - 1
        slide_labels: list[str] = []
        slice_duration = plan.stats_duration / len(plan.stats_indices)
        for n, image_index in enumerate(plan.stats_indices):
            s = f"st{n}"
            parts.append(
                f"[{image_index}:v]scale=-2:{max(320, int(height * 0.82))}:force_original_aspect_ratio=decrease,"
                f"format=rgba,colorchannelmixer=aa=0.82,trim=duration={slice_duration:.6f},setpts=PTS-STARTPTS[{s}]"
            )
            slide_labels.append(f"[{s}]")
        stack = "".join(slide_labels)
        parts.append(f"{stack}concat=n={len(slide_labels)}:v=1:a=0,fps={fps},settb=1/{fps},tpad=stop_mode=clone:stop_duration={plan.stats_duration:.6f},trim=duration={plan.stats_duration:.6f}[stats]")
        parts.append(f"[{video_labels[close_i]}][stats]overlay=x=40:y=(H-h)/2:eof_action=repeat:shortest=0[vc]")
        video_labels[close_i] = "vc"

    # 硬切 concat 保持每个源片段的原始时间轴；所有画面仍只在最终输出中编码一次。
    pairs = "".join(f"[{v}][{a}]" for v, a in zip(video_labels, audio_labels, strict=True))
    parts.append(f"{pairs}concat=n={len(video_labels)}:v=1:a=1[joinedv][joineda]")
    ass_path = escape_filter_path(ass)
    parts.append(f"[joinedv]subtitles={ass_path}:charenc=UTF-8[v]")
    parts.append(f"[joineda]{loudness_filter(spec, measured)}[a]")
    return ";".join(parts)


def parse_loudnorm(stderr: str) -> dict[str, str] | None:
    end = stderr.rfind("}")
    start = stderr.rfind("{", 0, end)
    if start < 0 or end < 0:
        return None
    try:
        value = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return None
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(key in value for key in keys):
        return None
    return {key: str(value[key]) for key in keys}


def build_encode_cmd(plan: InputPlan, graph: str, output: Path, test_codec: str | None = None) -> list[str]:
    codec_args = video_codec_args(FINAL_SPEC, test_codec=test_codec)
    return [
        "ffmpeg", "-y", "-hide_banner", *plan.args,
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        *codec_args,
        "-pix_fmt", FINAL_SPEC.timeline.pix_fmt,
        *audio_codec_args(FINAL_SPEC), "-movflags", "+faststart", str(output),
    ]


def measure_loudness(plan: InputPlan, graph: str) -> dict[str, str] | None:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", *plan.args, "-filter_complex", graph, "-map", "[a]", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return parse_loudnorm(proc.stderr) if proc.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--subtitles", help="默认 <episode-dir>/subtitles.txt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--test-codec", choices=("libx264",), help="仅隔离测试使用")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    media_dir = Path(args.media_dir).expanduser().resolve()
    episode_dir = Path(args.episode_dir).expanduser().resolve()
    subtitles = Path(args.subtitles).expanduser().resolve() if args.subtitles else episode_dir / "subtitles.txt"
    sources = discover_sources(media_dir)
    validate_gate(episode_dir, subtitles, args.confirmed, sources)
    output = Path(args.out).expanduser().resolve()
    if output.exists() and not args.dry_run:
        raise SystemExit(f"Refusing to overwrite existing final output: {output}")
    durations = [probe_duration(path) for path in sources.clips]
    plan = build_input_plan(sources, durations, FINAL_SPEC)
    ass = make_ass(subtitles)
    try:
        first_graph = build_filter_graph(sources, durations, plan, ass, measured=None)
        measured = None if args.dry_run else measure_loudness(plan, first_graph)
        if measured is not None:
            print(f"Loudnorm pass 1: I={measured['input_i']} TP={measured['input_tp']}")
        final_graph = build_filter_graph(sources, durations, plan, ass, measured=measured)
        cmd = build_encode_cmd(plan, final_graph, output, test_codec=args.test_codec)
        print("$", " ".join(cmd))
        if not args.dry_run:
            subprocess.run(cmd, check=True)
            print(f"Wrote {output}")
    finally:
        ass.unlink(missing_ok=True)
    return 0


def probe_duration(path: Path) -> float:
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True).strip()
    return float(raw)


if __name__ == "__main__":
    raise SystemExit(main())
