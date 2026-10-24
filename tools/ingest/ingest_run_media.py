#!/usr/bin/env python3
"""把手机未重命名导出收进素材目录，按拍摄时间改成 open / run-* / close。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
VID_RE = re.compile(r"VID_(\d{8})_(\d{6})", re.IGNORECASE)
FIT_TS_RE = re.compile(r"(20\d{12})")
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
SKIP_NAME_PARTS = ("-hud-", "hud-preview", "run-final", "cover-", "-raw", "trimtmp")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
STATS_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-stats-\d+$")
STATS_HINTS = ("screenshot", "coros", "截图")


def run_ffprobe_duration(path: Path) -> float | None:
    try:
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
    except (subprocess.CalledProcessError, ValueError):
        return None


def parse_vid_start(name: str) -> datetime | None:
    match = VID_RE.search(name)
    if not match:
        return None
    return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)


def parse_fit_start(name: str) -> datetime | None:
    match = FIT_TS_RE.search(name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)


def file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=SHANGHAI)


# ---------- FIT 按时间窗挑 ----------

FIT_GUESS_SPAN = timedelta(hours=3)  # 读不到 record 时，从文件名开始时间往后估这么长
CLOSE_AFTER_FIT_SLACK = timedelta(seconds=60)


def fit_window(path: Path) -> tuple[datetime | None, datetime | None, str]:
    """FIT 的 (开始, 结束, 来源)。优先读 record 时间戳（要 fitdecode，仓库 .venv 有），否则用文件名里的开始时间。"""
    try:
        import fitdecode  # type: ignore
    except ImportError:
        fitdecode = None
    if fitdecode is not None:
        try:
            tmin = tmax = None
            with fitdecode.FitReader(path) as reader:
                for frame in reader:
                    if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                        continue
                    ts = next((f.value for f in frame.fields if f.name == "timestamp"), None)
                    if ts is None:
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=ZoneInfo("UTC"))
                    tmin = ts if tmin is None or ts < tmin else tmin
                    tmax = ts if tmax is None or ts > tmax else tmax
            if tmin is not None:
                return tmin.astimezone(SHANGHAI), tmax.astimezone(SHANGHAI), "records"
        except Exception as exc:  # noqa: BLE001 坏 FIT 不该让整个 ingest 崩
            print(f"  FIT {path.name}: 读 record 失败（{exc}），退回文件名时间")
    start = parse_fit_start(path.name)
    return (start, None, "filename") if start else (None, None, "unknown")


def video_window(path: Path, duration: float | None) -> tuple[datetime, datetime]:
    """视频 (开始, 结束)：VID_ 文件名是开始时间；没有就把 mtime 当结束时间往前推时长（和 HUD 对齐同口径）。"""
    dur = timedelta(seconds=duration or 0)
    start = parse_vid_start(path.name)
    if start is not None:
        return start, start + dur
    end = file_mtime(path)
    return end - dur, end


def overlap_s(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


def pick_fit(fits: list[Path], windows: list[tuple[datetime, datetime]], explicit: str | None = None) -> tuple[Path | None, list[dict]]:
    """按和视频时间窗的重叠挑 FIT。多场都重叠、或都不重叠时停下列候选，让人用 --fit 指定。"""
    report: list[dict] = []
    for f in fits:
        start, end, src = fit_window(f)
        eff_end = end or (start + FIT_GUESS_SPAN if start else None)
        ov = sum(overlap_s(a, b, start, eff_end) for a, b in windows) if start and eff_end else 0.0
        report.append({"path": f, "start": start, "end": end, "source": src, "overlap_s": round(ov, 1)})
    for r in report:
        st = r["start"].strftime("%Y-%m-%d %H:%M:%S") if r["start"] else "?"
        en = r["end"].strftime("%H:%M:%S") if r["end"] else ("估" if r["start"] else "?")
        print(f"  FIT {r['path'].name}  {st} → {en}（{r['source']}）  和视频重叠 {r['overlap_s']:.0f}s")
    if explicit:
        hit = [r for r in report if r["path"].name == explicit or str(r["path"]) == explicit]
        if not hit:
            raise SystemExit(f"--fit {explicit} 不在源目录的 FIT 里：{[f.name for f in fits]}")
        return hit[0]["path"], report
    if not fits:
        return None, report
    if len(fits) == 1:
        if report[0]["overlap_s"] == 0:
            print("  ⚠ 唯一的 FIT 和视频时间窗不重叠（时区 / 拿错场？），先核对再 --apply")
        return fits[0], report
    ranked = sorted((r for r in report if r["overlap_s"] > 0), key=lambda r: r["overlap_s"], reverse=True)
    names = "、".join(r["path"].name for r in report)
    if not ranked:
        raise SystemExit(f"多个 FIT 都和视频时间窗不重叠：{names}。核对后用 --fit <文件名> 指定。")
    if len(ranked) > 1 and ranked[1]["overlap_s"] >= 0.5 * ranked[0]["overlap_s"]:
        raise SystemExit("多个 FIT 都和视频重叠，分不出是哪一场：" +
                         "、".join(f"{r['path'].name}（{r['overlap_s']:.0f}s）" for r in ranked) +
                         "。用 --fit <文件名> 指定。")
    print(f"  → 选 {ranked[0]['path'].name}（重叠最多）")
    return ranked[0]["path"], report


def count_trailing_closes(ordered: list[Path], durations: dict[Path, float | None], fit_end: datetime | None,
                          min_runs: int = 1) -> int:
    """FIT 结束之后才开拍的尾部片段都是跑后口播（close）。至少留 min_runs 段当 run。"""
    if fit_end is None:
        return 1
    n = 0
    for p in reversed(ordered):
        if video_window(p, durations.get(p))[0] >= fit_end - CLOSE_AFTER_FIT_SLACK:
            n += 1
        else:
            break
    return max(1, min(n, len(ordered) - min_runs))


def discover_videos(src: Path) -> list[Path]:
    videos: list[Path] = []
    for path in sorted(src.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
            continue
        name = path.name.lower()
        if any(part in name for part in SKIP_NAME_PARTS):
            continue
        if path.name.startswith("."):
            continue
        videos.append(path)
    return videos


def discover_fits(src: Path) -> list[Path]:
    return sorted(path for path in src.iterdir() if path.is_file() and path.suffix.lower() == ".fit")


def discover_raw_stats(src: Path) -> list[Path]:
    """高驰 App 截图：Screenshot_* / *coros* / 截图*。已命名的 stats-NN 不重复收。"""
    found: list[Path] = []
    for path in sorted(src.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXT:
            continue
        if STATS_STEM_RE.match(path.stem):
            continue
        name = path.name.lower()
        if name.startswith("cover-") or any(part in name for part in SKIP_NAME_PARTS):
            continue
        if any(hint in name for hint in STATS_HINTS):
            found.append(path)
    return found


def sort_key(path: Path) -> datetime:
    parsed = parse_vid_start(path.name)
    return parsed if parsed is not None else file_mtime(path)


def already_named(path: Path) -> str | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}-(open|close(?:-\d+)?|run-[a-z]|broll-\d+)$", path.stem)
    return match.group(1) if match else None


def propose_roles(videos: list[Path], no_open: bool, no_close: bool, n_close: int = 1) -> list[tuple[Path, str]]:
    ordered = sorted(videos, key=sort_key)
    named: list[tuple[Path, str]] = []
    leftover: list[Path] = []
    for path in ordered:
        role = already_named(path)
        if role:
            named.append((path, role))
        else:
            leftover.append(path)

    if not leftover:
        return named

    roles: list[str] = []
    n = len(leftover)
    n_close = 0 if no_close else max(1, n_close)
    if n_close > 1:
        if n < n_close + (0 if no_open else 1) + 1:
            raise SystemExit(f"{n} 段视频不够分：要 {n_close} 段 close + {'0' if no_open else '1'} 段 open + 至少 1 段 run")
        head = [] if no_open else ["open"]
        runs = [f"run-{chr(ord('a') + i)}" for i in range(n - len(head) - n_close)]
        roles = head + runs + [f"close-{i}" for i in range(1, n_close + 1)]
    elif n == 1:
        roles = ["run-a"]
    elif n == 2:
        if no_open and no_close:
            roles = ["run-a", "run-b"]
        elif no_open:
            roles = ["run-a", "close"]
        elif no_close:
            roles = ["open", "run-a"]
        else:
            # 两段时默认跑前 + 跑中；不要猜成没有 run 的 open+close
            print("Two clips: proposing open + run-a. Override with --no-open / --no-close if needed.")
            roles = ["open", "run-a"]
    else:
        start = 0
        end = n
        if not no_open:
            roles.append("open")
            start = 1
        if not no_close:
            end = n - 1
        run_idx = 0
        for _ in range(start, end):
            roles.append(f"run-{chr(ord('a') + run_idx)}")
            run_idx += 1
        if not no_close:
            roles.append("close")

    if len(roles) != len(leftover):
        raise SystemExit(f"Role count {len(roles)} != video count {len(leftover)}")
    return named + list(zip(leftover, roles, strict=True))


def stream_sig(path: Path) -> str:
    """能不能无损 concat：视频编码/宽高/帧率 + 音频编码/采样率/声道 都一样才行。"""
    try:
        return subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
             "-of", "compact=p=0", str(path)], text=True).strip()
    except subprocess.CalledProcessError:
        return f"?{path}"


def pick_video_encoder() -> list[str]:
    try:
        enc = subprocess.check_output(["ffmpeg", "-hide_banner", "-encoders"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        enc = ""
    if "hevc_videotoolbox" in enc:
        return ["-c:v", "hevc_videotoolbox", "-q:v", "65", "-tag:v", "hvc1"]
    return ["-c:v", "libx264", "-crf", "16", "-preset", "medium"]


def join_clips(parts: list[Path], dest: Path, dry_run: bool) -> str:
    """几段跑后口播拼成一条 close。参数一致就 -c copy 无损拼；不一致才重编码。mtime 取最后一段（结束时间）。"""
    sigs = {stream_sig(p) for p in parts}
    mode = "copy" if len(sigs) == 1 else "reencode"
    print(f"join {' + '.join(p.name for p in parts)} -> {dest.name}（{mode}）")
    if dry_run:
        return mode
    if mode == "copy":
        lst = dest.with_suffix(".concat.txt")
        lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
               "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(dest)]
    else:
        lst = None
        ins: list[str] = []
        for p in parts:
            ins += ["-i", str(p)]
        w, h = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", str(parts[0])], text=True).strip().split(",")[:2]
        chains = "".join(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps=60[v{i}];[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}];"
            for i in range(len(parts)))
        concat = "".join(f"[v{i}][a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=1[v][a]"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *ins, "-filter_complex", chains + concat,
               "-map", "[v]", "-map", "[a]", *pick_video_encoder(), "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)]
    try:
        subprocess.run(cmd, check=True)
    finally:
        if lst is not None:
            lst.unlink(missing_ok=True)
    ts = parts[-1].stat().st_mtime
    os.utime(dest, (ts, ts))
    return mode


def dest_name(date: str, role: str, suffix: str) -> str:
    return f"{date}-{role}{suffix}"


def copy_or_move(src: Path, dest: Path, move: bool, dry_run: bool) -> None:
    if src.resolve() == dest.resolve():
        return
    # 已经在目标目录里的文件只改名，不复制出第二份
    same_dir = src.parent.resolve() == dest.parent.resolve()
    action = "mv" if move or same_dir else "cp"
    print(f"{action} {src} -> {dest}")
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if action == "mv":
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)


def maybe_fix_mtime(path: Path, start: datetime | None, duration: float | None, dry_run: bool) -> str:
    if start is None or duration is None:
        return "mtime unchanged (no VID_ start or duration)"
    end = start + timedelta(seconds=duration)
    current = file_mtime(path)
    delta = abs((current - end).total_seconds())
    if delta <= 300:
        return f"mtime ok ({current.isoformat(timespec='seconds')})"
    msg = f"mtime {current.isoformat(timespec='seconds')} -> {end.isoformat(timespec='seconds')} (VID_ start + duration)"
    print(msg)
    if not dry_run:
        ts = end.timestamp()
        os.utime(path, (ts, ts))
    return msg


def display_media_dir(media_dir: Path) -> str:
    """assets.md 里写成 ~/Movies/...，不要展开成 /Users/...。"""
    resolved = media_dir.expanduser().resolve()
    home_media = (Path.home() / "Movies/running-content").resolve()
    try:
        rel = resolved.relative_to(home_media)
    except ValueError:
        return str(resolved)
    return f"~/Movies/running-content/{rel}/"


def write_assets_md(
    dest: Path,
    media_dir: Path,
    date: str,
    slug: str,
    rows: list[dict],
    fits: list[tuple[str, str]],
) -> None:
    lines = [
        f"# {date} {slug} 素材索引",
        "",
        "## 本地素材目录",
        "",
        f"`{display_media_dir(media_dir)}`",
        "",
        "## 重命名结果",
        "",
        "### 视频素材",
        "",
    ]
    for row in rows:
        lines.append(f"- `{row['src']}` -> `{row['dest']}`")
    lines.extend(["", "### 跑步数据", ""])
    if fits:
        for src, dest_name_ in fits:
            lines.append(f"- `{src}` -> `{dest_name_}`")
    else:
        lines.append("- （未发现 FIT）")
    lines.extend(["", "## 时间顺序依据", ""])
    for row in rows:
        lines.append(f"- {row['start']}: `{row['role']}`")
    lines.extend(["", "## 素材关联", ""])
    for row in rows:
        lines.append(f"- `{row['role']}`：`{row['dest']}`")
    for _, dest_name_ in fits:
        lines.append(f"- FIT：`{dest_name_}`")
    old = dest.read_text(encoding="utf-8") if dest.is_file() else ""
    if "## 制作状态" in old:
        # 重跑 ingest 只更新素材部分；制作状态和之后人写的记录原样保留，只把 ingest 置 done
        tail = "## 制作状态" + old.split("## 制作状态", 1)[1]
        tail = re.sub(r"^- ingest:.*$", "- ingest: done", tail, count=1, flags=re.M)
        if "- ingest:" not in tail:
            tail = tail.replace("## 制作状态\n", "## 制作状态\n\n- ingest: done", 1)
        lines.extend(["", tail.rstrip("\n"), ""])
    else:
        lines.extend(["", "## 制作状态", "", "- ingest: done"]
                     + [f"- {k}: pending" for k in ("shoes", "hud", "cover", "assemble", "qc", "subs", "upload")] + [""])
    dest.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest phone exports into a named running-content folder.")
    parser.add_argument("--src", required=True, help="Folder of unrenamed phone exports")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--media-root",
        default=str(Path.home() / "Movies" / "running-content"),
        help="Parent of YYYY-MM-DD-slug",
    )
    parser.add_argument("--episode-dir", help="Write assets.md here (repo episodes/...)")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-close", action="store_true")
    parser.add_argument("--fit", help="源目录里有多个 FIT 且自动挑不出时，指定文件名")
    parser.add_argument("--close-clips", type=int,
                        help="最后几段是跑后口播 close（默认：有 FIT 时按「FIT 结束后才开拍」自动数，否则 1）。>1 时自动拼成一条 close")
    parser.add_argument("--move", action="store_true", help="Move instead of copy")
    parser.add_argument("--apply", action="store_true", help="Actually copy/rename. Default is dry-run")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--skip-pause-trim",
        action="store_true",
        help="Do not trim long pauses in open/close",
    )
    args = parser.parse_args()

    src = Path(args.src).expanduser().resolve()
    if not src.is_dir():
        raise SystemExit(f"Source is not a directory: {src}")
    date = args.date
    slug = args.slug
    media_dir = Path(args.media_root).expanduser().resolve() / f"{date}-{slug}"
    dry_run = not args.apply

    videos = discover_videos(src)
    fits = discover_fits(src)
    if not videos:
        raise SystemExit(f"No videos in {src}")

    print(f"Media dir: {media_dir}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    durations = {p: run_ffprobe_duration(p) for p in videos}
    windows = [video_window(p, durations[p]) for p in videos]
    primary_fit, fit_report = pick_fit(fits, windows, args.fit)
    fit_end = next((r["end"] for r in fit_report if r["path"] == primary_fit and r["source"] == "records"), None)

    if args.close_clips is not None:
        n_close = args.close_clips
    elif args.no_close:
        n_close = 0
    else:
        unnamed = sorted((p for p in videos if not already_named(p)), key=sort_key)
        n_close = count_trailing_closes(unnamed, durations, fit_end, min_runs=1 + (0 if args.no_open else 1))
        if n_close > 1:
            print(f"FIT 结束后还有 {n_close} 段：都当跑后口播，拼成一条 close（不对就 --close-clips 1）")
    mapping = propose_roles(videos, no_open=args.no_open, no_close=args.no_close, n_close=n_close)
    rows: list[dict] = []
    close_parts: list[tuple[int, Path, int]] = []
    for path, role in mapping:
        start = parse_vid_start(path.name) or file_mtime(path)
        duration = durations.get(path)
        dest = media_dir / dest_name(date, role, path.suffix.lower())
        exists = dest.exists() and dest.resolve() != path.resolve()
        print(f"  {path.name}  {start.strftime('%H:%M:%S')}  {duration or '?'}s  -> {dest.name}  [{role}]")
        if exists and not args.force:
            raise SystemExit(f"Refusing to overwrite {dest} (pass --force)")
        copy_or_move(path, dest, move=args.move, dry_run=dry_run)
        target = dest if (args.apply or dest.exists()) else path
        if re.fullmatch(r"close-\d+", role):
            close_parts.append((int(role.rsplit("-", 1)[1]), target, len(rows)))
        mtime_note = maybe_fix_mtime(
            target if args.apply else path,
            parse_vid_start(path.name),
            duration,
            dry_run,
        )
        rows.append(
            {
                "src": path.name,
                "dest": dest.name,
                "role": role,
                "start": start.strftime("%H:%M:%S"),
                "mtime": mtime_note,
            }
        )

    if len(close_parts) > 1:
        close_parts.sort()
        parts = [t for _, t, _ in close_parts]
        joined = media_dir / f"{date}-close.mp4"
        if joined.exists() and not args.force:
            raise SystemExit(f"Refusing to overwrite {joined} (pass --force)")
        mode = join_clips(parts, joined, dry_run)
        rows.append({"src": " + ".join(rows[i]["dest"] for _, _, i in close_parts), "dest": joined.name,
                     "role": "close", "start": rows[close_parts[0][2]]["start"],
                     "mtime": f"拼接（{mode}），mtime=最后一段"})

    fit_pairs: list[tuple[str, str]] = []
    if primary_fit is not None:
        dest_fit = media_dir / f"{date}-run-data.fit"
        copy_or_move(primary_fit, dest_fit, move=args.move, dry_run=dry_run)
        fit_pairs.append((primary_fit.name, dest_fit.name))

    for i, path in enumerate(discover_raw_stats(src), start=1):
        dest_stat = media_dir / f"{date}-stats-{i:02d}{path.suffix.lower()}"
        print(f"  STAT {path.name} -> {dest_stat.name}")
        copy_or_move(path, dest_stat, move=args.move, dry_run=dry_run)

    payload = {
        "media_dir": str(media_dir),
        "date": date,
        "slug": slug,
        "rows": rows,
        "fits": [{"src": a, "dest": b} for a, b in fit_pairs],
        "dry_run": dry_run,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.episode_dir:
        assets = Path(args.episode_dir).expanduser().resolve() / "assets.md"
        print(f"assets.md -> {assets}")
        if not dry_run:
            assets.parent.mkdir(parents=True, exist_ok=True)
            write_assets_md(assets, media_dir, date, slug, rows, fit_pairs)

    if not dry_run:
        if args.skip_pause_trim:
            print("skip open/close pause trim")
        else:
            trim_script = Path(__file__).resolve().parent / "trim_talk_pauses.py"
            print("open/close pause trim")
            rc = subprocess.run(
                [
                    sys.executable,
                    str(trim_script),
                    "--media-dir",
                    str(media_dir),
                    "--apply",
                ],
                check=False,
            ).returncode
            if rc:
                print(f"open/close 粗剪失败（exit {rc}）：素材已收，但粗剪没做。修好后单独跑 trim_talk_pauses.py --apply，或用 --skip-pause-trim。", file=sys.stderr)
                return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
