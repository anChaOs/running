#!/usr/bin/env python3
"""把已经渲好的 HUD / 数据图片段接成整条审片预览。

优先 stream copy。只有编码、分辨率、像素格式、帧率或音频对不上时，才按
preview profile 轻转那一段，然后再 `-c copy` 接起来。30/1 和 30000/1001
都算 30fps，目标像素格式跟 HUD preview（常见 yuvj420p）走，不把长预览收成
整数 30 或 yuv420p。open 尾和 close 头按最终成片的 0.2s xfade 剪掉同样的
时长，中间段不剪、也不做叠化。缺 HUD preview 就失败，不会退回原片 + alpha
重压。不烧字幕、不修响度。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "assemble"))
sys.path.insert(0, str(TOOLS_DIR / "subs"))

from export_spec import PREVIEW_SPEC, ExportSpec, video_codec_args
# 和最终导出用同一套 stats 图片判定，这样「有数据图却没有 close-stats」的失败条件和最终会叠的静帧一致。
# XFADE 只用来对齐时间轴，不在这里重压叠化。
from final_export import RAW_CLIP_PARTS, XFADE, _one, _stats_files
from txt_to_subs import parse_txt, write_srt

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Mux slack after the xfade trim is already subtracted. Kept under one 0.2s overlap.
DURATION_SLACK_S = 0.15
# 30/1 and 30000/1001 are both copy-eligible. They are not the same rate.
NTSC_30 = 30000 / 1001
RATE_EPS = 0.001
PREVIEW_PIX_FMTS = {"yuv420p", "yuvj420p"}
H264_PROFILES = {"high", "main", "baseline"}


@dataclass(frozen=True)
class StreamInfo:
    vcodec: str
    width: int
    height: int
    pix_fmt: str
    fps: float
    profile: str | None
    sar: str
    acodec: str | None
    sample_rate: int | None
    channels: int | None
    n_streams: int
    n_video: int
    n_audio: int
    fps_rate: str = "30/1"


@dataclass(frozen=True)
class PreviewCut:
    open_clip: Path | None
    runs: tuple[Path, ...]
    close_clip: Path | None
    date: str

    @property
    def segments(self) -> tuple[Path, ...]:
        return tuple(p for p in (self.open_clip, *self.runs, self.close_clip) if p is not None)


@dataclass(frozen=True)
class SegmentAction:
    source: Path
    mode: str  # copy | remux | transcode
    video: str  # copy | encode
    audio: str  # copy | encode
    reason: str
    trim_start: float = 0.0
    trim_end: float = 0.0


@dataclass(frozen=True)
class PreviewPlan:
    actions: tuple[SegmentAction, ...]
    target: StreamInfo
    durations: tuple[float, ...]

    @property
    def expected_duration(self) -> float:
        total = 0.0
        for duration, action in zip(self.durations, self.actions, strict=True):
            total += duration - action.trim_start - action.trim_end
        return total


def _is_30(fps: float) -> bool:
    """True for integer 30/1 and phone 30000/1001. 60fps is not."""
    return abs(fps - 30.0) <= RATE_EPS or abs(fps - NTSC_30) <= RATE_EPS


def _rates_match(left: float, right: float) -> bool:
    return abs(left - right) <= RATE_EPS


def _rate_key(fps: float) -> str:
    if abs(fps - NTSC_30) <= RATE_EPS:
        return "30000/1001"
    if abs(fps - 30.0) <= RATE_EPS:
        return "30/1"
    return f"{fps:.3f}"


def _parse_rate(value: object) -> float:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return 0.0
    if "/" in text:
        num, den = text.split("/", 1)
        denom = float(den)
        return float(num) / denom if denom else 0.0
    return float(text)


def _fps_fields(stream: dict) -> tuple[float, str]:
    fps = _frame_rate(stream)
    for key in ("avg_frame_rate", "r_frame_rate"):
        token = str(stream.get(key) or "")
        if "/" not in token:
            continue
        parsed = _parse_rate(token)
        if parsed <= 0 or abs(parsed - fps) > RATE_EPS:
            continue
        num, den = token.split("/", 1)
        try:
            return fps, f"{int(float(num))}/{int(float(den))}"
        except ValueError:
            continue
    return fps, _rate_key(fps)


def _frame_rate(stream: dict) -> float:
    avg = _parse_rate(stream.get("avg_frame_rate"))
    raw = _parse_rate(stream.get("r_frame_rate"))
    if avg > 0 and raw > 0 and abs(avg - raw) > 0.5:
        # Variable or mismatched rates are not a stable 30fps stream.
        if _is_30(avg) and not _is_30(raw):
            return raw
        if _is_30(raw) and not _is_30(avg):
            return avg
        return raw
    return avg or raw


def _sar(value: object) -> str:
    text = str(value or "").strip()
    if not text or text in {"N/A", "0:1"}:
        return "1:1"
    return text


def _optional_int(value: object) -> int | None:
    if value is None or value == "N/A" or value == "":
        return None
    return int(value)


def _video_matches(left: StreamInfo, right: StreamInfo) -> bool:
    if left.vcodec != right.vcodec or left.pix_fmt != right.pix_fmt or left.sar != right.sar:
        return False
    if (left.width, left.height) != (right.width, right.height):
        return False
    if not _is_30(left.fps) or not _is_30(right.fps) or not _rates_match(left.fps, right.fps):
        return False
    if left.profile and right.profile and left.profile != right.profile:
        return False
    return True


def _audio_matches(left: StreamInfo, right: StreamInfo) -> bool:
    return (
        left.acodec is not None
        and left.acodec == right.acodec
        and left.sample_rate == right.sample_rate
        and left.channels == right.channels
    )


def _clean(info: StreamInfo) -> bool:
    return info.n_video == 1 and info.n_audio == 1 and info.n_streams == 2


def _signature_key(info: StreamInfo) -> tuple:
    return (
        info.vcodec,
        info.width,
        info.height,
        info.pix_fmt,
        info.sar,
        info.profile or "",
        info.acodec,
        info.sample_rate,
        info.channels,
        _rate_key(info.fps),
    )


def classify_segment(info: StreamInfo, target: StreamInfo) -> tuple[str, str, str, str]:
    """Return mode, video action, audio action, and a short reason."""
    video_ok = _video_matches(info, target)
    audio_ok = _audio_matches(info, target)
    if video_ok and audio_ok and _clean(info):
        return "copy", "copy", "copy", ""
    if video_ok and audio_ok:
        return "remux", "copy", "copy", f"extra streams ({info.n_streams})"
    reasons: list[str] = []
    if not video_ok:
        if info.vcodec != target.vcodec:
            reasons.append(f"video {info.vcodec}!={target.vcodec}")
        if (info.width, info.height) != (target.width, target.height):
            reasons.append(f"size {info.width}x{info.height}!={target.width}x{target.height}")
        if info.pix_fmt != target.pix_fmt:
            reasons.append(f"pix_fmt {info.pix_fmt}!={target.pix_fmt}")
        if info.sar != target.sar:
            reasons.append(f"sar {info.sar}!={target.sar}")
        if not _rates_match(info.fps, target.fps) or not _is_30(info.fps) or not _is_30(target.fps):
            reasons.append(f"fps {info.fps:.3f}!={target.fps:.3f}")
        if info.profile and target.profile and info.profile != target.profile:
            reasons.append(f"profile {info.profile}!={target.profile}")
    if not audio_ok:
        reasons.append(
            f"audio {info.acodec}/{info.sample_rate}/{info.channels}"
            f"!={target.acodec}/{target.sample_rate}/{target.channels}"
        )
    return "transcode", "copy" if video_ok else "encode", "copy" if audio_ok else "encode", ", ".join(reasons)


def choose_target(infos: list[StreamInfo], durations: list[float]) -> StreamInfo:
    """Pick the 30fps signature the long HUD previews can keep.

    h264 wins when any 30fps h264 group exists, even if a longer HEVC open is
    present, so those previews stay stream-copy. yuvj420p is eligible and stays
    distinct from yuv420p: the winning group's own pix_fmt and frame rate
    (including 30000/1001) become the target. Outliers are transcoded to it.
    """
    groups: dict[tuple, list[tuple[StreamInfo, float]]] = {}
    for info, duration in zip(infos, durations, strict=True):
        if not (_is_30(info.fps) and info.pix_fmt in PREVIEW_PIX_FMTS and info.acodec):
            continue
        groups.setdefault(_signature_key(info), []).append((info, duration))
    if not groups:
        longest = max(zip(infos, durations, strict=True), key=lambda item: item[1])[0]
        return StreamInfo(
            vcodec="h264",
            width=longest.width,
            height=longest.height,
            pix_fmt="yuv420p",
            fps=30.0,
            fps_rate="30/1",
            profile="high",
            sar="1:1",
            acodec="aac",
            sample_rate=longest.sample_rate or PREVIEW_SPEC.timeline.sample_rate,
            channels=longest.channels or 2,
            n_streams=2,
            n_video=1,
            n_audio=1,
        )
    h264_groups = {key: members for key, members in groups.items() if key[0] == "h264"}
    pool = h264_groups or groups

    def score(key: tuple) -> tuple:
        members = pool[key]
        pixels = int(key[1]) * int(key[2])
        return (sum(item[1] for item in members), pixels, len(members))

    best = max(pool, key=score)
    return pool[best][0][0]


def _boundary_trims(
    index: int,
    count: int,
    duration: float,
    *,
    has_open: bool,
    has_close: bool,
) -> tuple[float, float]:
    """Match final_export's xfade shortening without restacking the blend.

    The final graph overlaps open into the first run, and the last run into
    close, by XFADE. Joins between runs do not change duration. Trim those
    same seconds off the short boundary clips while they are already being
    lightly transcoded. Leave the long HUD previews untouched.
    """
    if count < 2 or duration <= XFADE + 0.05:
        return 0.0, 0.0
    trim_end = XFADE if index == 0 and has_open else 0.0
    trim_start = XFADE if index == count - 1 and has_close else 0.0
    return trim_start, trim_end


def plan_preview(
    segments: list[Path] | tuple[Path, ...],
    infos: list[StreamInfo],
    durations: list[float],
    spec: ExportSpec = PREVIEW_SPEC,
    *,
    has_open: bool = False,
    has_close: bool = False,
) -> PreviewPlan:
    if spec.assembly != "concat-copy":
        raise SystemExit("Preview spec must use concat-copy assembly. Review preview does not restack.")
    if not segments:
        raise SystemExit("Review preview has no segments to concat.")
    if not (len(segments) == len(infos) == len(durations)):
        raise SystemExit("Preview plan inputs do not line up.")
    if any(duration <= 0 for duration in durations):
        raise SystemExit("A preview segment has no duration.")
    target = choose_target(list(infos), list(durations))
    actions: list[SegmentAction] = []
    count = len(segments)
    for index, (source, info, duration) in enumerate(zip(segments, infos, durations, strict=True)):
        mode, video, audio, reason = classify_segment(info, target)
        trim_start, trim_end = _boundary_trims(
            index, count, duration, has_open=has_open, has_close=has_close,
        )
        if trim_start or trim_end:
            mode = "transcode"
            video = "encode"
            audio = "encode"
            notes: list[str] = []
            if trim_end:
                notes.append(f"xfade trim tail {trim_end:.3f}s")
            if trim_start:
                notes.append(f"xfade trim head {trim_start:.3f}s")
            reason = ", ".join(part for part in (reason, *notes) if part)
        actions.append(
            SegmentAction(source, mode, video, audio, reason, trim_start, trim_end)
        )
    return PreviewPlan(tuple(actions), target, tuple(durations))


def probe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(raw)


def probe_streams(path: Path) -> StreamInfo:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        text=True,
    )
    streams = json.loads(raw).get("streams") or []
    videos = [
        stream for stream in streams
        if stream.get("codec_type") == "video" and not (stream.get("disposition") or {}).get("attached_pic")
    ]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise SystemExit(
            f"{path.name} has {len(videos)} video streams. "
            "Review preview does not restack a replacement."
        )
    if not audios:
        raise SystemExit(
            f"{path.name} has no audio stream. "
            "Review preview keeps each segment's audio and does not restack from originals."
        )
    video = videos[0]
    audio = audios[0]
    profile = video.get("profile")
    fps, fps_rate = _fps_fields(video)
    return StreamInfo(
        vcodec=str(video.get("codec_name") or ""),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        pix_fmt=str(video.get("pix_fmt") or ""),
        fps=fps,
        fps_rate=fps_rate,
        profile=str(profile).lower() if profile and profile != "N/A" else None,
        sar=_sar(video.get("sample_aspect_ratio")),
        acodec=str(audio.get("codec_name") or "") or None,
        sample_rate=_optional_int(audio.get("sample_rate")),
        channels=_optional_int(audio.get("channels")),
        n_streams=len(streams),
        n_video=len(videos),
        n_audio=len(audios),
    )


def _clip_date(path: Path) -> str:
    match = DATE_RE.match(path.name)
    if not match:
        raise SystemExit(f"Cannot read a YYYY-MM-DD date from {path.name}")
    return match.group(1)


def _original_runs(media_dir: Path) -> tuple[Path, ...]:
    return tuple(
        path for path in sorted(media_dir.glob("*-run-*.mp4"))
        if path.is_file() and not any(part in path.stem for part in RAW_CLIP_PARTS)
    )


def _preview_for(run: Path) -> Path:
    return run.parent / "hud-renders" / f"{run.stem}-hud-preview.mp4"


def _find_close(media_dir: Path, stats: tuple[Path, ...]) -> Path | None:
    close_stats = _one(
        [path for path in sorted(media_dir.glob("*-close-stats.mp4")) if path.is_file()],
        "close-stats",
    )
    close_raw = _one(
        [
            path for path in sorted(media_dir.glob("*-close.mp4"))
            if path.is_file() and "stats" not in path.name and "hud" not in path.name
        ],
        "close",
    )
    if close_stats is not None:
        return close_stats
    if not stats:
        return close_raw
    names = ", ".join(path.name for path in stats)
    if close_raw is None:
        raise SystemExit(
            f"Stats images are present ({names}) but there is no close or close-stats segment. "
            "Review preview does not restack stats onto another clip."
        )
    raise SystemExit(
        f"Stats images are present ({names}) but no rendered close-stats segment. "
        "Render the 数据图 segment with tools/assemble/overlay_close_stats.py first. "
        "Review preview does not restack close and stats."
    )


def discover_preview_cut(media_dir: Path) -> PreviewCut:
    """Resolve the review cut from rendered segment previews, never from HUD alpha."""
    runs = _original_runs(media_dir)
    if not runs:
        raise SystemExit(
            f"No original run clips in {media_dir}. "
            "Review preview concatenates HUD previews and does not restack originals."
        )
    missing = [run for run in runs if not _preview_for(run).is_file()]
    if missing:
        names = ", ".join(_preview_for(run).name for run in missing)
        raise SystemExit(
            f"Missing HUD preview(s): {names}. "
            "Render those segments with tools/hud/render_running_hud.py --overlay-only --preview first. "
            "Review preview does not restack originals and HUD alpha."
        )
    previews = tuple(_preview_for(run) for run in runs)
    open_clip = _one(
        [path for path in sorted(media_dir.glob("*-open.mp4")) if path.is_file()],
        "open",
    )
    close_clip = _find_close(media_dir, _stats_files(media_dir))
    return PreviewCut(open_clip, previews, close_clip, _clip_date(runs[0]))


def reject_preview_output(output: Path) -> None:
    if output.name.endswith("-run-final.mp4") or "upload" in output.parts:
        raise SystemExit("Review preview cannot be written as run-final or inside upload/")


def duration_slack(segments: int) -> float:
    return min(DURATION_SLACK_S, 0.06 + 0.01 * segments)


def assert_preview_ready(output: Path, expected_duration: float, segments: int) -> None:
    actual = probe_duration(output)
    slack = duration_slack(segments)
    if abs(actual - expected_duration) > slack:
        raise SystemExit(
            f"Review preview duration {actual:.3f}s != expected cut {expected_duration:.3f}s "
            f"(drift {actual - expected_duration:+.3f}s, slack {slack:.3f}s). "
            "Refusing a drifted preview."
        )
    info = probe_streams(output)
    if not _is_30(info.fps):
        raise SystemExit(
            f"Review preview is {info.fps:.3f} fps; expected 30fps so subtitle timing stays aligned."
        )


def format_plan(plan: PreviewPlan) -> str:
    target = plan.target
    lines = [
        "preview assembly=concat-copy "
        f"segments={len(plan.actions)} "
        f"target={target.vcodec} {target.width}x{target.height} "
        f"{target.fps:.3f}fps {target.pix_fmt} profile={target.profile or '-'} {target.acodec} "
        f"duration={plan.expected_duration:.3f}",
    ]
    for action in plan.actions:
        if action.mode == "copy":
            lines.append(f"copy {action.source}")
        else:
            lines.append(
                f"{action.mode} {action.source} video={action.video} audio={action.audio} ({action.reason})"
            )
    lines.append("concat=-c copy")
    return "\n".join(lines)


def normalized_path(work_dir: Path, index: int, source: Path) -> Path:
    return work_dir / f"{index:02d}-{source.stem}-norm.mp4"


def concat_inputs(plan: PreviewPlan, work_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for index, action in enumerate(plan.actions):
        if action.mode == "copy":
            paths.append(action.source)
        else:
            paths.append(normalized_path(work_dir, index, action.source))
    return paths


def concat_list_text(paths: list[Path]) -> str:
    lines = []
    for path in paths:
        escaped = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'\n")
    return "".join(lines)


def _rate_token(target: StreamInfo) -> str:
    return target.fps_rate or _rate_key(target.fps)


def _video_filters(info: StreamInfo, target: StreamInfo, action: SegmentAction, duration: float) -> list[str]:
    filters: list[str] = []
    if action.trim_start or action.trim_end:
        end = duration - action.trim_end
        filters.append(
            f"trim=start={action.trim_start:.6f}:end={end:.6f},setpts=PTS-STARTPTS"
        )
    if (info.width, info.height) != (target.width, target.height):
        width, height = target.width, target.height
        filters.append(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    elif info.sar != "1:1":
        filters.append("setsar=1")
    if not _rates_match(info.fps, target.fps):
        filters.append(f"fps={_rate_token(target)}")
    return filters


def _audio_encode_args(target: StreamInfo, spec: ExportSpec) -> list[str]:
    if target.acodec not in (None, "aac"):
        raise SystemExit(
            f"A segment must be transcoded to {target.acodec} audio. "
            "This light transcode only emits AAC from the preview profile. "
            "Match the segment codecs so they can be stream-copied. "
            "Review preview does not restack originals and HUD alpha."
        )
    rate = target.sample_rate or spec.timeline.sample_rate
    channels = target.channels or 2
    return ["-c:a", "aac", "-b:a", spec.abitrate, "-ar", str(rate), "-ac", str(channels)]


def _video_encode_args(target: StreamInfo, spec: ExportSpec) -> list[str]:
    if target.vcodec != "h264":
        raise SystemExit(
            "A segment must be transcoded to match the others, but those segments are "
            f"{target.vcodec}, not the h264 preview profile. "
            "Stream-copy needs matching codecs. "
            "Review preview does not restack originals and HUD alpha."
        )
    args = video_codec_args(spec)
    if target.profile in H264_PROFILES:
        args.extend(["-profile:v", target.profile])
    return args


def build_normalize_cmd(
    info: StreamInfo,
    action: SegmentAction,
    dest: Path,
    target: StreamInfo,
    duration: float,
    spec: ExportSpec = PREVIEW_SPEC,
) -> list[str]:
    cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-i", str(action.source)]
    if action.mode == "remux":
        return [
            *cmd,
            "-map", "0:v:0", "-map", "0:a:0",
            "-c", "copy",
            "-movflags", "+faststart",
            str(dest),
        ]
    filters = _video_filters(info, target, action, duration) if action.video == "encode" else []
    if filters:
        cmd.extend(["-vf", ",".join(filters)])
    cmd.extend(["-map", "0:v:0", "-map", "0:a:0"])
    if action.video == "encode":
        cmd.extend(_video_encode_args(target, spec))
        cmd.extend(["-pix_fmt", target.pix_fmt or "yuv420p", "-r", _rate_token(target)])
    else:
        cmd.extend(["-c:v", "copy"])
    if action.audio == "encode":
        if action.trim_start or action.trim_end:
            end = duration - action.trim_end
            cmd.extend([
                "-af",
                f"atrim=start={action.trim_start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS",
            ])
        cmd.extend(_audio_encode_args(target, spec))
    else:
        cmd.extend(["-c:a", "copy"])
    if action.trim_start or action.trim_end:
        kept = duration - action.trim_start - action.trim_end
        cmd.extend(["-t", f"{kept:.6f}"])
    cmd.extend(["-movflags", "+faststart", str(dest)])
    return cmd


def build_concat_cmd(list_path: Path, output: Path) -> list[str]:
    return [
        "ffmpeg", "-y", "-nostdin", "-hide_banner",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output),
    ]


def commands_for_plan(
    plan: PreviewPlan,
    infos: list[StreamInfo],
    output: Path,
    work_dir: Path,
    spec: ExportSpec = PREVIEW_SPEC,
) -> list[list[str]]:
    if len(infos) != len(plan.actions):
        raise SystemExit("Preview commands do not line up with probed segments.")
    list_path = work_dir / "concat.txt"
    commands: list[list[str]] = []
    for index, (info, action) in enumerate(zip(infos, plan.actions, strict=True)):
        if action.mode == "copy":
            continue
        commands.append(
            build_normalize_cmd(
                info,
                action,
                normalized_path(work_dir, index, action.source),
                plan.target,
                plan.durations[index],
                spec,
            )
        )
    commands.append(build_concat_cmd(list_path, output))
    return commands


def execute_plan(
    plan: PreviewPlan,
    infos: list[StreamInfo],
    output: Path,
    *,
    dry_run: bool,
    spec: ExportSpec = PREVIEW_SPEC,
) -> None:
    work_dir = output.parent / f".{output.stem}.preview-work"
    commands = commands_for_plan(plan, infos, output, work_dir, spec)
    print(format_plan(plan))
    for cmd in commands:
        print("$", " ".join(shlex.quote(part) for part in cmd))
    if dry_run:
        return
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    try:
        (work_dir / "concat.txt").write_text(
            concat_list_text(concat_inputs(plan, work_dir)),
            encoding="utf-8",
        )
        try:
            for cmd in commands:
                subprocess.run(cmd, check=True)
            assert_preview_ready(output, plan.expected_duration, len(plan.actions))
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def write_subtitle_sidecar(subtitles: Path, output: Path) -> Path:
    """Write an unchanged-time SRT next to the preview. Do not burn it in."""
    dest = output.with_suffix(".srt")
    write_srt(dest, parse_txt(subtitles))
    print(f"sidecar={dest}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--out")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--subtitles",
        help="Optional subtitles.txt. Writes a same-named .srt beside the preview with unchanged cue times. Does not burn in.",
    )
    args = parser.parse_args(argv)

    media_dir = Path(args.media_dir).expanduser().resolve()
    if not media_dir.is_dir():
        raise SystemExit(f"media dir not found: {media_dir}")
    cut = discover_preview_cut(media_dir)
    output = Path(args.out).expanduser().resolve() if args.out else media_dir / f"{cut.date}-review-preview.mp4"
    reject_preview_output(output)
    segments = list(cut.segments)
    infos = [probe_streams(path) for path in segments]
    durations = [probe_duration(path) for path in segments]
    plan = plan_preview(
        segments,
        infos,
        durations,
        PREVIEW_SPEC,
        has_open=cut.open_clip is not None,
        has_close=cut.close_clip is not None,
    )
    subtitles = Path(args.subtitles).expanduser().resolve() if args.subtitles else None
    if subtitles is not None and not subtitles.is_file():
        raise SystemExit(f"subtitles not found: {subtitles}")
    execute_plan(plan, infos, output, dry_run=args.dry_run)
    if subtitles is not None:
        if args.dry_run:
            print(f"sidecar={output.with_suffix('.srt')}")
        else:
            write_subtitle_sidecar(subtitles, output)
            print(f"Wrote {output}")
    elif not args.dry_run:
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
