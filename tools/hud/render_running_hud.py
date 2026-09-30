#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from datetime import timezone
from pathlib import Path

import fitdecode


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HUD_DIR = Path(__file__).resolve().parent
_weather_spec = importlib.util.spec_from_file_location("hud_weather", HUD_DIR / "weather.py")
if _weather_spec is None or _weather_spec.loader is None:
    raise SystemExit("Missing tools/hud/weather.py")
_weather = importlib.util.module_from_spec(_weather_spec)
_weather_spec.loader.exec_module(_weather)
fetch_hourly_weather = _weather.fetch_hourly_weather
write_weather_json = _weather.write_weather_json
WEATHER_CITIES = _weather.CITIES


DEFAULT_TEMPLATE = HUD_DIR / "templates" / "gopro-dashboard-overlay-running-hud-landscape-map-safe.xml"
def _default_hud_font_path() -> Path:
    # Cross-platform default: bundled Source Han Sans SC Heavy (Mac+Linux).
    # Face index / wght axis applied inside gopro_dashboard_wrap.load_font.
    # System Hiragino/PingFang/Noto only if bundle missing.
    bundled = HUD_DIR / "fonts" / "SourceHanSansSC-Heavy.otf"
    for candidate in (
        bundled,
        HUD_DIR / "fonts" / "NotoSansSC-VF.ttf",
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ):
        if candidate.exists():
            return candidate
    return bundled


DEFAULT_FONT = _default_hud_font_path()
DEFAULT_CONFIG_DIR = Path("/tmp/gopro-overlay-config")
DEFAULT_CACHE_DIR = Path("/tmp/gopro-overlay-cache")
FFMPEG_PROFILES = HUD_DIR / "ffmpeg-profiles.json"

# overlay-only 的对外名称 → gopro-overlay --profile
# png 走内置 mov（PNG-in-MOV）；其余来自 tools/hud/ffmpeg-profiles.json
OVERLAY_PROFILE_MAP = {
    "prores4444": "prores4444",
    "png": "mov",
    "qtrle": "qtrle",
}


def run(cmd: list[str], dry_run: bool = False) -> None:
    print("$", " ".join(str(part) for part in cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def discover_clips(media_dir: Path) -> list[Path]:
    clips = sorted(media_dir.glob("*-run-*.mp4"))
    if clips:
        return clips
    return sorted(path for path in media_dir.glob("*.mp4") if not path.name.endswith(("-open.mp4", "-close.mp4")))


def resolve_total_distance_meters(fit_path: Path) -> int | None:
    total_distance_m = None

    with fitdecode.FitReader(fit_path) as fit_reader:
        for frame in (
            frame
            for frame in fit_reader
            if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == "record"
        ):
            for field in frame.fields:
                if field.name != "distance" or field.value is None:
                    continue
                try:
                    distance_m = float(field.value)
                except (TypeError, ValueError):
                    continue
                if total_distance_m is None or distance_m > total_distance_m:
                    total_distance_m = distance_m

    if total_distance_m is None:
        return None

    return max(1, int(round(total_distance_m)))


def _remove_named_translate(root: ET.Element, target_name: str) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "translate" and child.attrib.get("name") == target_name:
                parent.remove(child)
                return


def resolve_fit_geo_time(fit_path: Path) -> tuple[float | None, float | None, datetime | None, datetime | None]:
    lat = lon = None
    tmin = tmax = None
    with fitdecode.FitReader(fit_path) as fit_reader:
        for frame in (
            frame
            for frame in fit_reader
            if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == "record"
        ):
            fields = {field.name: field.value for field in frame.fields}
            ts = fields.get("timestamp")
            if ts is not None:
                if getattr(ts, "tzinfo", None) is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if tmin is None or ts < tmin:
                    tmin = ts
                if tmax is None or ts > tmax:
                    tmax = ts
            plat = fields.get("position_lat")
            plon = fields.get("position_long")
            if lat is None and plat is not None and plon is not None:
                lat_v = float(plat)
                lon_v = float(plon)
                if abs(lat_v) > 90:
                    lat_v = lat_v * (180.0 / 2**31)
                    lon_v = lon_v * (180.0 / 2**31)
                lat, lon = lat_v, lon_v
    return lat, lon, tmin, tmax


def prepare_resolved_template(
    template: Path,
    fit_path: Path,
    shoe_name: str | None = None,
    shoe_total_km_after_run: float | None = None,
    weather_ok: bool = False,
) -> Path:
    total_distance_m = resolve_total_distance_meters(fit_path)

    tree = ET.parse(template)
    root = tree.getroot()

    if total_distance_m is not None:
        # 进度条和短滑块都用本场总里程当 max，这样填充和当前点对齐
        for progress_bar in root.findall(".//component[@name='distance_progress_bar']"):
            progress_bar.set("max", str(total_distance_m))
        for progress_knob in root.findall(".//component[@name='distance_progress_knob']"):
            progress_knob.set("max", str(total_distance_m))

        total_distance_text = root.find(".//component[@name='distance_total_text']")
        if total_distance_text is not None:
            total_distance_unit = root.find(".//component[@name='distance_total_unit']")
            if total_distance_unit is not None:
                total_distance_text.text = f"{total_distance_m / 1000:.2f}"
            else:
                total_distance_text.text = f"{total_distance_m / 1000:.2f} km"

    shoe_group_name = "shoe_mileage_group"
    shoe_name_component = root.find(".//component[@name='shoe_name_text']")
    cleaned_shoe_name = (shoe_name or "").strip()
    if shoe_name_component is None or not cleaned_shoe_name or shoe_total_km_after_run is None:
        _remove_named_translate(root, shoe_group_name)
    else:
        shoe_name_component.text = cleaned_shoe_name

    if not weather_ok:
        _remove_named_translate(root, "weather_group")

    resolved_template = DEFAULT_CONFIG_DIR / f"{template.stem}-resolved.xml"
    tree.write(resolved_template, encoding="unicode")
    return resolved_template


def ensure_ffmpeg_profiles(config_dir: Path) -> None:
    # 把仓库里的透明图层编码配置拷到 gopro-overlay 的 config-dir
    dest = config_dir / "ffmpeg-profiles.json"
    shutil.copyfile(FFMPEG_PROFILES, dest)


def probe_source_video(path: Path) -> dict[str, str | int]:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,bit_rate,width,height",
            "-show_entries",
            "format=bit_rate",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    data = json.loads(raw)
    stream = data["streams"][0]
    fmt = data.get("format") or {}
    bit_rate = int(stream.get("bit_rate") or fmt.get("bit_rate") or 0)
    return {
        "codec": str(stream.get("codec_name") or "hevc"),
        "bit_rate": bit_rate,
        "width": int(stream.get("width") or 1920),
        "height": int(stream.get("height") or 1080),
    }


def bake_matched_preview(source: Path, overlay: Path, dest: Path, dry_run: bool = False) -> None:
    # 预览/审片跟原片同档：编码、码率、分辨率都不降
    spec = probe_source_video(source)
    bit_rate = int(spec["bit_rate"])
    if bit_rate < 1_000_000:
        bit_rate = 20_000_000
    codec = str(spec["codec"])
    if codec in {"hevc", "h265"}:
        vcodec = ["-c:v", "hevc_videotoolbox", "-b:v", str(bit_rate), "-tag:v", "hvc1"]
    else:
        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", str(bit_rate)]
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-i",
        str(overlay),
        "-filter_complex",
        "[0:v][1:v]overlay=format=auto",
        *vcodec,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(dest),
    ]
    run(cmd, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render running HUDs automatically with gopro-dashboard-overlay."
    )
    parser.add_argument("--media-dir", required=True, help="Directory containing MP4 clips and FIT file")
    parser.add_argument("--fit", help="FIT file path; defaults to the first *-run-data.fit in media dir")
    parser.add_argument("--clips", nargs="*", help="Specific clip filenames inside media dir")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="Layout XML template path")
    parser.add_argument(
        "--map",
        action="store_true",
        help="Use the platform-safe full-route map HUD template (same as default unless --template overrides it)",
    )
    parser.add_argument("--font", default=str(DEFAULT_FONT), help="Font path passed to gopro-overlay; wrap overrides to unified PingFang SC / Noto Sans CJK SC (CJK+Latin one face)")
    parser.add_argument(
        "--video-end-time-mode",
        "--video-time-mode",
        dest="video_end_time_mode",
        choices=["file-created", "file-modified"],
        default="file-modified",
        help="Which file timestamp should be treated as the video end time; the start time is inferred as end time minus duration. For this workflow, file-modified is the safer default on macOS because gopro-dashboard's file-created mode uses ctime",
    )
    parser.add_argument("--output-dir", help="Defaults to <media-dir>/hud-renders")
    parser.add_argument("-sn", "--shoe-name", default="Secret Shoe", help="HUD shoe name (default: Secret Shoe)")
    parser.add_argument(
        "-sk",
        "--shoe-total-km-after-run",
        type=float,
        help="Cumulative shoe mileage after this run, in km; defaults to this run's total distance",
    )
    parser.add_argument(
        "--overlay-only",
        action="store_true",
        help="Export HUD as a transparent overlay (MOV with alpha) instead of baking it into the video",
    )
    parser.add_argument(
        "--overlay-profile",
        choices=sorted(OVERLAY_PROFILE_MAP),
        default="prores4444",
        help="Alpha encode for --overlay-only. prores4444 is Jianying-friendly; png is PNG-in-MOV; qtrle is smaller Animation codec",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="After overlay, bake a watchable mp4 matching the source codec/bitrate/size. Implies --overlay-only",
    )
    parser.add_argument("--no-weather", action="store_true", help="Do not fetch Open-Meteo weather for the HUD")
    parser.add_argument(
        "--weather-json",
        help="Use this hourly weather JSON instead of fetching Open-Meteo",
    )
    parser.add_argument(
        "--weather-city",
        choices=sorted(WEATHER_CITIES),
        help="Fetch Open-Meteo with city coordinates and FIT time window. Do not send FIT GPS.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.preview:
        args.overlay_only = True

    gopro_python = REPO_ROOT / ".venv" / "bin" / "python"
    gopro_dashboard = Path(__file__).resolve().parent / "gopro_dashboard_wrap.py"
    if not gopro_python.exists():
        raise SystemExit(f"Missing CLI: {gopro_python}")
    if not gopro_dashboard.exists():
        raise SystemExit(f"Missing CLI: {gopro_dashboard}")

    media_dir = Path(args.media_dir).expanduser().resolve()
    template = Path(args.template).expanduser().resolve()
    if args.map and str(args.template) == str(DEFAULT_TEMPLATE):
        template = DEFAULT_TEMPLATE.resolve()
    font = Path(args.font).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else media_dir / "hud-renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if args.overlay_only:
        ensure_ffmpeg_profiles(DEFAULT_CONFIG_DIR)

    if args.fit:
        fit = Path(args.fit).expanduser().resolve()
    else:
        fits = sorted(media_dir.glob("*-run-data.fit"))
        if not fits:
            raise SystemExit(f"No FIT file found in {media_dir}")
        fit = fits[0]

    if args.clips:
        clips = [media_dir / clip for clip in args.clips]
    else:
        clips = discover_clips(media_dir)

    if not clips:
        raise SystemExit(f"No clips found in {media_dir}")

    fit_total_km = 0.0
    total_distance_m = resolve_total_distance_meters(fit)
    if total_distance_m is not None:
        fit_total_km = total_distance_m / 1000
    default_shoe_total_km_after_run = args.shoe_total_km_after_run
    if default_shoe_total_km_after_run is None:
        default_shoe_total_km_after_run = fit_total_km
    os.environ["HUD_SHOE_TOTAL_KM_AFTER_RUN"] = str(default_shoe_total_km_after_run)
    os.environ["HUD_SHOE_RUN_TOTAL_KM"] = f"{fit_total_km:.6f}"
    print(
        f"Shoe: after={default_shoe_total_km_after_run:.2f} km  "
        f"run={fit_total_km:.3f} km  before={max(0.0, default_shoe_total_km_after_run - fit_total_km):.2f} km"
    )

    weather_path = media_dir / "weather-hourly.json"
    weather_ok = False
    if args.no_weather:
        pass
    elif args.weather_json:
        weather_path = Path(args.weather_json).expanduser().resolve()
        if not weather_path.exists():
            raise SystemExit(f"Weather JSON not found: {weather_path}")
        payload = json.loads(weather_path.read_text(encoding="utf-8"))
        weather_ok = bool(payload.get("hours"))
        print(f"Weather hours: {len(payload.get('hours') or [])} from {weather_path}")
    else:
        _fit_lat, _fit_lon, tmin, tmax = resolve_fit_geo_time(fit)
        if args.weather_city:
            lat, lon = WEATHER_CITIES[args.weather_city]
        else:
            lat, lon = _fit_lat, _fit_lon
        if lat is not None and lon is not None and tmin is not None and tmax is not None:
            try:
                if args.dry_run:
                    weather_ok = True
                    print(f"Weather would fetch Open-Meteo for {lat:.4f},{lon:.4f} {tmin} -> {tmax}")
                else:
                    hours = fetch_hourly_weather(lat, lon, tmin, tmax)
                    write_weather_json(weather_path, lat, lon, hours)
                    weather_ok = bool(hours)
                    print(f"Weather hours: {len(hours)} ({lat:.4f},{lon:.4f})")
            except Exception as exc:
                print(f"Weather fetch skipped: {exc}")
        else:
            print("Weather fetch skipped: missing coordinates or FIT time")
    os.environ["HUD_WEATHER_JSON"] = str(weather_path)

    resolved_template = prepare_resolved_template(
        template,
        fit,
        shoe_name=args.shoe_name,
        shoe_total_km_after_run=default_shoe_total_km_after_run,
        weather_ok=weather_ok,
    )

    for clip in clips:
        clip = clip.expanduser().resolve()
        if args.overlay_only:
            out = output_dir / f"{clip.stem}-hud-alpha.mov"
        else:
            out = output_dir / f"{clip.stem}-hud.mp4"
        cmd = [
            str(gopro_python),
            str(gopro_dashboard),
            str(clip),
            str(out),
            "--font",
            str(font),
            "--config-dir",
            str(DEFAULT_CONFIG_DIR),
            "--cache-dir",
            str(DEFAULT_CACHE_DIR),
            "--gpx",
            str(fit),
            "--use-fit-only",
            "--video-time-end",
            args.video_end_time_mode,
            "--layout",
            "xml",
            "--layout-xml",
            str(resolved_template),
            "--units-distance",
            "km",
        ]
        if args.overlay_only:
            cmd.extend(
                [
                    "--generate",
                    "overlay",
                    "--profile",
                    OVERLAY_PROFILE_MAP[args.overlay_profile],
                    "--bg",
                    "0,0,0,0",
                ]
            )
        cmd.extend(["--shoe-name", args.shoe_name])
        cmd.extend(["--shoe-total-km-after-run", str(default_shoe_total_km_after_run)])
        run(cmd, dry_run=args.dry_run)
        if args.preview:
            preview = output_dir / f"{clip.stem}-hud-preview.mp4"
            bake_matched_preview(clip, out, preview, dry_run=args.dry_run)

    print(f"\nDone. Output directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
