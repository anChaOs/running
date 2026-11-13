#!/usr/bin/env python3
"""字幕确认后的唯一最终导出入口。

有时间表时，确认导出仍是一条命令、一个成片文件。画面按大约两分钟分段编码，
段界不切断风刮或 xfade；每一段只出画面。整片音频用和测响度同一张图混一次、
编一次 AAC，和第一段画面并行。最后把画面段流拷贝接起来，配上这一条音频。

同一段里，一条原片只打开一次：`-ss` 到这段最早的入点，多段句间刀用 select 丢掉
空隙，不再 split。split 会把还没读到的输出垫住，解码帧一直留到这段结束，16GB
机器上足迹会随时间涨到几十 GB。窗口透明层仍按原片收成一条再叠一次，不按窗口
各留一个输入，也不读 `hud-renders/keeps/`。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
ASSEMBLE_DIR = Path(__file__).resolve().parent
SUBS_DIR = TOOLS_DIR / "subs"
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "hud"))
sys.path.insert(0, str(SUBS_DIR))
sys.path.insert(0, str(ASSEMBLE_DIR))

import log_timeline
import program_edl as edl
import todo_list
from export_spec import (
    FINAL_SPEC,
    ExportSpec,
    audio_codec_args,
    video_codec_args,
)
from txt_to_ass import (  # type: ignore[import-not-found]
    parse_txt,
    render_ass,
)
import assemble_episode as assemble  # noqa: E402

DATE_STATS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-stats-\d+$")
RAW_STATS_HINTS = ("screenshot", "coros", "截图")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
RAW_CLIP_PARTS = (
    "run-final",
    "hud-preview",
    "close-stats",
    "-raw",
    "pre-",
    "-bad",
    "orient",
    "transpose",
    "review-preview",
)
XFADE = 0.2
WIND = 0.08
WHOOSH_PATH = Path(__file__).resolve().parent / "sfx" / "whoosh.wav"
SUBTITLE_FONTS_DIR = TOOLS_DIR / "hud" / "fonts"
SUBTITLE_FONT_FILE = SUBTITLE_FONTS_DIR / "SourceHanSansSC-Heavy.otf"


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
    whoosh_index: int | None = None
    overlay_indices: tuple[int, ...] = ()


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


def _allowed_source(path: Path) -> bool:
    return not any(part in path.stem for part in RAW_CLIP_PARTS)


def discover_sources(media_dir: Path, *, allow_legacy_close_stats: bool = False) -> SourceSet:
    open_clip = _one([p for p in sorted(media_dir.glob("*-open.mp4")) if _allowed_source(p)], "open")
    close_candidates = [
        p for p in sorted(media_dir.glob("*-close.mp4"))
        if _allowed_source(p) and "stats" not in p.name and "hud" not in p.name
    ]
    close_clip = _one(close_candidates, "close")
    if close_clip is None and allow_legacy_close_stats:
        close_clip = _one(sorted(media_dir.glob("*-close-stats.mp4")), "legacy close-stats")
    elif close_clip is None and list(media_dir.glob("*-close-stats.mp4")):
        raise SystemExit("Final export requires original close; close-stats.mp4 is a legacy preview only")
    runs = tuple(p for p in sorted(media_dir.glob("*-run-*.mp4")) if _allowed_source(p))
    if not runs:
        raise SystemExit(f"No original run clips in {media_dir}; final export never consumes HUD previews")
    alpha = tuple(
        p for p in sorted((media_dir / "hud-renders").glob("*-run-*-hud-alpha.mov")) if _allowed_source(p)
    )
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
    return {k.lower(): v.strip() for k, v in re.findall(r"^\s*-\s*([A-Za-z]+)\s*:\s*([^\n]+)", section, re.MULTILINE)}


def validate_gate(episode_dir: Path, subtitles: Path, confirmed: bool, sources: SourceSet) -> None:
    if not confirmed:
        raise SystemExit("Final export requires --confirmed after manual subtitle review")
    if not subtitles.is_file():
        raise SystemExit(f"subtitles.txt not found: {subtitles}")
    parse_txt(subtitles)
    status = read_status(episode_dir)
    if not status.get("preview", "").startswith("done"):
        raise SystemExit("Final export requires assets.md preview: done")
    if not status.get("subs", "").startswith("done"):
        raise SystemExit("Final export requires assets.md subs: done after user confirmation")
    if not status.get("qc", "").startswith("done"):
        raise SystemExit("Final export requires preview qc: done before final export")
    for path in (*sources.clips, *sources.hud_alpha, *sources.stats):
        reject_encoded_intermediate(path)


def reject_encoded_intermediate(path: Path) -> None:
    """发现源和 overlay 共用 RAW_CLIP_PARTS；编码中间产物不能进最终输入。"""
    if not _allowed_source(path):
        raise SystemExit(f"Final export cannot consume encoded preview intermediates: {path.name}")


def escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def make_ass(subtitles: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix="running-final-", suffix=".ass")
    Path(name).write_text(render_ass(parse_txt(subtitles)), encoding="utf-8")
    # mkstemp 的 fd 不再需要；Python 的 Path 写入会重新打开同一路径。
    import os
    os.close(fd)
    return Path(name)


def load_timeline_overlays(
    media_dir: Path,
    durations: list[float],
    *,
    has_open: bool,
    has_close: bool,
    explicit: str | None = None,
) -> list[dict]:
    """按 assemble 的 overlays.json 约定解析到成片时间轴。没有配置就返回空列表。"""
    ov_file = assemble.find_overlays_file(media_dir, explicit)
    if ov_file is None:
        print("Overlays: none", flush=True)
        return []
    close_start, total = assemble.timeline(durations, has_open, has_close)
    loaded = assemble.load_overlays(ov_file, media_dir, file_gate=reject_encoded_intermediate)
    resolved = assemble.resolve_overlays(loaded, close_start, total)
    print(f"Overlays: {ov_file}", flush=True)
    for ov in resolved:
        print(
            f"  #{ov['n']} {ov['file'].name}  {assemble.fmt_ts(ov['t0'])} → {assemble.fmt_ts(ov['t1'])}"
            f"（停住 {ov['hold']:.1f}s）  x={ov['x']} y={ov['y']}"
        )
    return resolved


def build_input_plan(
    sources: SourceSet,
    durations: list[float],
    spec: ExportSpec,
    overlays: list[dict] | None = None,
) -> InputPlan:
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
    for image in sources.stats if sources.close_clip is not None else ():
        stats_indices.append(clip_count + len(alpha_indices) + len(stats_indices))
        args.extend(["-loop", "1", "-framerate", str(spec.timeline.fps), "-t", f"{close_duration:.6f}", "-i", str(image)])
    whoosh_index: int | None = None
    if len(sources.runs) > 1 and WHOOSH_PATH.is_file():
        whoosh_index = clip_count + len(alpha_indices) + len(stats_indices)
        args.extend(["-i", str(WHOOSH_PATH)])
    overlay_indices: list[int] = []
    next_index = clip_count + len(alpha_indices) + len(stats_indices) + (0 if whoosh_index is None else 1)
    for ov in overlays or ():
        overlay_indices.append(next_index)
        args.extend(assemble.overlay_input_spec(ov, fps=spec.timeline.fps))
        next_index += 1
    return InputPlan(
        tuple(args),
        clip_count,
        tuple(alpha_indices),
        tuple(stats_indices),
        close_duration,
        whoosh_index,
        tuple(overlay_indices),
    )


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



def snap_frames(seconds: float, fps: int) -> int:
    """把秒数落到最近的整数帧；时间轴和 trim 都用这个口径。"""
    return max(0, int(round(float(seconds) * fps)))


def frames_to_time(frames: int, fps: int) -> float:
    return frames / fps


def format_frames(frames: int, fps: int) -> str:
    return f"{frames_to_time(frames, fps):.6f}"


def wind_frames(fps: int) -> int:
    """0.08s 在 30fps 上不是整数帧；必须先对齐，否则 trim/color/overlay 各截一截。"""
    return max(1, snap_frames(WIND, fps))


def xfade_frames(fps: int) -> int:
    return max(1, snap_frames(XFADE, fps))


def pre_close_timeline(
    durations: list[float],
    has_open: bool,
    has_close: bool,
    fps: int,
) -> tuple[int, int | None, int]:
    """(vpre 帧数, close xfade 起点帧, 成片总帧数)。

    风刮按帧切开再拼回去，长度必须等于源片段帧数；close xfade 的 offset
    也必须用这个对齐后的 vpre，不能再用未对齐的浮点时长。
    """
    counts = [snap_frames(duration, fps) for duration in durations]
    run_start = 1 if has_open else 0
    run_end = len(counts) - 1 if has_close else len(counts)
    run_counts = counts[run_start:run_end]
    if not run_counts:
        raise ValueError("At least one run clip is required")
    fade = xfade_frames(fps)
    vpre = (counts[0] - fade if has_open else 0) + sum(run_counts)
    if not has_close:
        return vpre, None, vpre
    close_at = max(0, vpre - fade)
    return vpre, close_at, close_at + counts[-1]


def wind_chain(src: str, dst: str, duration: float, width: int, height: int, fps: int, direction: str) -> str:
    """在 run 接缝处保留旧流程的横向风刮转场。"""
    t = f"{duration:.6f}"
    fade_d = 0.02
    bg = f"{dst}bg"
    blur = f"{dst}bl"
    if direction == "out":
        x = f"W*0.62*pow(min(t/{t},1),1.65)"
        fade = f"fade=t=out:st={duration - fade_d:.6f}:d={fade_d:.6f}"
    elif direction == "in":
        x = f"-W*0.62*pow(1-min(t/{t},1),1.65)"
        fade = f"fade=t=in:st=0:d={fade_d:.6f}"
    else:
        raise ValueError(f"unknown wind direction: {direction}")
    return (
        f"color=c=black:s={width}x{height}:d={t}:r={fps},setsar=1,settb=1/{fps}[{bg}];"
        f"[{src}]dblur=angle=0:radius=46,setsar=1[{blur}];"
        f"[{bg}][{blur}]overlay=x='{x}':y=0:shortest=1,{fade},fps={fps},settb=1/{fps},format=yuv420p[{dst}]"
    )


def mix_whoosh(audio_label: str, whoosh_index: int, delays_ms: list[int], volume: float = 0.85) -> str:
    if len(delays_ms) == 1:
        delay = delays_ms[0]
        return (
            f"[{whoosh_index}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"adelay=delays={delay}:all=1,volume={volume:.3f}[wd0];"
            f"[{audio_label}][wd0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amixed]"
        )
    labels = "".join(f"[w{i}]" for i in range(len(delays_ms)))
    parts = [f"[{whoosh_index}:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit={len(delays_ms)}{labels}"]
    mixed = f"[{audio_label}]"
    for i, delay in enumerate(delays_ms):
        delayed = f"[wd{i}]"
        parts.append(f"[w{i}]adelay=delays={delay}:all=1,volume={volume:.3f}{delayed}")
        mixed += delayed
    parts.append(f"{mixed}amix=inputs={len(delays_ms) + 1}:duration=first:dropout_transition=0:normalize=0[amixed]")
    return ";".join(parts)


def transition_graph(
    parts: list[str],
    video_labels: list[str],
    audio_labels: list[str],
    durations: list[float],
    has_open: bool,
    has_close: bool,
    width: int,
    height: int,
    fps: int,
    whoosh_index: int | None,
) -> tuple[str, str]:
    """把旧 assemble 的叠化、风刮和 whoosh 放回新流程的同一张滤镜图。"""
    run_start = 1 if has_open else 0
    run_end = len(durations) - 1 if has_close else len(durations)
    run_indices = list(range(run_start, run_end))
    if not run_indices:
        raise ValueError("At least one run clip is required")

    fade_n = xfade_frames(fps)
    wind_n = wind_frames(fps)
    fade_t = format_frames(fade_n, fps)
    wind_t = format_frames(wind_n, fps)
    counts = [snap_frames(duration, fps) for duration in durations]

    processed: list[tuple[str, str]] = []
    whoosh_delays: list[int] = []
    do_wind = len(run_indices) >= 2 and wind_n >= 1
    for j, index in enumerate(run_indices):
        frames = counts[index]
        video = video_labels[index]
        if not do_wind or frames <= wind_n * 2 + 1:
            processed.append((video, audio_labels[index]))
            continue
        tag = f"r{j}"
        want_in = j != 0
        want_out = j != len(run_indices) - 1
        body_end = frames - wind_n
        if want_in and want_out:
            parts.append(f"[{video}]split=3[{tag}h][{tag}m][{tag}t]")
            parts.append(f"[{tag}h]trim=duration={wind_t},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}hr]")
            parts.append(
                f"[{tag}m]trim=start={wind_t}:end={format_frames(body_end, fps)},"
                f"setpts=PTS-STARTPTS,settb=1/{fps}[{tag}body]"
            )
            parts.append(f"[{tag}t]trim=start={format_frames(body_end, fps)},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}tr]")
            parts.append(wind_chain(f"{tag}hr", f"{tag}hi", frames_to_time(wind_n, fps), width, height, fps, "in"))
            parts.append(wind_chain(f"{tag}tr", f"{tag}to", frames_to_time(wind_n, fps), width, height, fps, "out"))
            parts.append(f"[{tag}hi][{tag}body][{tag}to]concat=n=3:v=1:a=0,fps={fps},settb=1/{fps}[{tag}p]")
        elif want_out:
            parts.append(f"[{video}]split=2[{tag}m][{tag}t]")
            parts.append(f"[{tag}m]trim=duration={format_frames(body_end, fps)},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}body]")
            parts.append(f"[{tag}t]trim=start={format_frames(body_end, fps)},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}tr]")
            parts.append(wind_chain(f"{tag}tr", f"{tag}to", frames_to_time(wind_n, fps), width, height, fps, "out"))
            parts.append(f"[{tag}body][{tag}to]concat=n=2:v=1:a=0,fps={fps},settb=1/{fps}[{tag}p]")
        else:
            parts.append(f"[{video}]split=2[{tag}h][{tag}m]")
            parts.append(f"[{tag}h]trim=duration={wind_t},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}hr]")
            parts.append(f"[{tag}m]trim=start={wind_t},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}body]")
            parts.append(wind_chain(f"{tag}hr", f"{tag}hi", frames_to_time(wind_n, fps), width, height, fps, "in"))
            parts.append(f"[{tag}hi][{tag}body]concat=n=2:v=1:a=0,fps={fps},settb=1/{fps}[{tag}p]")
        processed.append((f"{tag}p", audio_labels[index]))

    first_video, first_audio = processed[0]
    if has_open:
        offset_n = max(0, counts[0] - fade_n)
        parts.append(f"[{video_labels[0]}]fps={fps},settb=1/{fps}[openf]")
        parts.append(
            f"[openf][{first_video}]xfade=transition=fade:duration={fade_t}:offset={format_frames(offset_n, fps)},"
            f"settb=1/{fps}[vcur]"
        )
        parts.append(f"[{audio_labels[0]}][{first_audio}]acrossfade=d={fade_t}[acur]")
        vcur, acur = "vcur", "acur"
        acc_n = counts[0] + counts[run_indices[0]] - fade_n
    else:
        vcur, acur = first_video, first_audio
        acc_n = counts[run_indices[0]]

    for step, (next_video, next_audio) in enumerate(processed[1:], start=1):
        if do_wind:
            whoosh_delays.append(max(0, round(frames_to_time(max(0, acc_n - wind_n), fps) * 1000)))
        parts.append(f"[{vcur}][{next_video}]concat=n=2:v=1:a=0,fps={fps},settb=1/{fps}[vc{step}]")
        parts.append(f"[{acur}][{next_audio}]concat=n=2:v=0:a=1[ac{step}]")
        vcur, acur = f"vc{step}", f"ac{step}"
        acc_n += counts[run_indices[step]]

    if has_close:
        close_index = len(durations) - 1
        vpre_n, offset_n, _total_n = pre_close_timeline(durations, has_open, has_close, fps)
        if acc_n != vpre_n:
            raise ValueError(f"vpre frame count drifted: acc={acc_n} timeline={vpre_n}")
        offset_n = offset_n or 0
        parts.append(f"[{vcur}]fps={fps},settb=1/{fps}[vpre]")
        parts.append(f"[{video_labels[close_index]}]fps={fps},settb=1/{fps}[vclose]")
        parts.append(
            f"[vpre][vclose]xfade=transition=fade:duration={fade_t}:offset={format_frames(offset_n, fps)},"
            f"settb=1/{fps}[vxf]"
        )
        parts.append(f"[{acur}][{audio_labels[close_index]}]acrossfade=d={fade_t}[aclose]")
        vcur, acur = "vxf", "aclose"

    if whoosh_index is not None and whoosh_delays:
        parts.append(mix_whoosh(acur, whoosh_index, whoosh_delays))
        acur = "amixed"
    return vcur, acur


def build_filter_graph(
    sources: SourceSet,
    durations: list[float],
    plan: InputPlan,
    ass: Path | None,
    spec: ExportSpec = FINAL_SPEC,
    measured: dict[str, str] | None = None,
    apply_loudness: bool = True,
    overlays: list[dict] | None = None,
) -> str:
    """最终导出滤镜图。中段静帧叠在转场之后、字幕之前。"""
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
            f"aresample=async=1:first_pts=0,apad=whole_dur={duration:.6f},atrim=0:{duration:.6f},asetpts=PTS-STARTPTS[{a}]"
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
        parts.append(f"[{video_labels[close_i]}][stats]overlay=x=40:y=(H-h)/2:eof_action=repeat:shortest=0[vcstats]")
        video_labels[close_i] = "vcstats"

    vout, aout = transition_graph(
        parts, video_labels, audio_labels, durations,
        sources.open_clip is not None, sources.close_clip is not None,
        width, height, fps, plan.whoosh_index,
    )
    resolved = tuple(overlays or ())
    if len(resolved) != len(plan.overlay_indices):
        raise ValueError(
            f"overlay count {len(resolved)} does not match input plan {len(plan.overlay_indices)}"
        )
    for k, (index, ov) in enumerate(zip(plan.overlay_indices, resolved, strict=True)):
        nxt = f"vov{k}"
        parts.append(assemble.overlay_chain(index, ov, k, vout, nxt, fps=fps))
        vout = nxt
    if ass is not None:
        ass_path = escape_filter_path(ass)
        fontsdir = escape_filter_path(SUBTITLE_FONTS_DIR)
        parts.append(f"[{vout}]subtitles={ass_path}:fontsdir={fontsdir}:charenc=UTF-8[v]")
    else:
        parts.append(f"[{vout}]format=yuv420p[v]")
    if apply_loudness:
        parts.append(f"[{aout}]{loudness_filter(spec, measured)}[a]")
    else:
        parts.append(f"[{aout}]aformat=sample_rates={spec.timeline.sample_rate}:channel_layouts=stereo[a]")
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


def build_encode_cmd(
    plan: InputPlan,
    graph: str,
    output: Path,
    test_codec: str | None = None,
    spec: ExportSpec = FINAL_SPEC,
    filter_threads: int = 1,
) -> list[str]:
    # 滤镜线程必须写在第一个 -i 前面。不要加 -threads 1，那会限制 VideoToolbox。
    # 没有时间表的整段原片路径保持 1。确认导出的分段图用 CONFIRMED_FILTER_THREADS。
    if filter_threads < 1:
        raise ValueError("filter_threads must be >= 1")
    codec_args = video_codec_args(spec, test_codec=test_codec)
    return [
        "ffmpeg", "-y", "-hide_banner",
        "-filter_complex_threads", str(filter_threads),
        *plan.args,
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        *codec_args,
        "-pix_fmt", spec.timeline.pix_fmt,
        *audio_codec_args(spec), "-movflags", "+faststart", str(output),
    ]


def measure_loudness(plan: InputPlan, graph: str) -> dict[str, str] | None:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", *plan.args, "-filter_complex", graph, "-map", "[a]", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-8:])
        print(f"Loudnorm pass 1 failed: rc={proc.returncode}", flush=True)
        if tail:
            print(tail, flush=True)
        return None
    measured = parse_loudnorm(proc.stderr)
    if measured is None:
        print("Loudnorm pass 1: could not parse loudnorm JSON", flush=True)
    return measured


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--episode-dir")
    parser.add_argument("--subtitles", help="默认 <episode-dir>/subtitles.txt")
    parser.add_argument("--out")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument(
        "--measure-only",
        action="store_true",
        help="Measure loudnorm pass 1 from the frozen program mix. Does not write a final file and does not need confirmed subtitles",
    )
    parser.add_argument("--test-codec", choices=("libx264",), help="仅隔离测试使用")
    parser.add_argument(
        "--overlays",
        help="叠加层配置 JSON。默认找 <media-dir>/overlays.json，再找 episodes/<媒体目录名>/overlays.json",
    )
    parser.add_argument("--no-overlays", action="store_true", help="有 overlays.json 也不叠")
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="不烧硬字幕。默认仍按当前 skill 在一次编码里烧 ASS；需要只出外挂 SRT 时加这个开关。",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="补画 HUD 透明层的并行路数，默认 2。不改变确认导出的分段编码。"
        "8 核机器建议 6，留 1 到 2 核给系统和写 mov 的 ffmpeg",
    )
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    media_dir = Path(args.media_dir).expanduser().resolve()
    if args.measure_only:
        with log_timeline.span(media_dir, "loudness-measure", enabled=not args.dry_run) as wall:
            wall.rc = _measure_only(args, media_dir)
            return wall.rc
    if not args.episode_dir or not args.out:
        raise SystemExit("final export requires --episode-dir and --out")
    with log_timeline.span(media_dir, "final-export", enabled=not args.dry_run) as wall:
        wall.rc = _export_episode(args)
        return wall.rc


PROGRAM_SOURCE_FORBIDDEN = (
    "hud-preview",
    "review-preview",
    "close-stats",
    "run-final",
    "no-subs",
    "truncated",
    "no-burn",
)


# 小于一帧的起点当成从片头开始，不 seek，滤镜仍用原片绝对时间。
_SEEK_EPSILON_S = 1e-4


def source_is_seeked(start_s: float) -> bool:
    """这组切片的第一段不在片头时，在 -i 前 seek。从片头开始不 seek，避免改掉已对齐的帧边界。"""
    return float(start_s) > _SEEK_EPSILON_S


@dataclass(frozen=True)
class ClipOpening:
    """一次打开的原片。slices 是时间表下标，按成片顺序，原片时间不回头。"""

    clip: str
    seek_s: float | None
    slices: tuple[int, ...]


def clip_openings(slices: list[dict], break_before: set[int] | None = None) -> list[ClipOpening]:
    """同一条原片的顺向句间刀共用一次 -i。

    原片时间往回走（冷开场取了后面的一段）时另开一路。一个解码器只能往前读，
    倒 seek 会把已经错过的帧丢掉。`break_before` 里的下标强制另开一路，用来
    把风刮、xfade 或 HUD 开关两边拆开。
    """
    breaks = break_before or set()
    openings: list[ClipOpening] = []
    active: dict[str, int] = {}
    for index, sl in enumerate(slices):
        start = float(sl["src_start_s"])
        clip = str(sl["clip"])
        slot = active.get(clip)
        if slot is not None and index not in breaks:
            previous = openings[slot]
            last = slices[previous.slices[-1]]
            if start >= float(last["src_end_s"]) - 1e-6:
                openings[slot] = ClipOpening(previous.clip, previous.seek_s, previous.slices + (index,))
                continue
        seek = start if source_is_seeked(start) else None
        active[clip] = len(openings)
        openings.append(ClipOpening(clip, seek, (index,)))
    return openings


def program_openings(timeline: list[dict], wind_ids: set[str]) -> list[ClipOpening]:
    """画面输入按 act 打开。一个 act 里的句间刀仍共用一次 -i。"""
    breaks = {act[0] for act in _program_acts(timeline, wind_ids)}
    breaks.discard(0)
    return clip_openings(timeline, break_before=breaks)


def slice_trim_window(sl: dict, seek_s: float | None) -> tuple[float, float]:
    """seek 把时间戳拨回 0，trim 从 0 量。没 seek 的仍用原片绝对时间。"""
    start = float(sl["src_start_s"])
    end = float(sl["src_end_s"])
    if seek_s is not None:
        return start - seek_s, end - seek_s
    return start, end


def _source_pads(
    parts: list[str],
    slices: list[dict],
    *,
    video: bool,
    wind_ids: set[str] | None = None,
) -> tuple[list[ClipOpening], list[str], list[str], list[tuple[float, float]]]:
    """把共用的原片拆成每段一个音频入口。只有一段时不插 asplit。

    画面不再走 split。split 的输出要等 concat 逐个来读，没读到的那几路会把
    已经解码的帧留到这段结束，足迹随时间涨。`wind_ids` 给定时按 act 断开输入，
    和 `program_input_args` 使用同一组开口。测响度不传，避免改掉已测的音频图。
    """
    if wind_ids is None:
        openings = clip_openings(slices)
    else:
        openings = program_openings(slices, wind_ids)
    video_pads = [""] * len(slices)
    audio_pads = [""] * len(slices)
    windows: list[tuple[float, float]] = [(0.0, 0.0)] * len(slices)
    for input_index, opening in enumerate(openings):
        for index in opening.slices:
            windows[index] = slice_trim_window(slices[index], opening.seek_s)
        if len(opening.slices) == 1:
            index = opening.slices[0]
            video_pads[index] = f"{input_index}:v"
            audio_pads[index] = f"{input_index}:a"
            continue
        n = len(opening.slices)
        if video:
            labels = "".join(f"[c{input_index}v{k}]" for k in range(n))
            parts.append(f"[{input_index}:v]split={n}{labels}")
        labels = "".join(f"[c{input_index}a{k}]" for k in range(n))
        parts.append(f"[{input_index}:a]asplit={n}{labels}")
        for k, index in enumerate(opening.slices):
            video_pads[index] = f"c{input_index}v{k}"
            audio_pads[index] = f"c{input_index}a{k}"
    if any(pad == "" for pad in audio_pads):
        raise ValueError("program input plan left a slice without a source")
    return openings, video_pads, audio_pads, windows


# 输入 -t 多读的余量。select 不会自己结束，没有 -t 就会一直解码到原片末尾再丢掉。
_INPUT_TAIL_S = 0.5


def _opening_limit_args(opening: ClipOpening, slices: list[dict]) -> list[str]:
    """-ss 和 -t 成对：只解码这一路最后一个出点之前的画面。"""
    end = max(float(slices[index]["src_end_s"]) for index in opening.slices)
    start = opening.seek_s or 0.0
    args = ["-ss", f"{opening.seek_s:.6f}"] if opening.seek_s is not None else []
    return args + ["-t", f"{end - start + _INPUT_TAIL_S:.6f}"]


def _clip_input_args(media_dir: Path, slices: list[dict]) -> list[str]:
    args: list[str] = []
    for opening in clip_openings(slices):
        # 只跳过这段最早入点之前的画面。刀和刀之间的空隙仍会解码再丢掉。
        # 和滤镜里「seek 之后从 0 量」是一对，不能只改一边。
        args.extend(_opening_limit_args(opening, slices))
        args.extend(["-i", str(media_dir / opening.clip)])
    return args


def _program_alpha_mode(job: dict, durations: dict[str, float]) -> str:
    full = durations.get(job["clip"])
    if full is None:
        return "kept"
    if job["src_start_s"] <= 0.02 and job["src_end_s"] >= full - 0.02:
        return "full"
    return "kept"


def _program_wind_visual(
    parts: list[str],
    src: str,
    frames: int,
    wind_n: int,
    want_in: bool,
    want_out: bool,
    tag: str,
    fps: int,
    width: int,
    height: int,
) -> str:
    """把一段的头/尾换成和旧 transition_graph 一样的风刮。时长不变。"""
    if wind_n < 1 or frames <= wind_n * 2 + 1 or not (want_in or want_out):
        return src
    wind_t = format_frames(wind_n, fps)
    wind_time = frames_to_time(wind_n, fps)
    body_end = frames - wind_n
    if want_in and want_out:
        parts.append(f"[{src}]split=3[{tag}h][{tag}m][{tag}t]")
        parts.append(f"[{tag}h]trim=duration={wind_t},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}hr]")
        parts.append(
            f"[{tag}m]trim=start={wind_t}:end={format_frames(body_end, fps)},"
            f"setpts=PTS-STARTPTS,settb=1/{fps}[{tag}body]"
        )
        parts.append(f"[{tag}t]trim=start={format_frames(body_end, fps)},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}tr]")
        parts.append(wind_chain(f"{tag}hr", f"{tag}hi", wind_time, width, height, fps, "in"))
        parts.append(wind_chain(f"{tag}tr", f"{tag}to", wind_time, width, height, fps, "out"))
        parts.append(f"[{tag}hi][{tag}body][{tag}to]concat=n=3:v=1:a=0,fps={fps},settb=1/{fps}[{tag}p]")
    elif want_out:
        parts.append(f"[{src}]split=2[{tag}m][{tag}t]")
        parts.append(f"[{tag}m]trim=duration={format_frames(body_end, fps)},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}body]")
        parts.append(f"[{tag}t]trim=start={format_frames(body_end, fps)},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}tr]")
        parts.append(wind_chain(f"{tag}tr", f"{tag}to", wind_time, width, height, fps, "out"))
        parts.append(f"[{tag}body][{tag}to]concat=n=2:v=1:a=0,fps={fps},settb=1/{fps}[{tag}p]")
    else:
        parts.append(f"[{src}]split=2[{tag}h][{tag}m]")
        parts.append(f"[{tag}h]trim=duration={wind_t},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}hr]")
        parts.append(f"[{tag}m]trim=start={wind_t},setpts=PTS-STARTPTS,settb=1/{fps}[{tag}body]")
        parts.append(wind_chain(f"{tag}hr", f"{tag}hi", wind_time, width, height, fps, "in"))
        parts.append(f"[{tag}hi][{tag}body]concat=n=2:v=1:a=0,fps={fps},settb=1/{fps}[{tag}p]")
    return f"{tag}p"


def _program_acts(timeline: list[dict], wind_ids: set[str]) -> list[tuple[int, ...]]:
    """把时间表收成几段：同一条原片上连续、顺向、没有转场的句间刀合成一段。

    open、每一段跑、close 各是一段。换原片、原片时间往回、xfade、风刮，
    或者 HUD 开关变了，都另起一段。这样一段里面的窗口能接成一条再叠一次。
    """
    acts: list[list[int]] = []
    for index, sl in enumerate(timeline):
        if not acts:
            acts.append([index])
            continue
        prev = timeline[acts[-1][-1]]
        forward = float(sl["src_start_s"]) >= float(prev["src_end_s"]) - 1e-6
        if (
            sl["clip"] == prev["clip"]
            and forward
            and int(sl["fade_frames"]) == 0
            and sl["id"] not in wind_ids
            and bool(sl["hud"]) == bool(prev["hud"])
        ):
            acts[-1].append(index)
        else:
            acts.append([index])
    return [tuple(act) for act in acts]


def _concat_ready(parts: list[str], labels: list[str], *, video: bool, tag: str, fps: int) -> str:
    """一段里只有一个切片时不插 concat，滤镜串和原先逐段拼接保持一致。"""
    if len(labels) == 1:
        return labels[0]
    joined = "".join(f"[{label}]" for label in labels)
    if video:
        parts.append(f"{joined}concat=n={len(labels)}:v=1:a=0,fps={fps},settb=1/{fps}[{tag}]")
    else:
        parts.append(f"{joined}concat=n={len(labels)}:v=0:a=1[{tag}]")
    return tag


def _ffconcat_quote(path: Path) -> str:
    text = str(path).replace("\\", "\\\\").replace("'", "\\'")
    return "'" + text + "'"


def _write_alpha_concat(paths: tuple[Path, ...], dest: Path) -> None:
    """把短窗口 mov 列进 concat 解复用清单。不重编码，也不铺成整段透明底。"""
    lines = ["ffconcat version 1.0"]
    lines.extend("file " + _ffconcat_quote(path) for path in paths)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def confirmed_alpha_groups(table: dict, alpha_paths: list[Path], fps: int = 30) -> list[tuple[Path, ...]]:
    """每个要画 HUD 的段一条 alpha。同一条原片的窗口按成片顺序排在一组里。"""
    timeline = edl.frame_timeline(table, fps)
    wind_ids = {str(item["before_id"]) for item in edl.wind_transitions(table)}
    acts = _program_acts(timeline, wind_ids)
    hud_indexes = [index for index, sl in enumerate(timeline) if sl["hud"]]
    if len(hud_indexes) != len(alpha_paths):
        raise ValueError("HUD alpha count does not match hud slices")
    path_at = {index: alpha_paths[pos] for pos, index in enumerate(hud_indexes)}
    groups: list[tuple[Path, ...]] = []
    for act in acts:
        group = tuple(path_at[index] for index in act if index in path_at)
        if not group:
            continue
        if len(group) != len(act):
            raise ValueError("HUD windows in one act must cover every slice of that act")
        groups.append(group)
    return groups


def _picture_chain(width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},settb=1/{fps},format=yuv420p,setsar=1"
    )


def _opening_video(
    parts: list[str],
    input_index: int,
    ranges: list[tuple[float, float]],
    width: int,
    height: int,
    fps: int,
) -> str:
    """一次打开的画面只留一个消费者。多段句间刀用 select，不 split。

    先 fps 落到成片帧率，再按成片帧挑。原片是 30000/1001 时，在原片时间上挑再补帧，
    每个区间会差半帧，一段两分钟累计少 1–4 帧，段接起来画面越来越早于声音。
    窗口端点都是 1/fps 的整数倍，往前让半帧，挑出来的帧数恰好是区间帧数之和。
    -ss 之后第一帧可能落在 0 之后不到一帧，start_time=0 让 fps 从 0 补齐，不然少第一帧。
    """
    half = 0.5 / fps
    expr = "+".join(f"gte(t\\,{start - half:.6f})*lt(t\\,{end - half:.6f})" for start, end in ranges)
    frames = sum(int(round((end - start) * fps)) for start, end in ranges)
    head = f"fps={fps}:start_time=0,select='{expr}',setpts=N/{fps}/TB,trim=end_frame={frames}"
    label = f"ov{input_index}"
    parts.append(f"[{input_index}:v]{head},{_picture_chain(width, height, fps)}[{label}]")
    return label


def _kept_alpha_trim(skip: float, dur: float) -> str:
    """窗口 mov 从 0 起。段从窗口中间开始时，要跳过前面已经画过的透明层。"""
    if skip > 1e-6:
        return f"trim=start={skip:.6f}:end={skip + dur:.6f},setpts=PTS-STARTPTS"
    return f"trim=duration={dur:.6f},setpts=PTS-STARTPTS"


def build_program_filter(
    table: dict,
    alpha_modes: list[str],
    overlay_count: int,
    ass: Path | None,
    spec: ExportSpec = FINAL_SPEC,
    measured: dict[str, str] | None = None,
    apply_loudness: bool = True,
    alpha_skip: dict[str, float] | None = None,
    video_only: bool = False,
) -> str:
    """按时间表裁切、叠 HUD、转场、贴图、烧字幕、响度。

    `video_only` 时不建音频支路，只出 [v]。确认导出的分段走这条：音频整片一次混好，
    不再每段重启 dynaudnorm/loudnorm，也不让音频滤镜的几秒延迟把未压缩画面垫在内存里。预览用的是同一组落帧区间。

    句间刀先收成 open / 每一段跑 / close。一段跑上的窗口透明层已经在输入侧收成一条，
    这里只叠一次。画面用 select 或单段 trim，不用 split。测响度的音频图不走这条，
    仍按切片拼接，好让已测的 loudness.json 继续对得上。
    `alpha_skip` 是切片 id → 透明层要从窗口开头跳过的秒数，分段导出切在窗口中间时用。
    """
    fps = spec.timeline.fps
    timeline = edl.frame_timeline(table, fps)
    if not timeline:
        raise ValueError("program timeline has no segments")
    width, height = spec.timeline.width, spec.timeline.height
    parts: list[str] = []
    audio_labels: list[str] = []
    durations: list[float] = []
    winds = {item["before_id"]: item for item in edl.wind_transitions(table)}
    wind_ids = set(winds)
    aparts: list[str] = [] if video_only else parts
    openings, _video_pads, audio_pads, windows = _source_pads(aparts, timeline, video=False, wind_ids=wind_ids)
    video_of: dict[int, str] = {}
    for input_index, opening in enumerate(openings):
        label = _opening_video(
            parts, input_index, [windows[index] for index in opening.slices], width, height, fps,
        )
        for index in opening.slices:
            video_of[index] = label
    for index, sl in enumerate(timeline):
        dur = sl["frames"] / fps
        durations.append(dur)
        trim_start, trim_end = windows[index]
        aparts.append(
            f"[{audio_pads[index]}]atrim=start={trim_start:.6f}:end={trim_end:.6f},asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates={spec.timeline.sample_rate}:channel_layouts=stereo,"
            f"aresample=async=1:first_pts=0,apad=whole_dur={dur:.6f},atrim=0:{dur:.6f}[a{index}]"
        )
        audio_labels.append(f"a{index}")
    skips = alpha_skip or {}

    hud_count = sum(1 for sl in timeline if sl["hud"])
    if len(alpha_modes) != hud_count:
        raise ValueError("HUD alpha count does not match hud slices")
    modes_at: dict[int, str] = {}
    hud_at = 0
    for index, sl in enumerate(timeline):
        if not sl["hud"]:
            continue
        modes_at[index] = alpha_modes[hud_at]
        hud_at += 1
    acts = _program_acts(timeline, wind_ids)
    alpha_at: dict[int, int] = {}
    next_input = len(openings)
    for act_i, act in enumerate(acts):
        if any(timeline[index]["hud"] for index in act):
            alpha_at[act_i] = next_input
            next_input += 1
    wind_out: dict[str, dict] = {}
    for index, sl in enumerate(timeline[:-1]):
        nxt = timeline[index + 1]["id"]
        if nxt in winds:
            wind_out[sl["id"]] = winds[nxt]

    act_video: list[str] = []
    act_audio: list[str] = []
    for act_i, act in enumerate(acts):
        # 一个 act 的画面已经是一条 select/trim。这里只接音频。标签相同就不要再 concat。
        picture = []
        for index in act:
            if not picture or picture[-1] != video_of[index]:
                picture.append(video_of[index])
        vlabel = _concat_ready(parts, picture, video=True, tag=f"gv{act_i}", fps=fps)
        alabel = _concat_ready(aparts, [audio_labels[index] for index in act], video=False, tag=f"ga{act_i}", fps=fps)
        if act_i in alpha_at:
            anchor = act[0]
            if len(act) == 1:
                mode = modes_at[anchor]
                sl = timeline[anchor]
                if mode == "full":
                    trim = f"trim=start={sl['src_start_s']:.6f}:end={sl['src_end_s']:.6f},setpts=PTS-STARTPTS"
                else:
                    trim = _kept_alpha_trim(float(skips.get(sl["id"], 0.0)), durations[anchor])
            else:
                if any(modes_at[index] == "full" for index in act):
                    raise ValueError("a run with several windows cannot use a full-length HUD alpha")
                frames = sum(int(timeline[index]["frames"]) for index in act)
                trim = _kept_alpha_trim(float(skips.get(timeline[anchor]["id"], 0.0)), frames / fps)
            parts.append(f"[{alpha_at[act_i]}:v]{trim},fps={fps},format=rgba[ha{anchor}]")
            parts.append(f"[{vlabel}][ha{anchor}]overlay=eof_action=pass:shortest=0:format=auto[vh{anchor}]")
            vlabel = f"vh{anchor}"
        first, last = timeline[act[0]], timeline[act[-1]]
        incoming = winds.get(first["id"])
        outgoing = wind_out.get(last["id"])
        if incoming or outgoing:
            wind_n = max(1, snap_frames(float((incoming or outgoing)["duration_s"]), fps))
            frames = sum(int(timeline[index]["frames"]) for index in act)
            vlabel = _program_wind_visual(
                parts, vlabel, frames, wind_n,
                bool(incoming), bool(outgoing), f"rw{act[0]}", fps, width, height,
            )
        act_video.append(vlabel)
        act_audio.append(alabel)

    vcur, acur = act_video[0], act_audio[0]
    whoosh_delays: list[int] = []
    for act_i in range(1, len(acts)):
        head = timeline[acts[act_i][0]]
        # 段内已经接好。这里只在段和段之间做 xfade 或硬切，offset 仍是下一段第一帧。
        # 每段恰好一个切片时，段号就是时间表下标，转场标签和以前逐段拼接相同。
        join = acts[act_i][0] if len(acts) == len(timeline) else act_i
        fade_n = int(head["fade_frames"])
        if fade_n:
            # offset 用落帧后的起点。浮点累计会比 fps 滤镜的真实长度长出几帧，close 就会被 xfade 丢掉。
            offset = head["program_start_frame"] / fps
            fade_t = fade_n / fps
            parts.append(
                f"[{vcur}][{act_video[act_i]}]xfade=transition=fade:duration={fade_t:.6f}:offset={offset:.6f},settb=1/{fps}[vx{join}]"
            )
            aparts.append(f"[{acur}][{act_audio[act_i]}]acrossfade=d={fade_t:.6f}[ax{join}]")
        else:
            wind = winds.get(head["id"])
            if wind:
                wind_n = max(1, snap_frames(float(wind["duration_s"]), fps))
                seam = int(head["program_start_frame"])
                whoosh_delays.append(max(0, round(frames_to_time(max(0, seam - wind_n), fps) * 1000)))
            parts.append(
                f"[{vcur}][{act_video[act_i]}]concat=n=2:v=1:a=0,fps={fps},settb=1/{fps}[vx{join}]"
            )
            aparts.append(f"[{acur}][{act_audio[act_i]}]concat=n=2:v=0:a=1[ax{join}]")
        vcur, acur = f"vx{join}", f"ax{join}"

    n_whoosh = 1 if winds else 0
    whoosh_index = len(openings) + len(alpha_at) if n_whoosh else None
    if whoosh_index is not None and whoosh_delays:
        aparts.append(mix_whoosh(acur, whoosh_index, whoosh_delays))
        acur = "amixed"
    overlay_base = len(openings) + len(alpha_at) + n_whoosh
    for k, ov in enumerate(table.get("overlays") or []):
        nxt = f"vov{k}"
        parts.append(_program_overlay_chain(overlay_base + k, ov, k, vcur, nxt, height=height))
        vcur = nxt
    if overlay_count != len(table.get("overlays") or []):
        raise ValueError("overlay input count does not match the program")
    if ass is not None:
        parts.append(
            f"[{vcur}]subtitles={escape_filter_path(ass)}:fontsdir={escape_filter_path(SUBTITLE_FONTS_DIR)}:charenc=UTF-8[v]"
        )
    else:
        parts.append(f"[{vcur}]format=yuv420p[v]")
    if video_only:
        return ";".join(parts)
    if apply_loudness:
        parts.append(f"[{acur}]{loudness_filter(spec, measured)}[a]")
    else:
        parts.append(f"[{acur}]aformat=sample_rates={spec.timeline.sample_rate}:channel_layouts=stereo[a]")
    return ";".join(parts)


def _program_overlay_chain(index: int, ov: dict, k: int, vin: str, vout: str, *, height: int) -> str:
    start = float(ov["program_start_s"])
    end = float(ov["program_end_s"])
    span = end - start
    if ov.get("role") == "stats":
        scale = f"scale=-2:{max(320, int(height * 0.82))}:force_original_aspect_ratio=decrease,format=rgba,colorchannelmixer=aa=0.82"
        x = ov.get("x") or "40"
        y = ov.get("y") or "(H-h)/2"
    else:
        scale = "format=yuva420p"
        if ov.get("width"):
            scale = f"scale={int(ov['width'])}:-2,format=yuva420p"
        opacity = float(ov.get("opacity") or 1)
        if opacity < 1:
            scale += f",colorchannelmixer=aa={opacity:.3f}"
        x = ov.get("x") or "0"
        y = ov.get("y") or "0"
    return (
        f"[{index}:v]{scale},trim=duration={span:.6f},setpts=PTS-STARTPTS+{start:.6f}/TB[ol{k}];"
        f"[{vin}][ol{k}]overlay=x={x}:y={y}:eof_action=pass:format=auto"
        f":enable='between(t,{start:.6f},{end:.6f})'[{vout}]"
    )


# 刀点只挪了这么多秒时，沿用已测的响度。更大的时间表改动必须重测。
TINY_LOUDNESS_DELTA_S = 1.0
LOUDNESS_NAME = "loudness.json"


def audio_signature(table: dict, fps: int = 30) -> dict:
    """响度只看切点、风刮和 whoosh。字幕文字和时间不是输入。"""
    timeline = edl.frame_timeline(table, fps)
    return {
        "duration_s": round(edl.frame_program_duration(table, fps), 3),
        "slices": [
            [sl["clip"], round(float(sl["src_start_s"]), 3), round(float(sl["src_end_s"]), 3)]
            for sl in timeline
        ],
        "wind": [
            [str(item.get("before_id")), round(float(item["duration_s"]), 3)]
            for item in edl.wind_transitions(table)
        ],
    }


def loudness_path(media_dir: Path) -> Path:
    return media_dir / "logs" / LOUDNESS_NAME


def read_loudness(media_dir: Path) -> dict | None:
    path = loudness_path(media_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_loudness(media_dir: Path, table: dict, measured: dict[str, str]) -> Path:
    path = loudness_path(media_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "tiny_delta_s": TINY_LOUDNESS_DELTA_S,
        "signature": audio_signature(table),
        "measured": measured,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def loudness_reusable(saved: dict | None, table: dict) -> bool:
    if not isinstance(saved, dict) or not isinstance(saved.get("measured"), dict):
        return False
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(key in saved["measured"] for key in keys):
        return False
    new = audio_signature(table)
    old = saved.get("signature")
    if old == new:
        return True
    if not isinstance(old, dict):
        return False
    old_slices = old.get("slices") or []
    new_slices = new["slices"]
    if not isinstance(old_slices, list) or len(old_slices) != len(new_slices):
        return False
    try:
        if [row[0] for row in old_slices] != [row[0] for row in new_slices]:
            return False
        if len(old.get("wind") or []) != len(new["wind"]):
            return False
        duration_delta = abs(float(old.get("duration_s")) - float(new["duration_s"]))
        shift = 0.0
        for before, after in zip(old_slices, new_slices, strict=True):
            shift += abs(float(before[1]) - float(after[1])) + abs(float(before[2]) - float(after[2]))
    except (TypeError, ValueError, IndexError):
        return False
    return duration_delta <= TINY_LOUDNESS_DELTA_S and shift <= TINY_LOUDNESS_DELTA_S


def program_audio_input_args(media_dir: Path, table: dict, spec: ExportSpec = FINAL_SPEC) -> list[str]:
    """测响度只解码成片用到的音频。不读透明层、贴图或字幕。同一条原片只打开一次。"""
    args = _clip_input_args(media_dir, edl.export_slices(table, spec.timeline.fps))
    if edl.wind_transitions(table):
        if not WHOOSH_PATH.is_file():
            raise SystemExit(f"wind transitions need whoosh audio: {WHOOSH_PATH}")
        args.extend(["-i", str(WHOOSH_PATH)])
    return args


def build_program_audio_filter(
    table: dict,
    spec: ExportSpec = FINAL_SPEC,
    measured: dict[str, str] | None = None,
    apply_loudness: bool = True,
) -> str:
    """成片混音：切点、xfade、风刮接缝上的 whoosh。没有画面，也没有字幕。"""
    fps = spec.timeline.fps
    timeline = edl.frame_timeline(table, fps)
    if not timeline:
        raise ValueError("program timeline has no segments")
    parts: list[str] = []
    audio_labels: list[str] = []
    openings, _video_pads, audio_pads, windows = _source_pads(parts, timeline, video=False)
    for index, sl in enumerate(timeline):
        dur = sl["frames"] / fps
        trim_start, trim_end = windows[index]
        parts.append(
            f"[{audio_pads[index]}]atrim=start={trim_start:.6f}:end={trim_end:.6f},asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates={spec.timeline.sample_rate}:channel_layouts=stereo,"
            f"aresample=async=1:first_pts=0,apad=whole_dur={dur:.6f},atrim=0:{dur:.6f}[a{index}]"
        )
        audio_labels.append(f"a{index}")
    winds = {item["before_id"]: item for item in edl.wind_transitions(table)}
    acur = audio_labels[0]
    whoosh_delays: list[int] = []
    for index in range(1, len(timeline)):
        fade_n = int(timeline[index]["fade_frames"])
        if fade_n:
            fade_t = fade_n / fps
            parts.append(f"[{acur}][{audio_labels[index]}]acrossfade=d={fade_t:.6f}[ax{index}]")
        else:
            wind = winds.get(timeline[index]["id"])
            if wind:
                wind_n = max(1, snap_frames(float(wind["duration_s"]), fps))
                seam = int(timeline[index]["program_start_frame"])
                whoosh_delays.append(max(0, round(frames_to_time(max(0, seam - wind_n), fps) * 1000)))
            parts.append(f"[{acur}][{audio_labels[index]}]concat=n=2:v=0:a=1[ax{index}]")
        acur = f"ax{index}"
    if winds and whoosh_delays:
        parts.append(mix_whoosh(acur, len(openings), whoosh_delays))
        acur = "amixed"
    if apply_loudness:
        parts.append(f"[{acur}]{loudness_filter(spec, measured)}[a]")
    else:
        parts.append(f"[{acur}]aformat=sample_rates={spec.timeline.sample_rate}:channel_layouts=stereo[a]")
    graph = ";".join(parts)
    if "subtitles=" in graph:
        raise ValueError("loudness graph must not burn subtitles")
    return graph


def measure_program_loudness(media_dir: Path, table: dict) -> dict[str, str] | None:
    graph = build_program_audio_filter(table, measured=None)
    openings = clip_openings(edl.export_slices(table))
    plan = InputPlan(tuple(program_audio_input_args(media_dir, table)), len(openings), (), (), 0.0)
    return measure_loudness(plan, graph)


def _loudness_for_export(media_dir: Path, table: dict, *, dry_run: bool) -> dict[str, str] | None:
    saved = read_loudness(media_dir)
    if loudness_reusable(saved, table):
        measured = saved["measured"] if saved is not None else None
        print(f"Loudnorm pass 1 reused I={measured['input_i']}", flush=True)
        return measured
    if dry_run:
        print("would measure program loudness from the frozen timeline; subtitles are not an input", flush=True)
        return None
    measured = measure_program_loudness(media_dir, table)
    if measured is not None:
        print(f"Loudnorm pass 1: I={measured['input_i']} TP={measured['input_tp']}", flush=True)
        write_loudness(media_dir, table, measured)
    return measured


def _is_keep_intermediate(path: Path) -> bool:
    parts = path.parts
    return "hud-renders" in parts and "keeps" in parts


def _measure_only(args, media_dir: Path) -> int:
    """校对字幕时可以先测。不写最终文件，也不看字幕确认没有。"""
    if not edl.program_path(media_dir).is_file():
        raise SystemExit("loudness measure needs logs/program.json")
    table = edl.load_media(media_dir)
    problems = edl.validate(table, require_frozen=True)
    if problems:
        raise SystemExit("program timeline: " + "; ".join(problems))
    if todo_list.load(media_dir).get("preview") != "done":
        raise SystemExit("loudness measure needs preview done; it does not need confirmed subtitles")
    for sl in edl.export_slices(table):
        _reject_program_source(sl["clip"])
        if _is_keep_intermediate(media_dir / sl["clip"]):
            raise SystemExit(f"loudness measure reads original clips, not keeps: {sl['clip']}")
        if not (media_dir / sl["clip"]).is_file() and not args.dry_run:
            raise SystemExit(f"program clip not found: {media_dir / sl['clip']}")
    saved = read_loudness(media_dir)
    if loudness_reusable(saved, table):
        print(f"Loudnorm pass 1 reused I={saved['measured']['input_i']}", flush=True)
        if not args.dry_run:
            todo_list.mark(media_dir, "loudness-measure", "done")
        return 0
    if args.dry_run:
        print("would measure program loudness from the frozen timeline; subtitles are not an input", flush=True)
        return 0
    measured = measure_program_loudness(media_dir, table)
    if measured is None:
        raise SystemExit("Loudnorm pass 1 failed")
    write_loudness(media_dir, table, measured)
    print(f"Loudnorm pass 1: I={measured['input_i']} TP={measured['input_tp']}", flush=True)
    todo_list.mark(media_dir, "loudness-measure", "done")
    return 0


def program_input_args(
    media_dir: Path,
    table: dict,
    alpha_paths: list[Path],
    spec: ExportSpec = FINAL_SPEC,
    *,
    list_dir: Path | None = None,
) -> list[str]:
    """确认导出的输入。原片按条打开。一段跑的窗口透明层收成一个输入。

    多个短 mov 用 concat 解复用列在一张清单里，滤镜图只看到一条 alpha。
    不在滤镜图里为每个窗口留一个输入：那些 ARGB 解码器会一起常驻，16GB 机器会被杀掉。
    清单只是这几条短文件的路径，不是整段未压缩透明底，用完要删。
    """
    fps = spec.timeline.fps
    timeline = edl.frame_timeline(table, fps)
    wind_ids = {str(item["before_id"]) for item in edl.wind_transitions(table)}
    args: list[str] = []
    for opening in program_openings(timeline, wind_ids):
        args.extend(_opening_limit_args(opening, timeline))
        args.extend(["-i", str(media_dir / opening.clip)])
    for index, group in enumerate(confirmed_alpha_groups(table, alpha_paths, fps)):
        if len(group) == 1:
            args.extend(["-i", str(group[0])])
            continue
        if list_dir is None:
            raise ValueError("confirmed export needs list_dir to concat HUD window alphas")
        list_dir.mkdir(parents=True, exist_ok=True)
        listing = list_dir / f"alpha-{index:02d}.ffconcat"
        _write_alpha_concat(group, listing)
        args.extend(["-f", "concat", "-safe", "0", "-i", str(listing)])
    if edl.wind_transitions(table):
        if not WHOOSH_PATH.is_file():
            raise SystemExit(f"wind transitions need whoosh audio: {WHOOSH_PATH}")
        args.extend(["-i", str(WHOOSH_PATH)])
    for ov in table.get("overlays") or []:
        span = float(ov["program_end_s"]) - float(ov["program_start_s"])
        asset = media_dir / ov["asset"]
        args.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{span:.6f}", "-i", str(asset)])
    return args


# 大约两分钟。整片那张图在 16GB 上足迹随成片时间涨，两分钟是留给桌面程序的上限。
# 画面分段之后音频整片只混一次，段间不再有 AAC 接缝。
SEGMENT_MAX_S = 120.0
# 只并掉片尾的零头。10 秒以内不再单独开一段。
SEGMENT_TAIL_MERGE_S = 10.0
# 小分段图用 3。整片上百个 auto_scale 才会在默认多线程下 EAGAIN，那种图不再建。
# 这一段若十几秒内起不来，退回 1。不要加 -threads 1。
CONFIRMED_FILTER_THREADS = 3
FILTER_THREAD_RETRY_S = 15.0
_WHOOSH_SECONDS: float | None = None


@dataclass(frozen=True)
class ExportSegment:
    """成片帧区间 [start_frame, end_frame)。下一段从 end_frame 接着编码。"""

    start_frame: int
    end_frame: int

    @property
    def frames(self) -> int:
        return self.end_frame - self.start_frame


def whoosh_duration_s() -> float:
    global _WHOOSH_SECONDS
    if _WHOOSH_SECONDS is None:
        import wave

        with wave.open(str(WHOOSH_PATH)) as handle:
            rate = handle.getframerate() or 1
            _WHOOSH_SECONDS = handle.getnframes() / float(rate)
    return _WHOOSH_SECONDS


def segment_blocked_starts(table: dict, fps: int = 30) -> set[int]:
    """这些成片帧不能当一段的第一帧，否则会从风刮或 xfade 中间切开。"""
    timeline = edl.frame_timeline(table, fps)
    blocked: set[int] = set()
    whoosh_n = max(1, snap_frames(whoosh_duration_s(), fps))
    for sl in timeline:
        fade_n = int(sl["fade_frames"])
        if fade_n:
            start = int(sl["program_start_frame"])
            # 含叠化第一帧。从那里起段，上一段在新图里只剩叠化那么长，时间表会拒绝。
            blocked.update(range(max(start, 1), start + fade_n))
    by_id = {sl["id"]: sl for sl in timeline}
    for item in edl.wind_transitions(table):
        host = by_id.get(str(item.get("before_id")))
        if host is None:
            continue
        wind_n = max(1, snap_frames(float(item["duration_s"]), fps))
        seam = int(host["program_start_frame"])
        # 风刮要留下 wind_n*2+2 帧才画。whoosh 从接缝前 wind_n 帧开始，跨到下一段。
        guard = max(wind_n * 2 + 2, whoosh_n)
        blocked.update(frame for frame in range(seam - guard + 1, seam + guard) if frame > 0)
    return blocked


def _choose_segment_end(start: int, total: int, blocked: set[int], max_frames: int, fps: int) -> int:
    if start >= total:
        return total
    target = min(total, start + max_frames)
    if target >= total:
        return total
    cut: int | None = None
    for frame in range(target, start, -1):
        if frame not in blocked:
            cut = frame
            break
    if cut is None:
        for frame in range(target + 1, total + 1):
            if frame == total or frame not in blocked:
                cut = frame
                break
    if cut is None or cut <= start:
        cut = total
    # 片尾不到 10 秒就并进上一段。单独再起一个编码器不值得，并到片尾也不会切断转场。
    if 0 < total - cut < int(round(SEGMENT_TAIL_MERGE_S * fps)):
        cut = total
    return cut


def plan_confirmed_segments(
    table: dict,
    fps: int = 30,
    max_s: float = SEGMENT_MAX_S,
) -> list[ExportSegment]:
    """把成片切成大约 max_s 秒的段。段界只落在硬切上，不落在风刮或 xfade 里面。"""
    timeline = edl.frame_timeline(table, fps)
    if not timeline:
        raise ValueError("program timeline has no segments")
    if max_s <= 0:
        raise ValueError("segment length must be positive")
    total = int(timeline[-1]["program_start_frame"] + timeline[-1]["frames"])
    max_frames = max(1, int(round(float(max_s) * fps)))
    blocked = segment_blocked_starts(table, fps)
    segments: list[ExportSegment] = []
    start = 0
    while start < total:
        end = _choose_segment_end(start, total, blocked, max_frames, fps)
        if end <= start:
            raise RuntimeError("confirmed segment did not advance")
        if start != 0 and start in blocked:
            raise RuntimeError(f"confirmed segment starts inside a transition at frame {start}")
        segments.append(ExportSegment(start, end))
        start = end
    if not segments or segments[-1].end_frame != total:
        raise RuntimeError("confirmed segments do not cover the program")
    return segments


def segment_program(table: dict, seg: ExportSegment, fps: int = 30) -> tuple[dict, dict[str, float]]:
    """切出这一段自己的时间表。成片时间从 0 起，转场只保留整段落在这段里的。"""
    timeline = edl.frame_timeline(table, fps)
    program: list[dict] = []
    skips: dict[str, float] = {}
    included: list[str] = []
    for sl in timeline:
        origin = int(sl["program_start_frame"])
        count = int(sl["frames"])
        lo = max(origin, seg.start_frame)
        hi = min(origin + count, seg.end_frame)
        if lo >= hi:
            continue
        src0 = int(sl["src_start_frame"])
        src_lo = src0 + (lo - origin)
        src_hi = src0 + (hi - origin)
        program.append(
            {
                "id": sl["id"],
                "type": sl["type"],
                "clip": sl["clip"],
                "src_start_s": src_lo / fps,
                "src_end_s": src_hi / fps,
                "program_start_s": 0.0,
                "hud": bool(sl["hud"]),
            }
        )
        included.append(str(sl["id"]))
        skips[str(sl["id"])] = (src_lo - src0) / fps
    present = set(included)
    by_id = {str(sl["id"]): sl for sl in timeline}
    transitions = []
    for item in table.get("transitions") or []:
        before = str(item.get("before_id"))
        if before not in present:
            continue
        seam = int(by_id[before]["program_start_frame"])
        if not (seg.start_frame <= seam < seg.end_frame):
            continue
        index = next(i for i, sl in enumerate(timeline) if str(sl["id"]) == before)
        if index == 0 or str(timeline[index - 1]["id"]) not in present:
            continue
        transitions.append(dict(item))
    seg_s = seg.start_frame / fps
    seg_e = seg.end_frame / fps
    overlays = []
    for ov in table.get("overlays") or []:
        lo = max(float(ov["program_start_s"]), seg_s)
        hi = min(float(ov["program_end_s"]), seg_e)
        if hi - lo <= 1e-4:
            continue
        shifted = dict(ov)
        shifted["program_start_s"] = lo - seg_s
        shifted["program_end_s"] = hi - seg_s
        overlays.append(shifted)
    sub = {"program": program, "transitions": transitions, "overlays": overlays}
    got = edl.frame_program_duration(sub, fps)
    want = (seg.end_frame - seg.start_frame) / fps
    if abs(got - want) > 1e-3:
        raise ValueError(
            f"segment {seg.start_frame}:{seg.end_frame} reflowed to {got:.6f}s, want {want:.6f}s"
        )
    return sub, skips


def cues_for_segment(
    cues: list[tuple[str, str, str]],
    start_s: float,
    end_s: float,
) -> list[tuple[str, str, str]]:
    """字幕按成片时间写。这一段的画面从 0 起，所以每条字幕减去段首，跨段的裁开。"""
    from subs_core import fmt_txt_time, parse_txt_time

    span = end_s - start_s
    shifted: list[tuple[str, str, str]] = []
    for start, end, text in cues:
        left = max(0.0, parse_txt_time(start) - start_s)
        right = min(span, parse_txt_time(end) - start_s)
        if right - left < 0.01:
            continue
        shifted.append((fmt_txt_time(left), fmt_txt_time(right), text))
    return shifted


def concat_copy_cmd(listing: Path, output: Path) -> list[str]:
    """段已经是同一套 videotoolbox / AAC 参数。接成片只做流拷贝，不再滤镜。"""
    return [
        "ffmpeg", "-y", "-hide_banner",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", "-movflags", "+faststart", str(output),
    ]


# 同时活着的 ffmpeg 合计常驻上限。超过就杀掉并报错，不等系统换页把整机拖死。
# 模拟里一段画面大约 0.8–1.5GB；8GB 已经说明有东西在垫帧。
SEGMENT_RSS_CAP_GB = 8.0
_RSS_POLL_S = 2.0
_FOOTPRINT_BIN = Path("/usr/bin/footprint")


def _rss_gb(pid: int) -> float:
    """ps 在 macOS 和 Linux 上都给 KB 的 RSS。拿不到就当 0，不让监控本身把导出弄挂。"""
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
        ).stdout
        return int((out or "").strip() or 0) / 1048576
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def parse_footprint_gb(text: str) -> float | None:
    """从 `footprint -p` 的输出里读 phys_footprint，单位换成 GB。读不到就返回 None。"""
    for line in text.splitlines():
        if not re.search(r"phys_footprint\b", line, re.I):
            continue
        if re.search(r"peak", line, re.I):
            continue
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(bytes|[KMGT]B|B)?", line, re.I)
        if match is None:
            continue
        value = float(match.group(1))
        unit = (match.group(2) or "").upper()
        scale = {"": 1.0, "B": 1.0, "BYTES": 1.0, "KB": 1024.0, "MB": 1024.0 ** 2, "GB": 1024.0 ** 3}
        if unit not in scale:
            continue
        # 没有单位、数字又很大时，footprint 打的是字节。
        if unit in ("", "B", "BYTES") and value >= 1024:
            return value / (1024.0 ** 3)
        if unit in ("", "B", "BYTES"):
            return value / (1024.0 ** 3)
        return value * scale[unit] / (1024.0 ** 3)
    return None


def _footprint_gb(pid: int) -> float | None:
    if not _FOOTPRINT_BIN.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(_FOOTPRINT_BIN), "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_footprint_gb(proc.stdout or "")


def _process_memory_gb(pid: int) -> tuple[float, str]:
    """macOS 上有 footprint 就读 phys_footprint，否则用 ps RSS。返回 (GB, 名字)。"""
    footprint = _footprint_gb(pid)
    if footprint is not None:
        return footprint, "footprint"
    return _rss_gb(pid), "rss"


def _watch_group(items: list[tuple[subprocess.Popen, str]], cap_gb: float = SEGMENT_RSS_CAP_GB) -> None:
    """盯着一组已经启动的 ffmpeg。每两秒加一次内存，合计超过上限就全杀掉，不重试。"""
    peaks = {id(proc): 0.0 for proc, _label in items}
    kinds = {id(proc): "rss" for proc, _label in items}
    started = {id(proc): time.monotonic() for proc, _label in items}
    finished: dict[int, float] = {}
    killed = False
    next_sample = time.monotonic()
    while True:
        alive = [(proc, label) for proc, label in items if proc.poll() is None]
        for proc, _label in items:
            if proc.poll() is not None and id(proc) not in finished:
                finished[id(proc)] = time.monotonic()
        if not alive:
            break
        now = time.monotonic()
        if now >= next_sample:
            total = 0.0
            for proc, _label in alive:
                gb, kind = _process_memory_gb(proc.pid)
                peaks[id(proc)] = max(peaks[id(proc)], gb)
                kinds[id(proc)] = kind
                total += gb
            if total > cap_gb and not killed:
                names = ", ".join(label for _proc, label in alive)
                print(
                    f"memory {total:.1f}GB > cap {cap_gb:.1f}GB ({names}), killing; not retrying",
                    flush=True,
                )
                for proc, _label in alive:
                    proc.kill()
                killed = True
            next_sample = now + _RSS_POLL_S
        try:
            alive[0][0].wait(timeout=max(0.05, min(_RSS_POLL_S, next_sample - time.monotonic())))
        except subprocess.TimeoutExpired:
            pass
    for proc, label in items:
        wall = finished.get(id(proc), time.monotonic()) - started[id(proc)]
        kind = kinds[id(proc)]
        print(
            f"{label}: rc={proc.returncode} peak_{kind}={peaks[id(proc)]:.2f}GB wall={wall:.1f}s",
            flush=True,
        )
    if killed:
        raise SystemExit(f"export exceeded the {cap_gb:.1f}GB memory cap; not retrying")


def _run_segment_encode(
    cmd: list[str],
    label: str = "segment",
    companions: list[tuple[subprocess.Popen, str]] | None = None,
) -> None:
    companions = list(companions or [])
    started = time.monotonic()
    proc = subprocess.Popen(cmd)
    _watch_group([(proc, label), *companions])
    rc = proc.returncode
    if rc == 0:
        return
    threads = cmd[cmd.index("-filter_complex_threads") + 1]
    # 负的返回码是信号（上一回是 SIGKILL）。内存超限已经在 _watch_group 里停掉，不会走到这里重试。
    still = [(peer, name) for peer, name in companions if peer.poll() is None]
    if rc > 0 and threads != "1" and time.monotonic() - started < FILTER_THREAD_RETRY_S:
        print(
            "segment filter graph did not stay up; retrying with -filter_complex_threads 1",
            flush=True,
        )
        retry = list(cmd)
        retry[retry.index("-filter_complex_threads") + 1] = "1"
        proc = subprocess.Popen(retry)
        _watch_group([(proc, label + " (threads 1)"), *still])
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, retry)
        return
    raise subprocess.CalledProcessError(rc if rc is not None else 1, cmd)


def probe_video_frames(path: Path) -> int:
    """数这一段实际写出的视频帧。和计划差一帧就停，不要把累计漂移接到成片里。"""
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(path),
        ],
        text=True,
    ).strip()
    if not raw:
        raise SystemExit(f"no video frames in {path}")
    return int(raw)


def _require_segment_frames(path: Path, expected: int) -> None:
    got = probe_video_frames(path)
    if got != expected:
        raise SystemExit(f"{path.name} has {got} frames, plan is {expected}")


def confirmed_segment_cmd(
    media_dir: Path,
    table: dict,
    seg: ExportSegment,
    alpha_paths: list[Path],
    modes: list[str],
    cues: list[tuple[str, str, str]],
    measured: dict[str, str] | None,
    work: Path,
    index: int,
    output: Path,
    test_codec: str | None = None,
    spec: ExportSpec = FINAL_SPEC,
) -> list[str]:
    """这一段的 ffmpeg 命令。只打开这段用到的原片和透明层。"""
    fps = spec.timeline.fps
    sub, skips = segment_program(table, seg, fps)
    full = edl.frame_timeline(table, fps)
    hud_ids = [str(sl["id"]) for sl in full if sl["hud"]]
    if len(hud_ids) != len(alpha_paths) or len(hud_ids) != len(modes):
        raise ValueError("HUD alpha count does not match hud slices")
    path_of = dict(zip(hud_ids, alpha_paths, strict=True))
    mode_of = dict(zip(hud_ids, modes, strict=True))
    sub_timeline = edl.frame_timeline(sub, fps)
    sub_paths = [path_of[str(sl["id"])] for sl in sub_timeline if sl["hud"]]
    sub_modes = [mode_of[str(sl["id"])] for sl in sub_timeline if sl["hud"]]
    list_dir = work / f"lists-{index:03d}"
    plan_args = program_input_args(media_dir, sub, sub_paths, spec, list_dir=list_dir)
    if any("hud-renders/keeps" in item.replace("\\", "/") for item in plan_args):
        raise SystemExit("final export cannot use keep intermediates as picture or HUD")
    ass_path = work / f"seg-{index:03d}.ass"
    ass_path.write_text(
        render_ass(cues_for_segment(cues, seg.start_frame / fps, seg.end_frame / fps)),
        encoding="utf-8",
    )
    wind_ids = {str(item["before_id"]) for item in edl.wind_transitions(sub)}
    openings = program_openings(sub_timeline, wind_ids)
    graph = build_program_filter(
        sub,
        sub_modes,
        len(sub.get("overlays") or []),
        ass_path,
        spec,
        measured=measured,
        alpha_skip=skips,
        video_only=True,
    )
    if "subtitles=" not in graph:
        raise SystemExit("confirmed export must burn subtitles in the picture encode")
    if "[a]" in graph or "loudnorm=" in graph:
        raise SystemExit("segment picture graph must not carry audio; audio is mixed once for the whole program")
    del openings
    return [
        "ffmpeg", "-y", "-hide_banner", "-nostdin",
        "-filter_complex_threads", str(CONFIRMED_FILTER_THREADS),
        *plan_args,
        "-filter_complex", graph, "-map", "[v]", "-an", "-frames:v", str(seg.frames),
        *video_codec_args(spec, test_codec=test_codec),
        "-pix_fmt", spec.timeline.pix_fmt,
        "-f", "mp4", str(output),
    ]


def program_audio_cmd(media_dir: Path, table: dict, measured: dict[str, str] | None, output: Path,
                      spec: ExportSpec = FINAL_SPEC) -> list[str]:
    """整片音频一次混好、一次 AAC。和测响度是同一张音频图，已测参数原样对得上。

    只解码原片的音轨，不碰画面。分段画面再多也只有这一条 AAC，没有段间 priming 接缝，
    dynaudnorm/loudnorm 也不会在段界重启。"""
    graph = build_program_audio_filter(table, spec, measured=measured, apply_loudness=True)
    return [
        "ffmpeg", "-y", "-hide_banner", "-nostdin",
        *program_audio_input_args(media_dir, table, spec),
        "-filter_complex", graph, "-map", "[a]", "-vn",
        *audio_codec_args(spec), "-f", "mp4", str(output),
    ]


def mux_final_cmd(listing: Path, audio: Path, output: Path) -> list[str]:
    """画面段流拷贝接起来，再配上整片那一条音频。不重编码。"""
    return [
        "ffmpeg", "-y", "-hide_banner", "-nostdin",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c", "copy", "-movflags", "+faststart", str(output),
    ]


def _reject_program_source(name: str) -> None:
    if any(part in name for part in PROGRAM_SOURCE_FORBIDDEN):
        raise SystemExit(f"program timeline cannot use encoded intermediate: {name}")


def _export_from_program(args, media_dir: Path) -> int:
    import final_qc
    import render_running_hud as hud

    episode_dir = Path(args.episode_dir).expanduser().resolve()
    subtitles = Path(args.subtitles).expanduser().resolve() if args.subtitles else episode_dir / "subtitles.txt"
    table = edl.load_media(media_dir)
    if not args.confirmed:
        raise SystemExit("Final export requires --confirmed after manual subtitle review")
    if args.no_subtitles:
        raise SystemExit("program export burns subtitles in the one confirmed encode; --no-subtitles is not available")
    if not subtitles.is_file():
        raise SystemExit(f"subtitles.txt not found: {subtitles}")
    cues = parse_txt(subtitles)
    status = read_status(episode_dir)
    if not status.get("preview", "").startswith("done"):
        raise SystemExit("Final export requires assets.md preview: done")
    if not status.get("subs", "").startswith("done"):
        raise SystemExit("Final export requires assets.md subs: done after user confirmation")
    if not status.get("qc", "").startswith("done"):
        raise SystemExit("Final export requires preview qc: done before final export")
    problems = edl.validate(table, require_frozen=True)
    if problems:
        raise SystemExit("program timeline: " + "; ".join(problems))
    try:
        todo_list.assert_export_allowed(media_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    for sl in edl.export_slices(table):
        _reject_program_source(sl["clip"])
        if not (media_dir / sl["clip"]).is_file() and not args.dry_run:
            raise SystemExit(f"program clip not found: {media_dir / sl['clip']}")
    output = Path(args.out).expanduser().resolve()
    if output.exists() and not args.dry_run:
        raise SystemExit(f"Refusing to overwrite existing final output: {output}")
    durations = {}
    fps = FINAL_SPEC.timeline.fps
    for sl in edl.export_slices(table, fps):
        path = media_dir / sl["clip"]
        if path.is_file() and sl["clip"] not in durations:
            durations[sl["clip"]] = probe_duration(path)
    jobs = edl.hud_jobs(table, fps)
    modes = [_program_alpha_mode(job, durations) for job in jobs]
    worker_count = hud.HUD_EXPORT_JOBS if args.jobs is None else args.jobs
    if worker_count < 1:
        raise SystemExit("--jobs must be >= 1")
    if hud.alphas_ready(media_dir, table, fps=fps):
        alpha_paths = hud.planned_alpha_paths(media_dir, table, fps=fps)
        print("HUD alpha reused", flush=True)
    else:
        alpha_paths = hud.export_alphas(
            media_dir, table, durations, dry_run=args.dry_run, fps=fps, jobs=worker_count,
        )
    if len(alpha_paths) != len(jobs):
        raise SystemExit("HUD alpha plan does not match kept run slices")
    for path in alpha_paths:
        if "keeps" in Path(path).parts:
            raise SystemExit(f"final export cannot use keep intermediates as HUD: {path}")
    if not args.dry_run:
        todo_list.mark(media_dir, "hud-render", "done")
    # 段文件、透明层清单和按段平移过的 ASS 都在这一个临时目录里。成功和失败都删。
    work = tempfile.TemporaryDirectory(prefix="running-confirmed-")
    try:
        try:
            measured = _loudness_for_export(media_dir, table, dry_run=args.dry_run)
            if measured is not None and not args.dry_run:
                todo_list.mark(media_dir, "loudness-measure", "done")
            elif not args.dry_run:
                print("Loudnorm pass 1 skipped; encode will use single-pass loudnorm", flush=True)
            segments = plan_confirmed_segments(table, fps)
            work_dir = Path(work.name)
            print(
                f"confirmed segments={len(segments)} max={SEGMENT_MAX_S:.0f}s "
                f"filter_threads={CONFIRMED_FILTER_THREADS}",
                flush=True,
            )
            segment_paths: list[Path] = []
            audio_path = work_dir / "program-audio.m4a"
            audio_cmd = program_audio_cmd(media_dir, table, measured, audio_path)
            # 整片音频和第一段画面一起跑。音频大约 0.2GB，第一段画面大约 1–2GB，合计仍在 8GB 内。
            print("$", " ".join(audio_cmd), flush=True)
            audio_proc: subprocess.Popen | None = None
            if not args.dry_run:
                audio_proc = subprocess.Popen(audio_cmd)
            try:
                for index, seg in enumerate(segments):
                    seg_path = work_dir / f"seg-{index:03d}.mp4"
                    cmd = confirmed_segment_cmd(
                        media_dir, table, seg, alpha_paths, modes, cues, measured,
                        work_dir, index, seg_path, test_codec=args.test_codec,
                    )
                    inputs = [cmd[pos + 1] for pos, flag in enumerate(cmd) if flag == "-i"]
                    print(
                        f"segment {index + 1}/{len(segments)} "
                        f"{seg.start_frame / fps:.3f}-{seg.end_frame / fps:.3f}s "
                        f"inputs={len(inputs)} frames={seg.frames}",
                        flush=True,
                    )
                    print("$", " ".join(cmd), flush=True)
                    if not args.dry_run:
                        companions = []
                        if index == 0 and audio_proc is not None and audio_proc.poll() is None:
                            companions = [(audio_proc, "program audio")]
                        _run_segment_encode(
                            cmd, f"segment {index + 1}/{len(segments)}", companions=companions,
                        )
                        if index == 0 and audio_proc is not None and audio_proc.poll() is None:
                            _watch_group([(audio_proc, "program audio")])
                        if audio_proc is not None and audio_proc.returncode not in (0, None):
                            raise subprocess.CalledProcessError(audio_proc.returncode, audio_cmd)
                        _require_segment_frames(seg_path, seg.frames)
                    segment_paths.append(seg_path)
            finally:
                if audio_proc is not None and audio_proc.poll() is None:
                    audio_proc.kill()
                    audio_proc.wait()
            listing = work_dir / "segments.ffconcat"
            _write_alpha_concat(tuple(segment_paths), listing)
            join = mux_final_cmd(listing, audio_path, output)
            print("$", " ".join(join), flush=True)
            if args.dry_run:
                return 0
            subprocess.run(join, check=True)
            print(f"Wrote {output}", flush=True)
            info = final_qc.probe_final(output)
            loudness = final_qc.measure_integrated_lufs(output)
            codec = args.test_codec or FINAL_SPEC.vcodec
            tag = None if args.test_codec else FINAL_SPEC.tag
            qc_problems = final_qc.check_final(
                info,
                expected_duration=edl.frame_program_duration(table, FINAL_SPEC.timeline.fps),
                loudness_i=loudness,
                video_codec="h264" if codec == "libx264" else "hevc",
                video_tag=tag,
            )
            if qc_problems:
                raise SystemExit("final QC failed: " + "; ".join(qc_problems))
            # final-qc 要等抽帧看过字幕、HUD、贴图。结构检查通过只代表这一次编码可以留下。
            todo_list.mark(media_dir, "final-export", "done")
        except BaseException:
            if not args.dry_run:
                output.unlink(missing_ok=True)
            raise
    finally:
        work.cleanup()
    return 0


def _export_episode(args) -> int:
    media_dir = Path(args.media_dir).expanduser().resolve()
    if edl.program_path(media_dir).is_file():
        return _export_from_program(args, media_dir)
    episode_dir = Path(args.episode_dir).expanduser().resolve()
    subtitles = Path(args.subtitles).expanduser().resolve() if args.subtitles else episode_dir / "subtitles.txt"
    sources = discover_sources(media_dir)
    validate_gate(episode_dir, subtitles, args.confirmed, sources)
    output = Path(args.out).expanduser().resolve()
    if output.exists() and not args.dry_run:
        raise SystemExit(f"Refusing to overwrite existing final output: {output}")
    durations = [probe_duration(path) for path in sources.clips]
    overlays = [] if args.no_overlays else load_timeline_overlays(
        media_dir,
        durations,
        has_open=sources.open_clip is not None,
        has_close=sources.close_clip is not None,
        explicit=args.overlays,
    )
    plan = build_input_plan(sources, durations, FINAL_SPEC, overlays)
    ass = None if args.no_subtitles else make_ass(subtitles)
    try:
        first_graph = build_filter_graph(sources, durations, plan, ass, measured=None, overlays=overlays)
        measured = None if args.dry_run else measure_loudness(plan, first_graph)
        if measured is not None:
            print(f"Loudnorm pass 1: I={measured['input_i']} TP={measured['input_tp']}", flush=True)
        elif not args.dry_run:
            print("Loudnorm pass 1 skipped; encode will use single-pass loudnorm", flush=True)
        final_graph = build_filter_graph(sources, durations, plan, ass, measured=measured, overlays=overlays)
        cmd = build_encode_cmd(plan, final_graph, output, test_codec=args.test_codec)
        print("$", " ".join(cmd), flush=True)
        if not args.dry_run:
            subprocess.run(cmd, check=True)
            print(f"Wrote {output}", flush=True)
    finally:
        if ass is not None:
            ass.unlink(missing_ok=True)
    return 0


def probe_duration(path: Path) -> float:
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True).strip()
    return float(raw)


if __name__ == "__main__":
    raise SystemExit(main())
