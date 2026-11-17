#!/usr/bin/env python3
"""最终成片的结构核对。只看探针结果，不重新编码。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def check_final(
    info: dict,
    *,
    expected_duration: float,
    loudness_i: float | None,
    video_codec: str = "hevc",
    video_tag: str | None = "hvc1",
    width: int = 1920,
    height: int = 1080,
    fps: float = 30.0,
    loudness_target: float = -16.0,
) -> list[str]:
    """返回问题列表。空列表表示可以放行。"""
    problems: list[str] = []
    if info.get("n_video") != 1 or info.get("n_audio") != 1:
        problems.append(
            f"expected one video and one audio stream, got video={info.get('n_video')} audio={info.get('n_audio')}"
        )
    video = info.get("video") or {}
    audio = info.get("audio") or {}
    if video.get("codec") != video_codec:
        problems.append(f"video codec {video.get('codec')} != {video_codec}")
    if video_tag and video.get("tag") != video_tag:
        problems.append(f"video tag {video.get('tag')} != {video_tag}")
    if (video.get("width"), video.get("height")) != (width, height):
        problems.append(f"frame size {video.get('width')}x{video.get('height')} != {width}x{height}")
    got_fps = float(video.get("fps") or 0)
    if abs(got_fps - fps) > 0.05:
        problems.append(f"fps {got_fps:.3f} != {fps:.3f}")
    if audio.get("codec") != "aac":
        problems.append(f"audio codec {audio.get('codec')} != aac")
    duration = info.get("duration")
    if duration is None or abs(float(duration) - expected_duration) > 0.2:
        problems.append(f"duration {duration} != expected {expected_duration:.3f}")
    if loudness_i is None:
        problems.append("loudness was not measured")
    elif abs(float(loudness_i) - loudness_target) > 1.5:
        problems.append(f"integrated loudness {loudness_i} is outside {loudness_target} +/- 1.5 LU")
    return problems


def probe_final(path: Path) -> dict:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True,
    )
    payload = json.loads(raw)
    videos = [stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"]
    audios = [stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio"]
    video = videos[0] if videos else {}
    audio = audios[0] if audios else {}
    rate = str(video.get("avg_frame_rate") or "0/1")
    if "/" in rate:
        num, den = rate.split("/", 1)
        fps = float(num) / float(den) if float(den) else 0.0
    else:
        fps = float(rate or 0)
    tag = str(video.get("codec_tag_string") or "")
    return {
        "n_video": len(videos),
        "n_audio": len(audios),
        "duration": float((payload.get("format") or {}).get("duration") or 0),
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": fps,
            "tag": tag,
        },
        "audio": {"codec": audio.get("codec_name")},
    }


def measure_integrated_lufs(path: Path) -> float | None:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", "loudnorm=print_format=json", "-f", "null", "-",
        ],
        capture_output=True, text=True, check=False,
    )
    end = proc.stderr.rfind("}")
    start = proc.stderr.rfind("{", 0, end)
    if start < 0 or end < 0:
        return None
    try:
        payload = json.loads(proc.stderr[start:end + 1])
    except json.JSONDecodeError:
        return None
    try:
        return float(payload["input_i"])
    except (KeyError, TypeError, ValueError):
        return None
