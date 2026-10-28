#!/usr/bin/env python3
"""把 open + 带 HUD 的 run-* + close 拼成一条成片。

两端 0.2s 叠化；run 与 run 默认一阵风刮过（横向拖影，约 0.08s 出 + 0.08s 入），叠风声。
吃的是各段头尾，成片时长不变，字幕轴不用重算。
默认不烧字幕；外挂 SRT 另外上传。

混音后默认走响度链（dynaudnorm → compressor → loudnorm I=-16/TP=-1.5），
whoosh 叠完再 leveling，避免整轨盲目抬增益把峰值顶满。--no-loudness-fix 可关。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import wave
from array import array
from pathlib import Path


XFADE = 0.2
WIND_DEFAULT = 0.08
FONT_SRC = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
WHOOSH_PATH = Path(__file__).resolve().parent / "sfx" / "whoosh.wav"


# 成片默认响度链（起点参数；POV 实拍未逐条精调，拼完仍测 LUFS/峰值）。
# 顺序：高通去轰隆 → 轻降噪 → 3.5 kHz 存在感（+2.5 dB）→ 动态拉平人声起伏 → 压缩 → EBU R128 到 −16 LUFS / −1.5 dBTP。
# 意图约等于「整体至少再响 ~3.5 dB / 旧记忆 ×1.5」，但用 leveling+loudnorm，
# 避免 flat gain 先把峰值顶满、轻句仍小。
LOUDNESS_AF = (
    "highpass=f=90,"
    "afftdn=nf=-25,"
    "equalizer=f=3500:t=q:w=1.2:g=2.5,"  # 人声存在感：跑步口播偏闷，轻抬 3.5 kHz
    "dynaudnorm=f=250:g=15:p=0.9:m=8,"
    "acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
    "loudnorm=I=-16:TP=-1.5:LRA=7,"
    "aformat=sample_rates=48000:channel_layouts=stereo"
)


# 两遍 loudnorm：第一遍用同一条链（loudnorm 带 print_format=json）只测量，第二遍把测量值喂回去 + linear=true。
# loudnorm 之前的滤镜和单遍完全一样，只换最后的 loudnorm；测量失败就回到单遍 LOUDNESS_AF。
LOUDNORM_TARGET = "loudnorm=I=-16:TP=-1.5:LRA=7"
LOUDNESS_PRE, _LOUDNESS_POST = LOUDNESS_AF.split(LOUDNORM_TARGET + ",")
assert _LOUDNESS_POST == "aformat=sample_rates=48000:channel_layouts=stereo"
LOUDNESS_MEASURE_AF = f"{LOUDNESS_PRE}{LOUDNORM_TARGET}:print_format=json"


def loudness_af_two_pass(m: dict) -> str:
    return (
        f"{LOUDNESS_PRE}{LOUDNORM_TARGET}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
        f":linear=true:print_format=summary,{_LOUDNESS_POST}"
    )


def parse_loudnorm_json(stderr: str) -> dict | None:
    """从 ffmpeg stderr 里抠 loudnorm 打印的最后一个 JSON 块。"""
    end = stderr.rfind("}")
    start = stderr.rfind("{", 0, end)
    if start < 0 or end < 0:
        return None
    try:
        m = json.loads(stderr[start : end + 1])
    except json.JSONDecodeError:
        return None
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(k in m for k in keys):
        return None
    try:
        vals = [float(m[k]) for k in keys]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in vals):  # 全静音时 input_i=-inf
        return None
    return m


def measure_loudness(inputs: list[list[str]], audio_filter: str) -> dict | None:
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    for spec in inputs:
        cmd.extend(spec)
    cmd.extend(["-filter_complex", audio_filter, "-map", "[a]", "-f", "null", "-"])
    print("$ (loudnorm pass 1, audio only)", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        return None
    return parse_loudnorm_json(proc.stderr)


def measure_output(path: Path) -> dict | None:
    """成片实测 I / TP / LRA（只解码音频）。"""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", f"{LOUDNORM_TARGET}:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return parse_loudnorm_json(proc.stderr) if proc.returncode == 0 else None


# ---------- 叠加层（下三分之一动画 / 小视频，按成片时间轴摆，可停住到指定时间） ----------

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def parse_time(v: object) -> float:
    """'5:50' / '1:05:50' / '350.5' / 350 → 秒。"""
    if isinstance(v, (int, float)):
        return float(v)
    parts = str(v).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"bad time: {v!r}")
    sec = 0.0
    for part in parts:
        sec = sec * 60 + float(part)
    return sec


def find_overlays_file(media_dir: Path, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise SystemExit(f"overlays file not found: {p}")
        return p
    repo = Path(__file__).resolve().parents[2]
    for cand in (media_dir / "overlays.json", repo / "episodes" / media_dir.name / "overlays.json"):
        if cand.is_file():
            return cand
    return None


def load_overlays(cfg_path: Path, media_dir: Path) -> list[dict]:
    """读 overlays.json；只做静态校验，成片时间轴上的换算放到 resolve_overlays。"""
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    items = data.get("overlays", data) if isinstance(data, dict) else data
    out: list[dict] = []
    for n, raw in enumerate(items, start=1):
        if "file" not in raw or "start" not in raw:
            raise SystemExit(f"{cfg_path}: overlay #{n} 要有 file 和 start")
        f = Path(raw["file"]).expanduser()
        if not f.is_absolute():
            f = (media_dir / f) if (media_dir / f).exists() else (cfg_path.parent / f)
        if not f.is_file():
            raise SystemExit(f"{cfg_path}: overlay #{n} 文件不存在：{f}")
        anchor = raw.get("anchor", "final")
        if anchor not in ("final", "close"):
            raise SystemExit(f"{cfg_path}: overlay #{n} anchor 只能是 final / close")
        is_image = f.suffix.lower() in IMAGE_EXT
        start = parse_time(raw["start"])
        until = parse_time(raw["hold_until"]) if raw.get("hold_until") is not None else None
        if until is None and is_image:
            raise SystemExit(f"{cfg_path}: overlay #{n} 是图片，要给 hold_until")
        if until is not None and until <= start:
            raise SystemExit(f"{cfg_path}: overlay #{n} hold_until 要晚于 start")
        out.append({
            "n": n, "file": f, "anchor": anchor, "start": start, "until": until, "is_image": is_image,
            "src_dur": None if is_image else probe_duration(f),
            "x": str(raw.get("x", 0)), "y": str(raw.get("y", 0)),
            "width": raw.get("width"), "opacity": float(raw.get("opacity", 1.0)),
            "fade_in": float(raw.get("fade_in", 0)), "fade_out": float(raw.get("fade_out", 0)),
        })
    return out


def resolve_overlays(overlays: list[dict], close_start: float | None, total: float) -> list[dict]:
    """anchor=close 的换到成片时间轴；补齐 until（视频不给就放完一遍）；超出成片的截掉。"""
    res: list[dict] = []
    for ov in overlays:
        base = 0.0
        if ov["anchor"] == "close":
            if close_start is None:
                raise SystemExit(f"overlay #{ov['n']} anchor=close，但这次没有 close")
            base = close_start
        start = base + ov["start"]
        until = base + ov["until"] if ov["until"] is not None else start + ov["src_dur"]
        if start >= total:
            raise SystemExit(f"overlay #{ov['n']} 开始 {start:.2f}s 超出成片 {total:.2f}s")
        if until > total:
            print(f"  ⚠ overlay #{ov['n']} hold_until {until:.2f}s 超出成片，截到 {total:.2f}s")
            until = total
        span = until - start
        hold = 0.0 if ov["is_image"] else max(0.0, span - ov["src_dur"])
        res.append({**ov, "t0": start, "t1": until, "span": span, "hold": hold})
    return res


def overlay_input_spec(ov: dict) -> list[str]:
    if ov["is_image"]:
        return ["-loop", "1", "-framerate", "60", "-t", f"{ov['span']:.6f}", "-i", str(ov["file"])]
    return ["-i", str(ov["file"])]


def overlay_chain(index: int, ov: dict, k: int, vin: str, vout: str) -> str:
    """把第 index 路输入放到 t0..t1：放完原片后用最后一帧停住（tpad clone），到 t1 撤掉。"""
    f = [f"[{index}:v]fps=60,format=yuva420p"]
    if ov["width"]:
        f.append(f"scale={int(ov['width'])}:-2")
    if ov["hold"] > 0:
        f.append(f"tpad=stop_mode=clone:stop_duration={ov['hold']:.6f}")
    f.append(f"trim=duration={ov['span']:.6f}")
    if ov["fade_in"] > 0:
        f.append(f"fade=t=in:st=0:d={ov['fade_in']:.3f}:alpha=1")
    if ov["fade_out"] > 0:
        f.append(f"fade=t=out:st={max(0.0, ov['span'] - ov['fade_out']):.6f}:d={ov['fade_out']:.3f}:alpha=1")
    if ov["opacity"] < 1:
        f.append(f"colorchannelmixer=aa={ov['opacity']:.3f}")
    f.append(f"setpts=PTS-STARTPTS+{ov['t0']:.6f}/TB")
    src = ",".join(f) + f"[ol{k}]"
    return (
        f"{src};[{vin}][ol{k}]overlay=x={ov['x']}:y={ov['y']}:eof_action=pass:format=auto"
        f":enable='between(t,{ov['t0']:.6f},{ov['t1']:.6f})'[{vout}]"
    )


def timeline(durations: list[float], has_open: bool, has_close: bool) -> tuple[float | None, float]:
    """(close 在成片里的起点, 成片总长)。和 build_filter 的 xfade/concat 偏移同口径。"""
    n = len(durations)
    runs = durations[(1 if has_open else 0) : (n - 1 if has_close else n)]
    acc = (durations[0] - XFADE if has_open else 0.0) + sum(runs)
    if not has_close:
        return None, acc
    close_start = max(0.0, acc - XFADE)
    return close_start, close_start + durations[-1]


def video_codec_args(bitrate: int) -> list[str]:
    # 成片固定 hevc_videotoolbox（Mac）。ASSEMBLE_VCODEC=libx264 只给没有 videotoolbox 的机器跑自测用。
    if os.environ.get("ASSEMBLE_VCODEC") == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-b:v", str(bitrate)]
    return ["-c:v", "hevc_videotoolbox", "-b:v", str(bitrate), "-tag:v", "hvc1"]


def fmt_ts(sec: float) -> str:
    m, x = divmod(sec, 60)
    return f"{int(m)}:{x:05.2f}"


def run(cmd: list[str], dry_run: bool = False) -> None:
    print("$", " ".join(str(part) for part in cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def probe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(raw)


def probe_wh(path: Path) -> tuple[int, int]:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        text=True,
    ).strip()
    w_s, h_s = raw.split(",")
    return int(w_s), int(h_s)


def probe_video_bitrate(path: Path) -> int:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=bit_rate",
            "-show_entries",
            "format=bit_rate",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    data = json.loads(raw)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    bit_rate = int(stream.get("bit_rate") or fmt.get("bit_rate") or 0)
    return bit_rate if bit_rate >= 1_000_000 else 28_000_000


def discover(media_dir: Path) -> tuple[Path | None, list[Path], Path | None]:
    opens = sorted(media_dir.glob("*-open.mp4"))
    # 有高驰截图叠层时优先用 close-stats，原 close 留给重做
    stats_closes = sorted(media_dir.glob("*-close-stats.mp4"))
    closes = sorted(
        p for p in media_dir.glob("*-close.mp4") if "stats" not in p.name
    )
    hud = media_dir / "hud-renders"
    previews = sorted(p for p in hud.glob("*-run-*-hud-preview.mp4")
                      if p.name.endswith("-hud-preview.mp4")
                      and not any(k in p.name for k in ("run-final", "orient", "transpose", "-raw", "-bad")))
    if not previews:
        raise SystemExit(f"No HUD previews in {hud}. Render HUD with --preview first.")
    close = stats_closes[0] if stats_closes else (closes[0] if closes else None)
    return (opens[0] if opens else None, previews, close)


def ensure_whoosh(path: Path) -> Path:
    """合成从左刮到右的短风声，无音调。每次重写，方便改算法。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = 48000
    dur = 0.26
    n = int(sr * dur)
    rng = random.Random(5)
    brown = 0.0
    lp = 0.0
    left_f: list[float] = []
    right_f: list[float] = []
    for i in range(n):
        p = i / n
        env = (p / 0.10) if p < 0.10 else math.exp(-(p - 0.10) / 0.14)
        env = (env**1.05) * 0.38
        white = rng.uniform(-1.0, 1.0)
        brown = 0.985 * brown + 0.015 * white
        x = 0.88 * brown + 0.12 * white
        if p < 0.35:
            cut = 280.0 + 1100.0 * (p / 0.35)
        else:
            cut = 1380.0 - 900.0 * ((p - 0.35) / 0.65)
        alpha = 1.0 - math.exp(-2.0 * math.pi * cut / sr)
        lp = lp + alpha * (x - lp)
        pan = p**0.85
        left_f.append(env * lp * (1.05 - 0.80 * pan))
        right_f.append(env * lp * (0.25 + 0.80 * pan))
    peak = max(max(abs(v) for v in left_f), max(abs(v) for v in right_f)) or 1.0
    gain = 0.20 / peak
    samples = array("h")
    for a, b in zip(left_f, right_f, strict=True):
        samples.append(max(-32767, min(32767, int(a * gain * 32767))))
        samples.append(max(-32767, min(32767, int(b * gain * 32767))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


def wind_chain(src: str, dst: str, duration: float, width: int, height: int, direction: str) -> str:
    """横向一阵风：方向模糊 + 整幅被刮走/刮入。"""
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
        f"color=c=black:s={width}x{height}:d={t}:r=60,setsar=1,settb=1/60[{bg}];"
        f"[{src}]dblur=angle=0:radius=46,setsar=1[{blur}];"
        f"[{bg}][{blur}]overlay=x='{x}':y=0:shortest=1,{fade},fps=60,settb=1/60,format=yuv420p[{dst}]"
    )


def audio_lock_to_video(src: str, dst: str, duration: float) -> str:
    """把一段音频锁到该段视频时长。

    手机素材和 HUD preview 都是视频比音频长几十到一两百毫秒。
    音视频分开 concat 时这段差会逐段累加，片尾唇形能偏出将近一秒。
    片头按原 PTS 补静音（保留 AAC priming），片尾 pad/trim 对齐画面。
    """
    d = f"{duration:.6f}"
    return (
        f"[{src}]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"aresample=async=1:first_pts=0,"
        f"apad=whole_dur={d},atrim=0:{d},asetpts=PTS-STARTPTS[{dst}]"
    )


def mix_whoosh(
    audio_label: str,
    whoosh_index: int,
    delays_ms: list[int],
    volume: float,
    out_label: str = "a",
) -> tuple[str, str]:
    """把 whoosh 叠到主音轨。返回 (filter, output_label)。"""
    n = len(delays_ms)
    if n == 0:
        return f"[{audio_label}]anull[{out_label}]", out_label
    labels = "".join(f"[w{i}]" for i in range(n))
    parts = [f"[{whoosh_index}:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit={n}{labels}"]
    mixed = f"[{audio_label}]"
    for i, delay in enumerate(delays_ms):
        delayed = f"[wd{i}]"
        if delay > 0:
            parts.append(f"[w{i}]adelay=delays={delay}:all=1,volume={volume:.3f}{delayed}")
        else:
            parts.append(f"[w{i}]volume={volume:.3f}{delayed}")
        mixed += delayed
    parts.append(
        f"{mixed}amix=inputs={n + 1}:duration=first:dropout_transition=0:normalize=0[{out_label}]"
    )
    return ";".join(parts), out_label


def build_filter(
    n_inputs: int,
    durations: list[float],
    has_open: bool,
    has_close: bool,
    ass: Path | None,
    fontsdir: Path | None,
    run_transition: str,
    wind: float,
    width: int,
    height: int,
    whoosh_index: int | None,
    whoosh_volume: float,
    loudness_fix: bool = True,
    loudness_af: str | None = None,
    overlays: list[tuple[int, dict]] | None = None,
    audio_only: bool = False,
) -> str:
    """audio_only=True 只出 [a]（两遍 loudnorm 的测量遍用，不解码视频）。loudness_af 覆盖默认响度链。"""
    parts: list[str] = []

    def vp(x: str) -> None:  # 视频滤镜；audio_only 时不进图
        if not audio_only:
            parts.append(x)

    for i in range(n_inputs):
        vp(f"[{i}:v]fps=60,settb=1/60,format=yuv420p,setsar=1[v{i}]")
        parts.append(audio_lock_to_video(f"{i}:a", f"a{i}", durations[i]))

    run_start = 1 if has_open else 0
    run_end = n_inputs - 1 if has_close else n_inputs
    first_run = run_start
    last_run = run_end - 1
    run_indices = list(range(first_run, last_run + 1))
    do_wind = run_transition in {"wind", "spin"} and wind > 0.03

    processed: list[tuple[str, str]] = []
    whoosh_delays: list[int] = []
    for j, idx in enumerate(run_indices):
        d = durations[idx]
        a_label = f"a{idx}"
        is_first = j == 0
        is_last = j == len(run_indices) - 1
        can_wind = do_wind and d > wind * 2 + 0.05
        if len(run_indices) < 2 or not can_wind:
            processed.append((f"v{idx}", a_label))
            continue
        tag = f"r{j}"
        want_in = not is_first
        want_out = not is_last
        if want_in and want_out:
            vp(f"[v{idx}]split=3[{tag}h][{tag}m][{tag}t]")
            vp(f"[{tag}h]trim=duration={wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}hr]")
            vp(
                f"[{tag}m]trim=start={wind:.6f}:end={d - wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}body]"
            )
            vp(f"[{tag}t]trim=start={d - wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}tr]")
            vp(wind_chain(f"{tag}hr", f"{tag}hi", wind, width, height, "in"))
            vp(wind_chain(f"{tag}tr", f"{tag}to", wind, width, height, "out"))
            vp(f"[{tag}hi][{tag}body][{tag}to]concat=n=3:v=1:a=0,fps=60,settb=1/60[{tag}p]")
        elif want_out:
            vp(f"[v{idx}]split=2[{tag}m][{tag}t]")
            vp(f"[{tag}m]trim=duration={d - wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}body]")
            vp(f"[{tag}t]trim=start={d - wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}tr]")
            vp(wind_chain(f"{tag}tr", f"{tag}to", wind, width, height, "out"))
            vp(f"[{tag}body][{tag}to]concat=n=2:v=1:a=0,fps=60,settb=1/60[{tag}p]")
        else:
            vp(f"[v{idx}]split=2[{tag}h][{tag}m]")
            vp(f"[{tag}h]trim=duration={wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}hr]")
            vp(f"[{tag}m]trim=start={wind:.6f},setpts=PTS-STARTPTS,settb=1/60[{tag}body]")
            vp(wind_chain(f"{tag}hr", f"{tag}hi", wind, width, height, "in"))
            vp(f"[{tag}hi][{tag}body]concat=n=2:v=1:a=0,fps=60,settb=1/60[{tag}p]")
        processed.append((f"{tag}p", a_label))

    v0, a0 = processed[0]
    if has_open:
        offset = max(0.0, durations[0] - XFADE)
        vcur, acur = "vx0", "ax0"
        vp(
            f"[{v0}]fps=60,settb=1/60[{v0}f];"
            f"[v0][{v0}f]xfade=transition=fade:duration={XFADE}:offset={offset:.6f},settb=1/60[{vcur}]"
        )
        parts.append(f"[a0][{a0}]acrossfade=d={XFADE}[{acur}]")
        acc = durations[0] + durations[first_run] - XFADE
    else:
        vcur, acur = v0, a0
        acc = durations[first_run]

    for step, idx in enumerate(run_indices[1:], start=1):
        nv, na = f"vc{step}", f"ac{step}"
        pv, pa = processed[step]
        if do_wind:
            whoosh_delays.append(max(0, int(round((acc - wind) * 1000))))
        vp(f"[{vcur}][{pv}]concat=n=2:v=1:a=0,fps=60,settb=1/60[{nv}]")
        parts.append(f"[{acur}][{pa}]concat=n=2:v=0:a=1[{na}]")
        vcur, acur = nv, na
        acc += durations[idx]

    if has_close:
        close_i = n_inputs - 1
        offset = max(0.0, acc - XFADE)
        vp(f"[{vcur}]fps=60,settb=1/60[vpre]")
        vp(f"[v{close_i}]fps=60,settb=1/60[vcls]")
        vp(f"[vpre][vcls]xfade=transition=fade:duration={XFADE}:offset={offset:.6f}[vxf]")
        parts.append(f"[{acur}][a{close_i}]acrossfade=d={XFADE}[a0x]")
        vout = "vxf"
        a_pre = "a0x"
    else:
        vout = vcur
        a_pre = acur

    if whoosh_index is not None and whoosh_delays:
        mix, _aout = mix_whoosh(a_pre, whoosh_index, whoosh_delays, whoosh_volume, out_label="am")
        parts.append(mix)
    else:
        parts.append(f"[{a_pre}]anull[am]")

    # whoosh 叠完后再 leveling+loudnorm，避免 SFX 被单独猛推，同时 TP 仍由 loudnorm 卡住。
    if loudness_fix:
        parts.append(f"[am]{loudness_af or LOUDNESS_AF}[a]")
    else:
        parts.append(f"[am]anull[a]")

    if audio_only:
        return ";".join(parts)

    for k, (index, ov) in enumerate(overlays or []):
        nxt = f"vov{k}"
        vp(overlay_chain(index, ov, k, vout, nxt))
        vout = nxt

    if ass is not None:
        ass_path = str(ass).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        fonts = ""
        if fontsdir is not None:
            fonts_esc = str(fontsdir).replace(":", "\\:")
            fonts = f":fontsdir={fonts_esc}"
        vp(f"[{vout}]subtitles={ass_path}{fonts}:charenc=UTF-8[v]")
    else:
        vp(f"[{vout}]format=yuv420p[v]")

    return ";".join(parts)


def encode_cmd(
    inputs: list[Path] | list[list[str]],
    filt: str,
    out: Path,
    bitrate: int,
) -> list[str]:
    cmd = ["ffmpeg", "-y", "-hide_banner"]
    for spec in inputs:
        cmd.extend(spec if isinstance(spec, list) else ["-i", str(spec)])
    cmd.extend(
        [
            "-filter_complex",
            filt,
            "-map",
            "[v]",
            "-map",
            "[a]",
            *video_codec_args(bitrate),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    return cmd


def render_join_previews(
    runs: list[Path],
    out_dir: Path,
    wind: float,
    whoosh: Path | None,
    whoosh_volume: float,
    dry_run: bool,
) -> None:
    """只渲 run 接缝前后约 0.9s，方便听风声、看刮过。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pad = 0.90
    w, h = probe_wh(runs[0])
    for i, (left, right) in enumerate(zip(runs, runs[1:], strict=False)):
        left_dur = probe_duration(left)
        start = max(0.0, left_dur - pad - wind)
        seg = pad + wind
        delay_ms = int(round(pad * 1000))
        out = (
            out_dir
            / f"join-{left.stem.split('run-')[-1].split('-hud')[0]}-{right.stem.split('run-')[-1].split('-hud')[0]}.mp4"
        )
        inputs = [left, right]
        whoosh_idx: int | None = None
        if whoosh is not None:
            inputs.append(whoosh)
            whoosh_idx = 2
        filt = (
            f"[0:v]fps=60,settb=1/60,format=yuv420p,setsar=1,split=2[a0][a1];"
            f"[a0]trim=duration={pad:.6f},setpts=PTS-STARTPTS,settb=1/60[abody];"
            f"[a1]trim=start={pad:.6f},setpts=PTS-STARTPTS,settb=1/60[atail];"
            f"[1:v]fps=60,settb=1/60,format=yuv420p,setsar=1,split=2[b0][b1];"
            f"[b0]trim=duration={wind:.6f},setpts=PTS-STARTPTS,settb=1/60[bhead];"
            f"[b1]trim=start={wind:.6f},setpts=PTS-STARTPTS,settb=1/60[brest];"
            f"{wind_chain('atail', 'tail', wind, w, h, 'out')};"
            f"{wind_chain('bhead', 'head', wind, w, h, 'in')};"
            f"[abody][tail][head][brest]concat=n=4:v=1:a=0,settb=1/60[v];"
            f"[0:a][1:a]concat=n=2:v=0:a=1[ac]"
        )
        if whoosh_idx is not None:
            mix, _ = mix_whoosh("ac", whoosh_idx, [delay_ms], whoosh_volume)
            filt = f"{filt};{mix}"
        else:
            filt = f"{filt};[ac]anull[a]"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{seg:.6f}",
            "-i",
            str(left),
            "-t",
            f"{seg:.6f}",
            "-i",
            str(right),
        ]
        if whoosh is not None:
            cmd.extend(["-i", str(whoosh)])
        cmd.extend(
            [
                "-filter_complex",
                filt,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "hevc_videotoolbox",
                "-b:v",
                "12000000",
                "-tag:v",
                "hvc1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(out),
            ]
        )
        print(f"Join preview {i + 1}/{len(runs) - 1}: {out.name}")
        run(cmd, dry_run=dry_run)
        if not dry_run:
            print(subprocess.check_output(["ls", "-lh", str(out)], text=True).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble open + HUD run clips + close into one episode video.")
    parser.add_argument("--media-dir", required=True, help="Directory with open/run/close mp4 and hud-renders/")
    parser.add_argument("--close", help="Override close clip. Default: media-dir/*-close.mp4")
    parser.add_argument(
        "--ass",
        help="Burn ASS into the video. Omit by default; upload SRT as sidecar instead.",
    )
    parser.add_argument("--out", help="Output mp4. Default: <media-dir>/<date>-run-final.mp4")
    parser.add_argument(
        "--run-transition",
        choices=("wind", "cut", "spin"),
        default="wind",
        help="run-a/b/c join: wind gust (default) or hard cut",
    )
    parser.add_argument(
        "--wind",
        "--spin",
        type=float,
        default=WIND_DEFAULT,
        help="Wind-out / wind-in duration in seconds (default 0.08)",
    )
    parser.add_argument("--no-whoosh", action="store_true")
    parser.add_argument("--whoosh-volume", type=float, default=0.85)
    parser.add_argument(
        "--no-loudness-fix",
        action="store_true",
        help="Skip post-mix dynaudnorm+loudnorm (default ON: I=-16 LUFS, TP=-1.5 dBTP)",
    )
    parser.add_argument(
        "--preview-joins",
        action="store_true",
        help="Only render short run-run join previews into media-dir/qc/",
    )
    parser.add_argument(
        "--single-pass-loudnorm",
        action="store_true",
        help="响度链只跑单遍（默认两遍：先测量再 linear=true 套用；测量失败自动退回单遍）",
    )
    parser.add_argument(
        "--overlays",
        help="叠加层配置 JSON。默认找 <media-dir>/overlays.json，再找 episodes/<媒体目录名>/overlays.json",
    )
    parser.add_argument("--no-overlays", action="store_true", help="有 overlays.json 也不叠")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    media_dir = Path(args.media_dir).expanduser().resolve()
    open_clip, runs, close_clip = discover(media_dir)
    if args.close:
        close_clip = Path(args.close).expanduser().resolve()
        if not close_clip.is_file():
            raise SystemExit(f"close clip not found: {close_clip}")
    transition = "wind" if args.run_transition == "spin" else args.run_transition
    whoosh: Path | None = None
    if transition == "wind" and not args.no_whoosh:
        whoosh = ensure_whoosh(WHOOSH_PATH)

    if args.preview_joins:
        if len(runs) < 2:
            raise SystemExit("Need at least two run previews for --preview-joins.")
        render_join_previews(
            runs,
            media_dir / "qc",
            wind=args.wind,
            whoosh=whoosh,
            whoosh_volume=args.whoosh_volume,
            dry_run=args.dry_run,
        )
        return 0

    inputs: list[Path] = []
    if open_clip:
        inputs.append(open_clip)
    inputs.extend(runs)
    if close_clip:
        inputs.append(close_clip)

    durations = [probe_duration(path) for path in inputs]
    width, height = probe_wh(runs[0])
    bitrate = probe_video_bitrate(runs[0])
    print(f"Open: {open_clip}")
    print(f"Runs: {', '.join(p.name for p in runs)}")
    print(f"Close: {close_clip}")
    print("Durations:", " ".join(f"{d:.3f}s" for d in durations))
    loudness_fix = not args.no_loudness_fix
    print(f"Run transition: {transition} wind={args.wind:.3f}s whoosh={whoosh}")
    print(f"Loudness fix: {'ON ' + LOUDNESS_AF if loudness_fix else 'OFF'}")

    date_prefix = runs[0].name[:10]
    out = Path(args.out).expanduser().resolve() if args.out else media_dir / f"{date_prefix}-run-final.mp4"

    ass = Path(args.ass).expanduser().resolve() if args.ass else None
    fontsdir = None
    if ass is not None:
        if not ass.exists():
            raise SystemExit(f"ASS not found: {ass}")
        fontsdir = Path("/tmp/running-ass-fonts")
        fontsdir.mkdir(parents=True, exist_ok=True)
        if FONT_SRC.exists():
            shutil.copyfile(FONT_SRC, fontsdir / FONT_SRC.name)

    ffmpeg_inputs: list[list[str]] = [["-i", str(p)] for p in inputs]
    whoosh_index = None
    if whoosh is not None and transition == "wind":
        ffmpeg_inputs.append(["-i", str(whoosh)])
        whoosh_index = len(inputs)

    close_start, total = timeline(durations, open_clip is not None, close_clip is not None)
    ov_specs: list[tuple[int, dict]] = []
    ov_file = None if args.no_overlays else find_overlays_file(media_dir, args.overlays)
    if ov_file is not None:
        resolved = resolve_overlays(load_overlays(ov_file, media_dir), close_start, total)
        print(f"Overlays: {ov_file}")
        for ov in resolved:
            print(
                f"  #{ov['n']} {ov['file'].name}  {fmt_ts(ov['t0'])} → {fmt_ts(ov['t1'])}"
                f"（停住 {ov['hold']:.1f}s）  x={ov['x']} y={ov['y']}"
            )
            ov_specs.append((len(ffmpeg_inputs), ov))
            ffmpeg_inputs.append(overlay_input_spec(ov))
    else:
        print("Overlays: none")

    common = dict(
        n_inputs=len(inputs),
        durations=durations,
        has_open=open_clip is not None,
        has_close=close_clip is not None,
        run_transition=transition,
        wind=args.wind,
        width=width,
        height=height,
        whoosh_index=whoosh_index,
        whoosh_volume=args.whoosh_volume,
        loudness_fix=loudness_fix,
    )

    loudness_af = None
    if loudness_fix and not args.single_pass_loudnorm:
        if args.dry_run:
            print("Loudnorm: two-pass（dry-run 不测量；正式跑先只解码音频测一遍）")
        else:
            audio_filt = build_filter(**common, ass=None, fontsdir=None, loudness_af=LOUDNESS_MEASURE_AF,
                                      audio_only=True)
            measured = measure_loudness(ffmpeg_inputs[: len(inputs) + (1 if whoosh_index is not None else 0)],
                                        audio_filt)
            if measured is None:
                print("⚠ Loudnorm 测量失败，退回单遍响度链")
            else:
                loudness_af = loudness_af_two_pass(measured)
                print(
                    f"Loudnorm pass 1（链内 loudnorm 之前）: I={measured['input_i']} LUFS  "
                    f"TP={measured['input_tp']} dBTP  LRA={measured['input_lra']}  "
                    f"thresh={measured['input_thresh']}  offset={measured['target_offset']}"
                )
                print(f"Loudnorm pass 2: {loudness_af}")

    filt = build_filter(**common, ass=ass, fontsdir=fontsdir, loudness_af=loudness_af, overlays=ov_specs)

    cmd = encode_cmd(ffmpeg_inputs, filt, out, bitrate)
    run(cmd, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Wrote {out}")
        ls = subprocess.check_output(["ls", "-lh", str(out)], text=True).strip()
        print(ls)
        if loudness_fix:
            got = measure_output(out)
            if got is None:
                print("⚠ 成片响度实测失败，手动跑 SKILL 里的 loudnorm summary")
            else:
                tp = float(got["input_tp"])
                flag = "OK" if tp <= -1.0 else "⚠ 超过 -1.0 dBTP，查局部"
                print(f"成片实测: I={got['input_i']} LUFS  TP={got['input_tp']} dBTP  LRA={got['input_lra']}  {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
