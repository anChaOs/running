"""统一预览与最终导出的规格配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


SPEC_PATH = Path(__file__).with_name("export-spec.json")


@dataclass(frozen=True)
class TimelineSpec:
    width: int
    height: int
    fps: int
    pix_fmt: str
    sample_rate: int


@dataclass(frozen=True)
class LoudnessSpec:
    integrated_lufs: float
    true_peak_db: float
    lra: float


@dataclass(frozen=True)
class SubtitleSpec:
    font_size: int
    margin_v: int


@dataclass(frozen=True)
class ExportSpec:
    timeline: TimelineSpec
    vcodec: str
    bitrate: str | None
    crf: int | None
    preset: str | None
    tag: str | None
    acodec: str
    abitrate: str
    subtitle: SubtitleSpec
    loudness: LoudnessSpec


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Export spec {label} must be an object")
    return cast(dict[str, Any], value)


def load_export_specs(path: Path = SPEC_PATH) -> dict[str, ExportSpec]:
    root = _object(json.loads(path.read_text(encoding="utf-8")), "root")
    timeline_raw = _object(root["timeline"], "timeline")
    loudness_raw = _object(root["loudness"], "loudness")
    subtitle_raw = _object(root["subtitle"], "subtitle")
    timeline = TimelineSpec(
        width=int(timeline_raw["width"]),
        height=int(timeline_raw["height"]),
        fps=int(timeline_raw["fps"]),
        pix_fmt=str(timeline_raw["pix_fmt"]),
        sample_rate=int(timeline_raw["sample_rate"]),
    )
    loudness = LoudnessSpec(
        integrated_lufs=float(loudness_raw["integrated_lufs"]),
        true_peak_db=float(loudness_raw["true_peak_db"]),
        lra=float(loudness_raw["lra"]),
    )
    subtitle = SubtitleSpec(
        font_size=int(subtitle_raw["font_size"]),
        margin_v=int(subtitle_raw["margin_v"]),
    )
    specs: dict[str, ExportSpec] = {}
    for name in ("preview", "final"):
        raw = _object(root[name], name)
        specs[name] = ExportSpec(
            timeline=timeline,
            vcodec=str(raw["vcodec"]),
            bitrate=str(raw["bitrate"]) if raw.get("bitrate") is not None else None,
            crf=int(raw["crf"]) if raw.get("crf") is not None else None,
            preset=str(raw["preset"]) if raw.get("preset") is not None else None,
            tag=str(raw["tag"]) if raw.get("tag") is not None else None,
            acodec=str(raw["acodec"]),
            abitrate=str(raw["abitrate"]),
            subtitle=subtitle,
            loudness=loudness,
        )
    return specs


def validate_final_spec(spec: ExportSpec) -> None:
    if (spec.timeline.width, spec.timeline.height, spec.timeline.fps) != (1920, 1080, 30):
        raise ValueError("Final export must use 1920x1080 at 30 fps")
    if spec.timeline.pix_fmt != "yuv420p":
        raise ValueError("Final export must use yuv420p")
    if spec.vcodec != "hevc_videotoolbox" or spec.tag != "hvc1":
        raise ValueError("Final export must use hevc_videotoolbox with hvc1")
    if spec.acodec != "aac" or spec.abitrate != "192k":
        raise ValueError("Final export must use AAC 192k")


SPECS = load_export_specs()
PREVIEW_SPEC = SPECS["preview"]
FINAL_SPEC = SPECS["final"]
validate_final_spec(FINAL_SPEC)


def video_codec_args(spec: ExportSpec, *, test_codec: str | None = None) -> list[str]:
    """生成视频编码参数；测试编码器只能由调用方显式注入。"""
    codec = test_codec or spec.vcodec
    args = ["-c:v", codec]
    if codec == "libx264":
        args.extend(["-preset", spec.preset or "veryfast"])
        if spec.crf is not None:
            args.extend(["-crf", str(spec.crf)])
    elif spec.bitrate is not None:
        args.extend(["-b:v", spec.bitrate])
    if spec.tag and codec == spec.vcodec:
        args.extend(["-tag:v", spec.tag])
    return args


def audio_codec_args(spec: ExportSpec) -> list[str]:
    return ["-c:a", spec.acodec, "-b:a", spec.abitrate, "-ar", str(spec.timeline.sample_rate)]
