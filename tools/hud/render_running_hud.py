#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    fitdecode = importlib.import_module("fitdecode")
except ImportError:  # 运行时由仓库 .venv 提供；静态检查环境可能没有它。
    fitdecode = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_spec import PREVIEW_SPEC, video_codec_args
import log_timeline
import program_edl as edl
import todo_list

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


_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def run(
    cmd: list[str],
    *,
    dry_run: bool = False,
    log_path: Path | None = None,
    label: str | None = None,
) -> None:
    header = f"[{label}] " if label else ""
    _log(f"{header}$ {' '.join(str(part) for part in cmd)}")
    if dry_run:
        return
    if log_path is None:
        subprocess.run(cmd, check=True)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"$ {' '.join(str(part) for part in cmd)}\n")
        logf.flush()
        proc = subprocess.run(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


CLIP_SKIP = ("run-final", "orient", "transpose", "-raw", "pre-", "-bad", "-hud")


def discover_clips(media_dir: Path) -> list[Path]:
    # 只要 run-a / run-b 这类原段；成片 run-final、朝向备份、raw 不能再叠一层 HUD
    clips = sorted(p for p in media_dir.glob("*-run-*.mp4") if not any(k in p.name for k in CLIP_SKIP))
    if clips:
        return clips
    return sorted(path for path in media_dir.glob("*.mp4")
                  if not path.name.endswith("-open.mp4") and "-close" not in path.name  # close / close-N / close-stats
                  and not any(k in path.name for k in CLIP_SKIP))


def resolve_total_distance_meters(fit_path: Path) -> int | None:
    if fitdecode is None:
        raise RuntimeError("fitdecode is required; run this script with the repository .venv Python")
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

    return max(1, round(total_distance_m))


def _remove_named_translate(root: ET.Element, target_name: str) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "translate" and child.attrib.get("name") == target_name:
                parent.remove(child)
                return


def resolve_fit_geo_time(fit_path: Path) -> tuple[float | None, float | None, datetime | None, datetime | None]:
    if fitdecode is None:
        raise RuntimeError("fitdecode is required; run this script with the repository .venv Python")
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
        # 鞋名右对齐：左内边距与右边距同为 20（按实际字形宽度算锚点）
        try:
            from PIL import ImageFont
            font_path = Path(__file__).resolve().parent / "fonts" / "SourceHanSansSC-Heavy.otf"
            size = int(shoe_name_component.get("size") or 15)
            font = ImageFont.truetype(str(font_path), size)
            name_w = font.getbbox(cleaned_shoe_name)[2] - font.getbbox(cleaned_shoe_name)[0]
            pad = 20
            shoe_name_component.set("x", str(pad + name_w))
            shoe_name_component.set("align", "right")
        except Exception:
            pass

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


def bake_matched_preview(
    source: Path,
    overlay: Path,
    dest: Path,
    dry_run: bool = False,
    *,
    log_path: Path | None = None,
    label: str | None = None,
) -> None:
    # 单段 preview 使用统一轻量规格。整条审片预览只拼接这些文件，不再从原片和 alpha 重压。
    vcodec = video_codec_args(PREVIEW_SPEC)
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
    if dry_run or log_path is None:
        run(cmd, dry_run=dry_run, label=label)
        return
    # Append into the same per-clip render log.
    header = f"[{label}] " if label else ""
    _log(f"{header}$ {' '.join(str(part) for part in cmd)}")
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"$ {' '.join(str(part) for part in cmd)}\n")
        logf.flush()
        proc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)



def render_one_clip(
    *,
    clip: Path,
    output_dir: Path,
    gopro_python: Path,
    gopro_dashboard: Path,
    font: Path,
    fit: Path,
    resolved_template: Path,
    video_end_time_mode: str,
    overlay_only: bool,
    overlay_profile: str,
    preview: bool,
    shoe_name: str,
    shoe_total_km_after_run: float,
    dry_run: bool,
) -> Path:
    """Render one clip. Returns output path. Raises on failure with clip in message."""
    clip = clip.expanduser().resolve()
    label = clip.name
    if overlay_only:
        out = output_dir / f"{clip.stem}-hud-alpha.mov"
    else:
        out = output_dir / f"{clip.stem}-hud.mp4"
    # Per-clip cache avoids tile/map write races when jobs > 1.
    cache_dir = DEFAULT_CACHE_DIR / clip.stem
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{clip.stem}-hud-render.log"
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
        str(cache_dir),
        "--gpx",
        str(fit),
        "--use-fit-only",
        "--video-time-end",
        video_end_time_mode,
        "--layout",
        "xml",
        "--layout-xml",
        str(resolved_template),
        "--units-distance",
        "km",
    ]
    if overlay_only:
        cmd.extend(
            [
                "--generate",
                "overlay",
                "--profile",
                OVERLAY_PROFILE_MAP[overlay_profile],
                "--bg",
                "0,0,0,0",
            ]
        )
    cmd.extend(["--shoe-name", shoe_name])
    cmd.extend(["--shoe-total-km-after-run", str(shoe_total_km_after_run)])
    _log(f"[{label}] start -> {out.name}")
    try:
        run(cmd, dry_run=dry_run, log_path=None if dry_run else log_path, label=label)
        if preview:
            preview_out = output_dir / f"{clip.stem}-hud-preview.mp4"
            bake_matched_preview(
                clip,
                out,
                preview_out,
                dry_run=dry_run,
                log_path=None if dry_run else log_path,
                label=label,
            )
        _log(f"[{label}] ok -> {out.name}" + (f" (log {log_path.name})" if not dry_run else ""))
        return out
    except Exception as exc:
        raise RuntimeError(f"{label} failed: {exc}; see {log_path}") from exc


def _record_only(args) -> int:
    if args.preview:
        raise SystemExit("--record-only does not render, and it does not bake a preview")
    if args.shoe_total_km_after_run is None:
        raise SystemExit("--record-only needs -sk (cumulative km after this run)")
    media_dir = Path(args.media_dir).expanduser().resolve()
    table = edl.load_media(media_dir)
    city = None if args.no_weather else (args.weather_city or "shanghai")
    edl.save(media_dir, edl.record_hud(
        table,
        shoe_name=args.shoe_name,
        shoe_km_after=args.shoe_total_km_after_run if args.shoe_total_km_after_run is not None else 0.0,
        weather_city=city,
        overlay_profile=args.overlay_profile,
        video_end_time_mode=args.video_end_time_mode,
    ))
    todo_list.mark(media_dir, "hud-record", "done")
    print(edl.program_path(media_dir))
    return 0


def _alpha_dest(directory: Path, stem: str, profile: str) -> Path:
    # 渲染器固定写 {stem}-hud-alpha.mov。别的规格放进子目录，避免盖掉已有 ProRes。
    if profile == "prores4444":
        return directory / f"{stem}-hud-alpha.mov"
    return directory / profile / f"{stem}-hud-alpha.mov"


def _alpha_matches(path: Path, profile: str) -> bool:
    try:
        codec = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(path)],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    expected = {"qtrle": "qtrle", "prores4444": "prores", "png": "png"}[profile]
    return codec == expected or codec.startswith(expected)


def export_alphas(media_dir: Path, table: dict, durations: dict[str, float], *, dry_run: bool) -> list[Path]:
    """只给留下的区间渲 qtrle（或表里记的规格）透明层。已有同名文件就复用，避免重跑。"""
    hud = table.get("hud") or {}
    if not hud.get("recorded"):
        raise SystemExit("HUD data is not recorded on the program timeline")
    fits = sorted(media_dir.glob("*-run-data.fit"))
    if not fits and not dry_run:
        raise SystemExit(f"No FIT file found in {media_dir}")
    fit = fits[0] if fits else media_dir / "run-data.fit"
    weather = media_dir / "weather-hourly.json"
    paths: list[Path] = []
    for job in edl.hud_jobs(table):
        src = media_dir / job["clip"]
        full = durations.get(job["clip"])
        is_full = full is not None and job["src_start_s"] <= 0.02 and job["src_end_s"] >= full - 0.02
        profile = str(job["overlay_profile"])
        if is_full:
            render_dir = media_dir
            clip_name = src.name
            dest = _alpha_dest(media_dir / "hud-renders", src.stem, profile)
        else:
            render_dir = media_dir / "hud-renders" / "keeps"
            clip_name = f"{src.stem}-{job['src_start_s']:.3f}-{job['src_end_s']:.3f}.mp4"
            dest = _alpha_dest(render_dir, Path(clip_name).stem, profile)
        paths.append(dest)
        if dest.is_file() and _alpha_matches(dest, profile):
            _log(f"reuse {dest.name}")
            continue
        if dry_run:
            _log(f"would render {dest.name} from {job['src_start_s']:.3f}-{job['src_end_s']:.3f} profile={job['overlay_profile']}")
            continue
        render_dir.mkdir(parents=True, exist_ok=True)
        if not is_full:
            piece = render_dir / clip_name
            _trim_keep_for_hud(src, piece, float(job["src_start_s"]), float(job["src_end_s"]), float(full or 0))
        argv = [
            "--media-dir", str(render_dir),
            "--fit", str(fit),
            "--clips", clip_name,
            "--overlay-only",
            "--overlay-profile", str(job["overlay_profile"]),
            "--output-dir", str(dest.parent),
            "-sn", str(hud.get("shoe_name") or "Secret Shoe"),
            "-sk", str(hud.get("shoe_km_after") or 0),
            "-j", "1",
        ]
        if weather.is_file():
            argv.extend(["--weather-json", str(weather)])
        elif hud.get("weather_city"):
            argv.extend(["--weather-city", str(hud["weather_city"])])
        else:
            argv.append("--no-weather")
        rc = main(argv)
        if rc:
            raise SystemExit(f"HUD render failed for {clip_name}")
        if not dest.is_file():
            raise SystemExit(f"HUD alpha missing: {dest}")
    return paths


def _trim_keep_for_hud(src: Path, dest: Path, start: float, end: float, duration: float) -> None:
    """裁出留下的区间，并把 mtime 设成原片时间上的结束点，HUD 才不会按成片时间取样。"""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-i", str(src),
        "-vf", f"trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS",
        "-af", f"atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        str(dest),
    ]
    subprocess.run(cmd, check=True)
    mtime = edl.kept_alpha_mtime(src.stat().st_mtime, duration, end)
    os.utime(dest, (mtime, mtime))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.record_only:
        return _record_only(args)
    if args.preview:
        args.overlay_only = True
        _log("warning: --preview encodes an uncut review file in this same job; the official flow does not")
    media_dir = Path(args.media_dir).expanduser()
    with log_timeline.span(media_dir, "hud-render", enabled=not args.dry_run) as wall:
        wall.rc = _render_main(args)
        return wall.rc


def _parse_args(argv: list[str] | None = None):
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
    parser.add_argument(
        "--font",
        default=str(DEFAULT_FONT),
        help="Font file for the HUD (CJK+Latin). Default: bundled Source Han Sans SC Heavy. "
        "Honored by wrap unless HUD_FONT_PATH is set (env wins). Optional HUD_FONT_INDEX / HUD_FONT_WGHT for TTC/VF.",
    )
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
        default="qtrle",
        help="Alpha encode for --overlay-only. Default qtrle (lighter than ProRes 4444). png is PNG-in-MOV; prores4444 is the heavier Jianying-friendly option",
    )
    parser.add_argument(
        "--record-only",
        action="store_true",
        help="Write shoe, weather, and overlay profile into logs/program.json. Do not render",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="After overlay, bake a lightweight review mp4. Implies --overlay-only; final export reads the source clip and alpha layer instead",
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
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=2,
        help="Parallel clip renders (default: 2). Use 1 for serial.",
    )
    return parser.parse_args(argv)


def _render_main(args) -> int:
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
        _, _, tmin, tmax = resolve_fit_geo_time(fit)
        if not args.weather_city:
            # 不把 FIT GPS 发给 Open-Meteo（CLAUDE.md / p3-hud 硬规则）；忘了 flag 就停，不偷偷用坐标
            raise SystemExit("天气需要 --weather-city shanghai（或 --weather-json / --no-weather）；不会用 FIT 经纬度查天气。")
        lat, lon = WEATHER_CITIES[args.weather_city]
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

    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    jobs = min(args.jobs, len(clips))
    _log(f"Rendering {len(clips)} clip(s) with --jobs {jobs}")

    def _kwargs(clip: Path) -> dict:
        return dict(
            clip=clip,
            output_dir=output_dir,
            gopro_python=gopro_python,
            gopro_dashboard=gopro_dashboard,
            font=font,
            fit=fit,
            resolved_template=resolved_template,
            video_end_time_mode=args.video_end_time_mode,
            overlay_only=args.overlay_only,
            overlay_profile=args.overlay_profile,
            preview=args.preview,
            shoe_name=args.shoe_name,
            shoe_total_km_after_run=default_shoe_total_km_after_run,
            dry_run=args.dry_run,
        )

    failures: list[str] = []
    if jobs == 1:
        for clip in clips:
            try:
                render_one_clip(**_kwargs(clip))
            except Exception as exc:
                failures.append(str(exc))
                _log(f"ERROR: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="hud") as pool:
            futures = {pool.submit(render_one_clip, **_kwargs(clip)): clip for clip in clips}
            for fut in as_completed(futures):
                clip = futures[fut]
                try:
                    fut.result()
                except Exception as exc:
                    failures.append(str(exc))
                    _log(f"ERROR: {exc}")

    if failures:
        _log("\nHUD render failed for:")
        for item in failures:
            _log(f"  - {item}")
        raise SystemExit(1)

    _log(f"\nDone. Output directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
