#!/usr/bin/env python3
"""把墙钟追加到媒体目录 logs/timeline.txt。失败再追加 logs/failures.md。

时间是 Asia/Shanghai 的 YYYY-MM-DD HH:MM:SS。只追加，不改旧行。
elapsed 取该步最近一条还没配上 END/FAIL 的 START，是墙钟差，不是子步相加。
"""

from __future__ import annotations

import argparse
import fcntl
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")

_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)"
    r"  (?P<verb>START|END|FAIL)\s+"
    r"(?P<step>\S+)"
)

Now = datetime | Callable[[], datetime] | None


def logs_dir(media_dir: Path | str) -> Path:
    return Path(media_dir).expanduser().resolve() / "logs"


def format_stamp(moment: datetime) -> str:
    return _as_shanghai(moment).strftime("%Y-%m-%d %H:%M:%S")


def format_line(
    ts: str,
    verb: str,
    step: str,
    *,
    elapsed: str | None = None,
    rc: int | None = None,
    note: str | None = None,
) -> str:
    step = check_step(step)
    note = clean_note(note)
    body = f"{ts}  {verb:<5}  {step}"
    extra: list[str] = []
    if elapsed is not None:
        extra.append(f"elapsed={elapsed}")
    if rc is not None:
        extra.append(f"rc={rc}")
    if note:
        extra.append(f"note={note}")
    if extra:
        body += "  " + "  ".join(extra)
    return body


def check_step(step: str) -> str:
    text = str(step).strip()
    if not text or any(ch.isspace() for ch in text):
        raise ValueError(f"step must be one token, got {step!r}")
    return text


def clean_note(note: str | None, limit: int = 180) -> str | None:
    if note is None:
        return None
    text = " ".join(str(note).split())
    if not text:
        return None
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def start(media_dir: Path | str, step: str, now: Now = None) -> str:
    line = format_line(format_stamp(_coerce_now(now)), "START", step)
    _append_line(logs_dir(media_dir) / "timeline.txt", line)
    return line


def end(
    media_dir: Path | str,
    step: str,
    rc: int = 0,
    note: str | None = None,
    now: Now = None,
) -> str:
    return _finish(media_dir, step, "END", rc, note, now)


def fail(
    media_dir: Path | str,
    step: str,
    rc: int = 1,
    note: str | None = None,
    now: Now = None,
) -> str:
    line, ts, elapsed, cleaned = _finish_parts(media_dir, step, "FAIL", rc, note, now)
    _append_failure(media_dir, ts, check_step(step), rc, elapsed, cleaned)
    return line


class TimelineSpan:
    """包住一段真活。成功写 END，非零或异常写 FAIL。记日志失败不改脚本退出码。"""

    def __init__(self, media_dir: Path | str, step: str, *, enabled: bool = True, now: Now = None):
        self.media_dir = media_dir
        self.step = step
        self.enabled = enabled
        self.now = now
        self.rc = 0
        self.note: str | None = None
        self._started = False

    def __enter__(self) -> TimelineSpan:
        if not self.enabled:
            return self
        try:
            start(self.media_dir, self.step, now=self.now)
            self._started = True
        except Exception as exc:
            print(f"timeline start failed: {exc}", file=sys.stderr)
            self._started = False
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.enabled or not self._started:
            return False
        rc = self.rc
        note = self.note
        if exc is not None:
            rc = rc_from_exception(exc)
            if note is None:
                note = note_from_exception(exc)
        try:
            if rc:
                fail(self.media_dir, self.step, rc=rc, note=note, now=self.now)
            else:
                end(self.media_dir, self.step, rc=0, note=note, now=self.now)
        except Exception as log_exc:
            print(f"timeline log failed: {log_exc}", file=sys.stderr)
        return False


def span(
    media_dir: Path | str,
    step: str,
    *,
    enabled: bool = True,
    now: Now = None,
) -> TimelineSpan:
    return TimelineSpan(media_dir, step, enabled=enabled, now=now)


def rc_from_exception(exc: BaseException) -> int:
    if isinstance(exc, SystemExit):
        code = exc.code
        if code is None or code == 0:
            return 0
        if isinstance(code, int):
            return code
        return 1
    returncode = getattr(exc, "returncode", None)
    if isinstance(returncode, int):
        return returncode if returncode != 0 else 1
    return 1


def note_from_exception(exc: BaseException) -> str | None:
    if isinstance(exc, SystemExit):
        if isinstance(exc.code, str):
            return clean_note(exc.code)
        return None
    text = str(exc).strip()
    name = type(exc).__name__
    if not text:
        return name
    first = text.splitlines()[0]
    if first == name:
        return name
    return clean_note(f"{name}: {first}")


def parse_ts(ts: str) -> tuple[datetime, bool]:
    if len(ts) == 16:
        parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M")
        return parsed.replace(tzinfo=SH), False
    parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=SH), True


def format_elapsed(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes}m{seconds}s"
    if minutes:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"


def format_elapsed_minutes(minutes: int) -> str:
    if minutes < 0:
        minutes = 0
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h{mins}m"
    return f"{mins}m"


def unmatched_start(existing: str, step: str) -> tuple[datetime, bool] | None:
    pending: list[tuple[datetime, bool]] = []
    wanted = check_step(step)
    for raw in existing.splitlines():
        match = _LINE.match(raw.strip())
        if not match or match.group("step") != wanted:
            continue
        started, has_seconds = parse_ts(match.group("ts"))
        if match.group("verb") == "START":
            pending.append((started, has_seconds))
        elif pending:
            pending.pop()
    if not pending:
        return None
    return pending[-1]


def elapsed_from(existing: str, step: str, end_at: datetime) -> str | None:
    found = unmatched_start(existing, step)
    if found is None:
        return None
    started, start_has_seconds = found
    end_local = _as_shanghai(end_at).replace(microsecond=0)
    if start_has_seconds:
        start_local = started.astimezone(SH).replace(microsecond=0)
        return format_elapsed(int((end_local - start_local).total_seconds()))
    start_minute = started.astimezone(SH).replace(second=0, microsecond=0)
    end_minute = end_local.replace(second=0, microsecond=0)
    minutes = int((end_minute - start_minute).total_seconds() // 60)
    return format_elapsed_minutes(minutes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append a wall-clock line to media logs/timeline.txt.")
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("action", choices=("start", "end", "fail"))
    parser.add_argument("step")
    parser.add_argument("--rc", type=int)
    parser.add_argument("--note")
    args = parser.parse_args(argv)
    if args.action == "start" and (args.rc is not None or args.note):
        parser.error("start does not take --rc or --note")
    try:
        if args.action == "start":
            line = start(args.media_dir, args.step)
        elif args.action == "end":
            line = end(args.media_dir, args.step, rc=0 if args.rc is None else args.rc, note=args.note)
        else:
            line = fail(args.media_dir, args.step, rc=1 if args.rc is None else args.rc, note=args.note)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(line)
    return 0


def _coerce_now(now: Now) -> datetime:
    if now is None:
        return datetime.now(SH)
    if callable(now):
        now = now()
    return _as_shanghai(now)


def _as_shanghai(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=SH)
    return moment.astimezone(SH)


def _append_line(path: Path, line: str) -> None:
    def update(existing: str) -> str:
        if existing and not existing.endswith("\n"):
            return "\n" + line + "\n"
        return line + "\n"

    _locked_update(path, update)


def _finish(
    media_dir: Path | str,
    step: str,
    verb: str,
    rc: int,
    note: str | None,
    now: Now,
) -> str:
    line, _ts, _elapsed, _note = _finish_parts(media_dir, step, verb, rc, note, now)
    return line


def _finish_parts(
    media_dir: Path | str,
    step: str,
    verb: str,
    rc: int,
    note: str | None,
    now: Now,
) -> tuple[str, str, str | None, str | None]:
    moment = _coerce_now(now)
    ts = format_stamp(moment)
    cleaned = clean_note(note)
    written: dict[str, str | None] = {}

    def update(existing: str) -> str:
        elapsed = elapsed_from(existing, step, moment)
        line = format_line(ts, verb, step, elapsed=elapsed, rc=rc, note=cleaned)
        written["line"] = line
        written["elapsed"] = elapsed
        if existing and not existing.endswith("\n"):
            return "\n" + line + "\n"
        return line + "\n"

    _locked_update(logs_dir(media_dir) / "timeline.txt", update)
    return str(written["line"]), ts, written.get("elapsed"), cleaned


def _failure_section(ts: str, step: str, rc: int, elapsed: str | None, note: str | None) -> str:
    lines = [f"## {ts}  {step}", "", f"- rc: {rc}"]
    if elapsed is not None:
        lines.append(f"- elapsed: {elapsed}")
    if note:
        lines.append(f"- note: {note}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _append_failure(
    media_dir: Path | str,
    ts: str,
    step: str,
    rc: int,
    elapsed: str | None,
    note: str | None,
) -> None:
    section = _failure_section(ts, step, rc, elapsed, note)

    def update(existing: str) -> str:
        if not existing.strip():
            return section
        if existing.endswith("\n\n"):
            return section
        if existing.endswith("\n"):
            return "\n" + section
        return "\n\n" + section

    _locked_update(logs_dir(media_dir) / "failures.md", update)


def _locked_update(path: Path, update) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            existing = handle.read()
            addition = update(existing)
            if addition:
                handle.write(addition)
                handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    raise SystemExit(main())
