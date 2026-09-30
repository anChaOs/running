#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def parse_ffprobe_creation_time(path: Path) -> datetime | None:
    raw = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format_tags=creation_time:stream_tags=creation_time",
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(raw)
    candidates: list[str] = []
    format_tags = data.get("format", {}).get("tags", {})
    if "creation_time" in format_tags:
        candidates.append(format_tags["creation_time"])
    for stream in data.get("streams", []):
        tags = stream.get("tags", {})
        if "creation_time" in tags:
            candidates.append(tags["creation_time"])
    for value in candidates:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def parse_duration_seconds(path: Path) -> float:
    raw = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    ).strip()
    return float(raw)


def iso_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def local_or_none(dt: datetime | None, tz: timezone) -> str | None:
    return dt.astimezone(tz).isoformat() if dt else None


@dataclass
class ProbeResult:
    file: str
    duration_seconds: float
    stat_birth_utc: str | None
    stat_changed_utc: str | None
    stat_modified_utc: str | None
    ffprobe_creation_time_utc: str | None
    inferred_start_from_stat_birth_utc: str | None
    inferred_start_from_stat_changed_utc: str | None
    inferred_start_from_stat_modified_utc: str | None
    inferred_start_from_ffprobe_creation_utc: str | None


def probe(path: Path, tz: timezone) -> ProbeResult:
    stat = path.stat()
    duration_seconds = parse_duration_seconds(path)
    duration = timedelta(seconds=duration_seconds)
    birth = datetime.fromtimestamp(stat.st_birthtime, tz=timezone.utc) if hasattr(stat, "st_birthtime") else None
    changed = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    ffprobe_creation = parse_ffprobe_creation_time(path)
    return ProbeResult(
        file=str(path),
        duration_seconds=duration_seconds,
        stat_birth_utc=iso_or_none(birth),
        stat_changed_utc=iso_or_none(changed),
        stat_modified_utc=iso_or_none(modified),
        ffprobe_creation_time_utc=iso_or_none(ffprobe_creation),
        inferred_start_from_stat_birth_utc=iso_or_none(birth - duration) if birth else None,
        inferred_start_from_stat_changed_utc=iso_or_none(changed - duration) if changed else None,
        inferred_start_from_stat_modified_utc=iso_or_none(modified - duration) if modified else None,
        inferred_start_from_ffprobe_creation_utc=iso_or_none(ffprobe_creation - duration) if ffprobe_creation else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe MP4 times for HUD/FIT alignment.")
    parser.add_argument("files", nargs="+", help="MP4 files to inspect")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--timezone", default="+08:00", help="Display timezone offset, e.g. +08:00")
    args = parser.parse_args()

    tz = datetime.strptime(args.timezone, "%z").tzinfo or timezone.utc
    results = [probe(Path(file).expanduser().resolve(), tz) for file in args.files]

    if args.json:
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
        return 0

    for result in results:
        path = Path(result.file)
        print(f"# {path.name}")
        print(f"- duration: {result.duration_seconds:.3f}s")
        if result.stat_birth_utc:
            birth = datetime.fromisoformat(result.stat_birth_utc)
            print(f"- stat birth time: {birth.astimezone(tz).isoformat()}")
            inferred = datetime.fromisoformat(result.inferred_start_from_stat_birth_utc)
            print(f"- inferred start from stat birth time: {inferred.astimezone(tz).isoformat()}")
        if result.stat_changed_utc:
            changed = datetime.fromisoformat(result.stat_changed_utc)
            print(f"- stat changed time (ctime): {changed.astimezone(tz).isoformat()}")
            inferred = datetime.fromisoformat(result.inferred_start_from_stat_changed_utc)
            print(f"- inferred start from stat changed time: {inferred.astimezone(tz).isoformat()}")
        if result.stat_modified_utc:
            modified = datetime.fromisoformat(result.stat_modified_utc)
            print(f"- stat modified: {modified.astimezone(tz).isoformat()}")
            inferred = datetime.fromisoformat(result.inferred_start_from_stat_modified_utc)
            print(f"- inferred start from stat modified: {inferred.astimezone(tz).isoformat()}")
        if result.ffprobe_creation_time_utc:
            ffprobe_creation = datetime.fromisoformat(result.ffprobe_creation_time_utc)
            print(f"- ffprobe creation_time: {ffprobe_creation.astimezone(tz).isoformat()}")
            inferred = datetime.fromisoformat(result.inferred_start_from_ffprobe_creation_utc)
            print(f"- inferred start from ffprobe creation_time: {inferred.astimezone(tz).isoformat()}")
        print("- note: gopro-dashboard's file-created mode maps to ctime, not macOS birth time")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
