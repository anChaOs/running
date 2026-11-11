"""统一预览与最终导出的规格配置。"""

from __future__ import annotations

import json
import math
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
    # Preview-only. "concat-copy" concatenates rendered segments and stream-copies
    # when the formats already match. Final export leaves this unset.
    assembly: str | None = None


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Export spec {label} must be an object")
    return cast(dict[str, Any], value)


def _required(root: dict[str, Any], key: str, label: str) -> Any:
    if key not in root:
        raise ValueError(f"Export spec {label} is missing {key}")
    return root[key]


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"Export spec {label} must be a positive integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().lstrip("+").isdigit():
        number = int(value)
    else:
        raise ValueError(f"Export spec {label} must be a positive integer")
    if number <= 0:
        raise ValueError(f"Export spec {label} must be a positive integer")
    return number


def _finite_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Export spec {label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"Export spec {label} must be a finite number")
    return number


def load_export_specs(path: Path = SPEC_PATH) -> dict[str, ExportSpec]:
    root = _object(json.loads(path.read_text(encoding="utf-8")), "root")
    timeline_raw = _object(_required(root, "timeline", "root"), "timeline")
    loudness_raw = _object(_required(root, "loudness", "root"), "loudness")
    subtitle_raw = _object(_required(root, "subtitle", "root"), "subtitle")
    timeline = TimelineSpec(
        width=_positive_int(_required(timeline_raw, "width", "timeline"), "timeline.width"),
        height=_positive_int(_required(timeline_raw, "height", "timeline"), "timeline.height"),
        fps=_positive_int(_required(timeline_raw, "fps", "timeline"), "timeline.fps"),
        pix_fmt=str(_required(timeline_raw, "pix_fmt", "timeline")),
        sample_rate=_positive_int(_required(timeline_raw, "sample_rate", "timeline"), "timeline.sample_rate"),
    )
    loudness = LoudnessSpec(
        integrated_lufs=_finite_float(_required(loudness_raw, "integrated_lufs", "loudness"), "loudness.integrated_lufs"),
        true_peak_db=_finite_float(_required(loudness_raw, "true_peak_db", "loudness"), "loudness.true_peak_db"),
        lra=_finite_float(_required(loudness_raw, "lra", "loudness"), "loudness.lra"),
    )
    if loudness.lra <= 0:
        raise ValueError("Export spec loudness.lra must be positive")
    subtitle = SubtitleSpec(
        font_size=_positive_int(_required(subtitle_raw, "font_size", "subtitle"), "subtitle.font_size"),
        margin_v=_positive_int(_required(subtitle_raw, "margin_v", "subtitle"), "subtitle.margin_v"),
    )
    specs: dict[str, ExportSpec] = {}
    for name in ("preview", "final"):
        raw = _object(_required(root, name, "root"), name)
        specs[name] = ExportSpec(
            timeline=timeline,
            vcodec=str(_required(raw, "vcodec", name)),
            bitrate=str(raw["bitrate"]) if raw.get("bitrate") is not None else None,
            crf=_positive_int(raw["crf"], f"{name}.crf") if raw.get("crf") is not None else None,
            preset=str(raw["preset"]) if raw.get("preset") is not None else None,
            tag=str(raw["tag"]) if raw.get("tag") is not None else None,
            acodec=str(_required(raw, "acodec", name)),
            abitrate=str(_required(raw, "abitrate", name)),
            subtitle=subtitle,
            loudness=loudness,
            assembly=str(raw["assembly"]) if raw.get("assembly") not in (None, "") else None,
        )
    validate_final_spec(specs["final"], preview_spec=specs["preview"])
    return specs


def _validate_profile(spec: ExportSpec, name: str) -> None:
    if not spec.vcodec or not spec.acodec or not spec.abitrate:
        raise ValueError(f"Export spec {name} must define video and audio profiles")
    if spec.vcodec == "libx264" and (spec.crf is None or not spec.preset):
        raise ValueError(f"Export spec {name} libx264 profile needs crf and preset")
    if spec.vcodec != "libx264" and spec.bitrate is None:
        raise ValueError(f"Export spec {name} needs bitrate for {spec.vcodec}")


def validate_final_spec(spec: ExportSpec, *, preview_spec: ExportSpec | None = None) -> None:
    """校验配置自身，不把当前 1080p 默认值当成唯一合法时间轴。"""
    timeline = spec.timeline
    if min(timeline.width, timeline.height, timeline.fps, timeline.sample_rate) <= 0:
        raise ValueError("Export timeline dimensions, fps, and sample rate must be positive")
    if timeline.pix_fmt != "yuv420p":
        raise ValueError("Final export must use yuv420p")
    if spec.vcodec != "hevc_videotoolbox" or spec.tag != "hvc1":
        raise ValueError("Final export must use hevc_videotoolbox with hvc1")
    if spec.acodec != "aac" or spec.abitrate != "192k":
        raise ValueError("Final export must use AAC 192k")
    if not spec.bitrate:
        raise ValueError("Final export must define a video bitrate")
    _validate_profile(spec, "final")
    if preview_spec is not None:
        if preview_spec.timeline != timeline:
            raise ValueError("Preview and final profiles must share one timeline")
        _validate_profile(preview_spec, "preview")
        if preview_spec.assembly != "concat-copy":
            raise ValueError("Preview profile must use concat-copy assembly")


SPECS = load_export_specs()
PREVIEW_SPEC = SPECS["preview"]
FINAL_SPEC = SPECS["final"]


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
