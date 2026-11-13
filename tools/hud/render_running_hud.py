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
    output_path: Path | None = None,
    range_start: float | None = None,
    range_end: float | None = None,
) -> Path:
    """Render one clip. Returns output path. Raises on failure with clip in message."""
    clip = clip.expanduser().resolve()
    label = clip.name
    if output_path is not None:
        out = output_path
        out.parent.mkdir(parents=True, exist_ok=True)
    elif overlay_only:
        out = output_dir / f"{clip.stem}-hud-alpha.mov"
    else:
        out = output_dir / f"{clip.stem}-hud.mp4"
    # Per-clip cache avoids tile/map write races when jobs > 1.
    cache_name = clip.stem if range_start is None else f"{clip.stem}-{range_start:.3f}-{range_end:.3f}"
    cache_dir = DEFAULT_CACHE_DIR / cache_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_path = out.parent / f"{out.stem}-hud-render.log"
    if overlay_only:
        cmd = hud_overlay_command(
            gopro_python=gopro_python,
            gopro_dashboard=gopro_dashboard,
            clip=clip,
            out=out,
            font=font,
            fit=fit,
            template=resolved_template,
            cache_dir=cache_dir,
            video_end_time_mode=video_end_time_mode,
            overlay_profile=overlay_profile,
            shoe_name=shoe_name,
            shoe_total_km_after_run=shoe_total_km_after_run,
            range_start=range_start,
            range_end=range_end,
        )
    else:
        if range_start is not None:
            raise ValueError("a source-time window is only supported for overlay alpha")
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
            "--shoe-name",
            shoe_name,
            "--shoe-total-km-after-run",
            str(shoe_total_km_after_run),
        ]
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
    todo_list.clear_prep(media_dir, ("hud-render",))
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


# 和渲染器默认 --jobs、已发布期次用过的并行度一致。每段缓存目录按文件名分开。
HUD_EXPORT_JOBS = 2
HUD_ALPHA_MANIFEST = "hud-alpha.json"


def kept_source_steps(steps: list[float], start_s: float, end_s: float) -> list[float]:
    """原片时钟上的半开区间 [start, end)。透明层只画这些帧，不先裁出画面文件。"""
    from hud_window import iter_kept_ticks

    start = float(start_s)
    end = float(end_s)
    return [float(tick) for tick in iter_kept_ticks((float(step) for step in steps), start, end)]


def alpha_dest(media_dir: Path, job: dict, *, fps: int = 30) -> Path:
    """透明层直接写到 hud-renders/<profile>/，不经过 hud-renders/keeps/。"""
    profile = str(job["overlay_profile"])
    stem = Path(str(job["clip"])).stem
    start_f = int(round(float(job["src_start_s"]) * fps))
    end_f = int(round(float(job["src_end_s"]) * fps))
    return _alpha_dest(media_dir / "hud-renders", f"{stem}-f{start_f}-{end_f}", profile)


def job_is_full_clip(job: dict, full: float | None) -> bool:
    if full is None:
        return False
    return float(job["src_start_s"]) <= 0.02 and float(job["src_end_s"]) >= float(full) - 0.02


def hud_signature(table: dict, *, fps: int = 30) -> dict:
    hud = table.get("hud") or {}
    return {
        "overlay_profile": hud.get("overlay_profile") or edl.DEFAULT_OVERLAY_PROFILE,
        "shoe_name": hud.get("shoe_name"),
        "shoe_km_after": hud.get("shoe_km_after"),
        "weather_city": hud.get("weather_city"),
        "fps": fps,
        "jobs": [
            {
                "clip": job["clip"],
                "src_start_s": round(float(job["src_start_s"]), 6),
                "src_end_s": round(float(job["src_end_s"]), 6),
            }
            for job in edl.hud_jobs(table, fps)
        ],
    }


def hud_manifest_path(media_dir: Path) -> Path:
    return media_dir / "logs" / HUD_ALPHA_MANIFEST


def plan_alpha_jobs(media_dir: Path, table: dict, durations: dict[str, float] | None = None, *, fps: int = 30) -> list[dict]:
    """每个要画 HUD 的留下区间一条。源是原片，产物不是 keeps。"""
    durations = durations or {}
    plans = []
    for job in edl.hud_jobs(table, fps):
        full = durations.get(job["clip"])
        ranged = not job_is_full_clip(job, full)
        plans.append(
            {
                "clip": job["clip"],
                "source": media_dir / job["clip"],
                "dest": alpha_dest(media_dir, job, fps=fps),
                "src_start_s": float(job["src_start_s"]),
                "src_end_s": float(job["src_end_s"]),
                "overlay_profile": str(job["overlay_profile"]),
                "ranged": ranged,
            }
        )
    return plans


def hud_overlay_command(
    *,
    gopro_python: Path,
    gopro_dashboard: Path,
    clip: Path,
    out: Path,
    font: Path,
    fit: Path,
    template: Path,
    cache_dir: Path,
    video_end_time_mode: str,
    overlay_profile: str,
    shoe_name: str,
    shoe_total_km_after_run: float,
    range_start: float | None = None,
    range_end: float | None = None,
    config_dir: Path | None = None,
) -> list[str]:
    """对原片画透明层。切开的区间用 --hud-start/--hud-end，不另写画面文件。"""
    cmd = [
        str(gopro_python),
        str(gopro_dashboard),
        str(clip),
        str(out),
        "--font",
        str(font),
        "--config-dir",
        str(config_dir or DEFAULT_CONFIG_DIR),
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
        str(template),
        "--units-distance",
        "km",
        "--generate",
        "overlay",
        "--profile",
        OVERLAY_PROFILE_MAP[overlay_profile],
        "--bg",
        "0,0,0,0",
        "--shoe-name",
        shoe_name,
        "--shoe-total-km-after-run",
        str(shoe_total_km_after_run),
    ]
    if range_start is not None or range_end is not None:
        if range_start is None or range_end is None:
            raise ValueError("HUD range needs both start and end")
        cmd.extend(["--hud-start", f"{float(range_start):.6f}", "--hud-end", f"{float(range_end):.6f}"])
    return cmd


def hud_keep_trim_cmd(src: Path, dest: Path, start: float, end: float) -> list[str]:
    """旧路径：先把留下的区间编码成画面，再拿去渲 HUD。export_alphas 不再调用。

    留着是因为 copy 会停在关键帧上，时长一变 HUD 取样就偏。新路径不写这个文件。
    """
    if end <= start:
        raise ValueError(f"HUD keep range is empty: {start:.6f}..{end:.6f}")
    length = end - start
    return [
        "ffmpeg", "-y", "-nostdin", "-hide_banner",
        "-ss", f"{start:.6f}",
        "-i", str(src),
        "-t", f"{length:.6f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        str(dest),
    ]


def _trim_keep_for_hud(src: Path, dest: Path, start: float, end: float, duration: float) -> None:
    """裁出留下的区间，并把 mtime 设成原片时间上的结束点，HUD 才不会按成片时间取样。"""
    subprocess.run(hud_keep_trim_cmd(src, dest, start, end), check=True)
    mtime = edl.kept_alpha_mtime(src.stat().st_mtime, duration, end)
    os.utime(dest, (mtime, mtime))


def _trim_keeps(trims: list[tuple[Path, Path, float, float, float]]) -> None:
    if not trims:
        return
    workers = min(HUD_EXPORT_JOBS, len(trims))

    def _one(item: tuple[Path, Path, float, float, float]) -> None:
        src, piece, start, end, full = item
        _trim_keep_for_hud(src, piece, start, end, full)

    if workers == 1:
        for item in trims:
            _one(item)
        return
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hud-trim") as pool:
        futures = [pool.submit(_one, item) for item in trims]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                errors.append(exc)
    if errors:
        raise errors[0]


def overlay_render_argv(
    *,
    render_dir: Path,
    clips: list[str],
    output_dir: Path,
    fit: Path,
    hud: dict,
    weather: Path,
    profile: str,
    jobs: int,
) -> list[str]:
    argv = [
        "--media-dir", str(render_dir),
        "--fit", str(fit),
        "--clips", *clips,
        "--overlay-only",
        "--overlay-profile", profile,
        "--output-dir", str(output_dir),
        "-sn", str(hud.get("shoe_name") or "Secret Shoe"),
        "-sk", str(hud.get("shoe_km_after") or 0),
        "-j", str(jobs),
    ]
    if weather.is_file():
        argv.extend(["--weather-json", str(weather)])
    elif hud.get("weather_city"):
        argv.extend(["--weather-city", str(hud["weather_city"])])
    else:
        argv.append("--no-weather")
    argv.extend(["--video-end-time-mode", str(hud.get("video_end_time_mode") or "file-modified")])
    return argv


def _manifest_files(media_dir: Path, plans: list[dict]) -> list[dict]:
    rows = []
    for plan in plans:
        dest: Path = plan["dest"]
        rows.append(
            {
                "path": dest.relative_to(media_dir).as_posix(),
                "bytes": dest.stat().st_size if dest.is_file() else -1,
                "clip": plan["clip"],
                "src_start_s": plan["src_start_s"],
                "src_end_s": plan["src_end_s"],
                "ranged": bool(plan["ranged"]),
            }
        )
    return rows


def write_alpha_manifest(media_dir: Path, table: dict, plans: list[dict], *, fps: int = 30) -> Path:
    path = hud_manifest_path(media_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "signature": hud_signature(table, fps=fps),
        "files": _manifest_files(media_dir, plans),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def alphas_ready(media_dir: Path, table: dict, *, fps: int = 30) -> bool:
    """清单和文件都对得上当前时间表才复用。对不上就重渲，不读 keeps。"""
    path = hud_manifest_path(media_dir)
    if not path.is_file():
        return False
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if saved.get("signature") != hud_signature(table, fps=fps):
        return False
    files = saved.get("files")
    plans = plan_alpha_jobs(media_dir, table, fps=fps)
    if not isinstance(files, list) or len(files) != len(plans):
        return False
    for row, plan in zip(files, plans, strict=True):
        if not isinstance(row, dict):
            return False
        rel = row.get("path")
        if rel != plan["dest"].relative_to(media_dir).as_posix():
            return False
        dest = media_dir / str(rel)
        if not dest.is_file():
            return False
        try:
            size = int(row.get("bytes"))
        except (TypeError, ValueError):
            return False
        if dest.stat().st_size != size:
            return False
        if "keeps" in dest.parts:
            return False
    return True


def planned_alpha_paths(media_dir: Path, table: dict, *, fps: int = 30) -> list[Path]:
    return [plan["dest"] for plan in plan_alpha_jobs(media_dir, table, fps=fps)]


def export_alphas(
    media_dir: Path,
    table: dict,
    durations: dict[str, float],
    *,
    dry_run: bool,
    fps: int = 30,
) -> list[Path]:
    """按留下的入出点直接画透明层。不写 hud-renders/keeps/。

    整段留下的原片不限窗口，透明层时间从原片 0 起。切开的区间把窗口交给
    gopro 包装脚本，只画这一段；原片像素留到确认导出时再解一次。
    """
    hud = table.get("hud") or {}
    if not hud.get("recorded"):
        raise SystemExit("HUD data is not recorded on the program timeline")
    plans = plan_alpha_jobs(media_dir, table, durations, fps=fps)
    for plan in plans:
        if "keeps" in plan["dest"].parts:
            raise SystemExit(f"HUD alpha must not be written under keeps: {plan['dest']}")
    fits = sorted(media_dir.glob("*-run-data.fit"))
    if not fits and not dry_run:
        raise SystemExit(f"No FIT file found in {media_dir}")
    fit = fits[0] if fits else media_dir / "run-data.fit"
    weather = media_dir / "weather-hourly.json"
    pending = []
    for plan in plans:
        dest = plan["dest"]
        if dest.is_file() and _alpha_matches(dest, plan["overlay_profile"]):
            _log(f"reuse {dest.relative_to(media_dir).as_posix()}")
            continue
        pending.append(plan)
        if dry_run:
            window = ""
            if plan["ranged"]:
                window = f" --hud-start {plan['src_start_s']:.6f} --hud-end {plan['src_end_s']:.6f}"
            _log(
                f"would render {dest.relative_to(media_dir).as_posix()} from {plan['source'].name}"
                f"{window} profile={plan['overlay_profile']}"
            )
    if dry_run:
        return [plan["dest"] for plan in plans]
    groups: dict[str, list[dict]] = {}
    for plan in pending:
        groups.setdefault(plan["overlay_profile"], []).append(plan)
    for profile, jobs in groups.items():
        argv = overlay_render_argv(
            render_dir=media_dir,
            clips=[job["clip"] for job in jobs],
            output_dir=media_dir / "hud-renders" / profile,
            fit=fit,
            hud=hud,
            weather=weather,
            profile=profile,
            jobs=HUD_EXPORT_JOBS,
        )
        args = _parse_args(argv)
        args.alpha_jobs = jobs
        # 不走 main()：调用方决定墙钟记在 hud-render 还是 final-export。
        rc = _render_main(args)
        if rc:
            raise SystemExit(f"HUD render failed for profile {profile}")
    for plan in plans:
        if not plan["dest"].is_file():
            raise SystemExit(f"HUD alpha missing: {plan['dest']}")
    write_alpha_manifest(media_dir, table, plans, fps=fps)
    return [plan["dest"] for plan in plans]


def _render_alpha_jobs(
    jobs: list[dict],
    *,
    gopro_python: Path,
    gopro_dashboard: Path,
    font: Path,
    fit: Path,
    resolved_template: Path,
    video_end_time_mode: str,
    overlay_profile: str,
    shoe_name: str,
    shoe_total_km_after_run: float,
    dry_run: bool,
    jobs_n: int,
) -> int:
    """每个留下的区间单独画。源文件是原片，窗口用 --hud-start/--hud-end。"""
    if jobs_n < 1:
        raise SystemExit("--jobs must be >= 1")
    workers = min(jobs_n, len(jobs))
    _log(f"Rendering {len(jobs)} HUD alpha range(s) with --jobs {workers}")

    def _one(job: dict) -> None:
        start = float(job["src_start_s"]) if job.get("ranged") else None
        end = float(job["src_end_s"]) if job.get("ranged") else None
        render_one_clip(
            clip=Path(job["source"]),
            output_dir=Path(job["dest"]).parent,
            gopro_python=gopro_python,
            gopro_dashboard=gopro_dashboard,
            font=font,
            fit=fit,
            resolved_template=resolved_template,
            video_end_time_mode=video_end_time_mode,
            overlay_only=True,
            overlay_profile=overlay_profile,
            preview=False,
            shoe_name=shoe_name,
            shoe_total_km_after_run=shoe_total_km_after_run,
            dry_run=dry_run,
            output_path=Path(job["dest"]),
            range_start=start,
            range_end=end,
        )

    failures: list[str] = []
    if workers == 1:
        for job in jobs:
            try:
                _one(job)
            except Exception as exc:
                failures.append(str(exc))
                _log(f"ERROR: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hud-alpha") as pool:
            futures = [pool.submit(_one, job) for job in jobs]
            for fut in as_completed(futures):
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
    return 0


def _prep_alpha(args) -> int:
    """时间表冻结后直接渲留下区间的透明层。不等字幕确认，也不写 keeps。"""
    if args.preview:
        raise SystemExit("--prep-alpha does not bake a preview")
    media_dir = Path(args.media_dir).expanduser().resolve()
    table = edl.load_media(media_dir)
    problems = edl.validate(table, require_frozen=True)
    if problems:
        raise SystemExit("program timeline: " + "; ".join(problems))
    if todo_list.load(media_dir).get("preview") != "done":
        raise SystemExit("HUD prep needs preview done; it does not need confirmed subtitles")
    durations: dict[str, float] = {}
    for job in edl.hud_jobs(table):
        path = media_dir / job["clip"]
        if job["clip"] in durations:
            continue
        if not path.is_file():
            if args.dry_run:
                continue
            raise SystemExit(f"program clip not found: {path}")
        try:
            if args.dry_run:
                raw = subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                durations[job["clip"]] = float(raw)
            else:
                durations[job["clip"]] = _probe_duration(path)
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            if not args.dry_run:
                raise
    with log_timeline.span(media_dir, "hud-render", enabled=not args.dry_run) as wall:
        export_alphas(media_dir, table, durations, dry_run=args.dry_run)
        if not args.dry_run:
            todo_list.mark(media_dir, "hud-render", "done")
        wall.rc = 0
        return 0


def _probe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True,
    ).strip()
    return float(raw)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.record_only:
        return _record_only(args)
    if args.prep_alpha:
        return _prep_alpha(args)
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
        "--prep-alpha",
        action="store_true",
        help="After logs/program.json is frozen, draw HUD alpha for kept ranges only. "
        "Does not write hud-renders/keeps and does not wait for confirmed subtitles",
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

    alpha_jobs = list(getattr(args, "alpha_jobs", None) or [])
    if alpha_jobs:
        return _render_alpha_jobs(
            alpha_jobs,
            gopro_python=gopro_python,
            gopro_dashboard=gopro_dashboard,
            font=font,
            fit=fit,
            resolved_template=resolved_template,
            video_end_time_mode=args.video_end_time_mode,
            overlay_profile=args.overlay_profile,
            shoe_name=args.shoe_name,
            shoe_total_km_after_run=default_shoe_total_km_after_run,
            dry_run=args.dry_run,
            jobs_n=args.jobs,
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
