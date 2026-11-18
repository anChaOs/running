#!/usr/bin/env python3
"""成片发布前的进度清单。媒体目录 logs/todo.md。

和 logs/timeline.txt 一起写。导出、打包、发布都读这份文件，不靠文件名猜进度。
后面的阶段不能在前面没完成时标完成。

行内时间是该步进入当前状态的 Asia/Shanghai 时刻，不是墙钟耗时。
时间表仍只记 START / END / FAIL。旧行没有时间就留空，不要回补。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")

STEPS: tuple[tuple[str, str], ...] = (
    ("ingest", "原片对齐 FIT"),
    ("edl", "句间刀已写入时间表"),
    ("hud-record", "HUD 数据已记录，还没渲"),
    ("layout", "冷开场、贴图、插入已入表"),
    ("preview", "低成本预览"),
    ("hud-render", "留下的区间已直接渲成 HUD 透明层"),
    ("loudness-measure", "成片混音已测响度"),
    ("subs", "字幕；waiting-review 等用户改错字和换行"),
    ("final-export", "确认导出"),
    ("final-qc", "最终片 QC；done 后等用户说可以发了"),
    ("pack-upload", "打包进 upload/"),
    ("bilibili", "B 站字数预检与投稿"),
    ("drive", "Drive 暂存"),
    ("youtube", "YouTube 公开上传"),
    ("published", "双链已写，status=published"),
    ("cleanup", "发布后清临时；等人确认再进废纸篓，禁止 rm"),
)

# 标成完成之前，这些步骤必须已经是 done（subs 见下面的特例）。
# hud-render / loudness-measure 只要求预览已完成，不要求字幕确认，校对时可以先做。
# final-export 仍要字幕 confirmed；缺的透明层和响度由 final_export --confirmed 自己补。
# cleanup 在 published 之后，等人确认才进废纸篓。
REQUIRES: dict[str, tuple[str, ...]] = {
    "ingest": (),
    "edl": ("ingest",),
    "hud-record": ("ingest",),
    "layout": ("edl", "hud-record"),
    "preview": ("layout",),
    "hud-render": ("preview",),
    "loudness-measure": ("preview",),
    "subs": ("preview",),
    "final-export": ("preview",),
    "final-qc": ("final-export",),
    "pack-upload": ("final-qc",),
    "bilibili": ("pack-upload",),
    "drive": ("pack-upload",),
    "youtube": ("drive",),
    "published": ("bilibili", "youtube"),
    "cleanup": ("published",),
}

PREP_STEPS = ("hud-render", "loudness-measure")

DONE = "done"
PENDING = "pending"
SUBS_STATES = ("pending", "waiting-review", "aligned", "confirmed", "stale")
_LINE = re.compile(
    r"^- \[[ x]\] (?P<step>[a-z-]+): "
    r"(?:(?P<at>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) )?"
    r"(?P<state>[a-z-]+) — .+$"
)
_HEADER = """\
# 成片进度

做到哪看每一行。有前置的步骤，前置没完成不能打勾。
行内时间是该步进入当前状态的 Asia/Shanghai 时刻（YYYY-MM-DD HH:MM:SS），写在状态词前面。这不是墙钟。墙钟的 START/END/FAIL 和 elapsed 仍在 logs/timeline.txt。没有时间的旧行留空，不要回补。
校对字幕时可以先做 HUD 透明层和响度测量；确认导出仍要字幕已确认。

等人的只有这三处：
- subs 为 waiting-review：等用户改错字和换行。用户说改好了、字幕 confirmed 之前，不要跑 final_export.py --confirmed。
- final-qc 已是 done：等用户审片并说「可以发了」，再打包或发布。
- published 之后 cleanup 仍是 pending：等用户确认清临时，再移进废纸篓。禁止 rm。YYYY-MM-DD-review-preview.edl 留下；旁边的预览 .srt 仍可删，除非用户另说。

封面确认、打开审片预览、必听硬失败，都不是这份清单的等待点。
"""


class TodoStatus(dict[str, str]):
    """step -> state。times 是进入该状态的时刻，旧行没有则为空字符串。"""

    def __init__(self, states: dict[str, str] | None = None, times: dict[str, str] | None = None):
        base = {key: PENDING for key, _label in STEPS}
        if states:
            for key, value in states.items():
                if key in base:
                    base[key] = value
        super().__init__(base)
        self.times: dict[str, str] = {key: "" for key in self}
        if times:
            for key, value in times.items():
                if key in self.times:
                    self.times[key] = value


def todo_path(media_dir: Path | str) -> Path:
    return Path(media_dir).expanduser().resolve() / "logs" / "todo.md"


def empty_status() -> TodoStatus:
    return TodoStatus()


def _stamp(now: datetime | None = None) -> str:
    moment = now if now is not None else datetime.now(SH)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SH)
    else:
        moment = moment.astimezone(SH)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _checked(key: str, value: str) -> str:
    if value == DONE or (key == "subs" and value == "confirmed"):
        return "x"
    return " "


def _shown(state: str, at: str) -> str:
    if at:
        return f"{at} {state}"
    return state


def render(status: dict[str, str]) -> str:
    times = getattr(status, "times", {})
    lines = _HEADER.rstrip("\n").split("\n")
    lines.append("")
    for key, label in STEPS:
        value = status.get(key, PENDING)
        at = times.get(key, "") if isinstance(times, dict) else ""
        lines.append(f"- [{_checked(key, value)}] {key}: {_shown(value, at)} — {label}")
    lines.append("")
    return "\n".join(lines)


def parse(text: str) -> TodoStatus:
    found: dict[str, str] = {}
    found_at: dict[str, str] = {}
    for raw in text.splitlines():
        match = _LINE.match(raw.strip())
        if not match:
            continue
        found[match.group("step")] = match.group("state")
        found_at[match.group("step")] = match.group("at") or ""
    return TodoStatus(found, found_at)


def load(media_dir: Path | str) -> TodoStatus:
    path = todo_path(media_dir)
    if not path.is_file():
        return empty_status()
    return parse(path.read_text(encoding="utf-8"))


def write(media_dir: Path | str, status: dict[str, str]) -> Path:
    path = todo_path(media_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(status), encoding="utf-8")
    return path


def _is_done(status: dict[str, str], key: str) -> bool:
    value = status.get(key, PENDING)
    if key == "subs":
        return value == "confirmed"
    return value == DONE


def _assign(status: TodoStatus, step: str, state: str, now: datetime | None) -> None:
    """状态没变就不改时间。旧行留空的时间不要回补。"""
    if status.get(step) == state:
        return
    status[step] = state
    status.times[step] = _stamp(now)


def mark(
    media_dir: Path | str,
    step: str,
    state: str,
    *,
    confirmed: bool = False,
    now: datetime | None = None,
) -> TodoStatus:
    """更新一步。前置没完成就拒绝，避免把后面的门闩提前打勾。"""
    if step not in REQUIRES:
        raise ValueError(f"unknown todo step: {step}")
    status = load(media_dir)
    if step == "subs":
        if state not in SUBS_STATES:
            raise ValueError(f"bad subtitle state: {state}")
        if state == "confirmed" and not confirmed:
            raise ValueError("marking subs confirmed requires --confirmed")
        if state == "stale" and status["subs"] == PENDING:
            raise ValueError("subs cannot go stale before a draft exists")
        new_state = state
    else:
        if state != DONE:
            raise ValueError(f"{step} only moves to done")
        new_state = DONE
    if new_state in {DONE, "confirmed", "waiting-review", "aligned"}:
        for need in REQUIRES[step]:
            if not _is_done(status, need):
                raise ValueError(f"cannot mark {step} {new_state} before {need} is done")
        if step == "final-export" and status.get("subs") != "confirmed":
            raise ValueError("cannot export before subtitles are confirmed")
    _assign(status, step, new_state, now)
    write(media_dir, status)
    return status


def clear_prep(
    media_dir: Path | str,
    steps: tuple[str, ...] = PREP_STEPS,
    *,
    now: datetime | None = None,
) -> None:
    """时间表变了之后，把已经打勾的准备步骤改回 pending，并改写那一行的时间。

    文件还没写过就不动。本来就是 pending 的行不改时间。
    """
    status = load(media_dir)
    changed = False
    for key in steps:
        if key not in REQUIRES:
            raise ValueError(f"unknown todo step: {key}")
        if status.get(key) == DONE:
            _assign(status, key, PENDING, now)
            changed = True
    if changed and todo_path(media_dir).is_file():
        write(media_dir, status)


def init(media_dir: Path | str, *, now: datetime | None = None) -> TodoStatus:
    """建期时写一份全 pending 的清单。文件已在就不改，避免把进度打回去。"""
    path = todo_path(media_dir)
    if path.is_file():
        return load(media_dir)
    status = empty_status()
    stamp = _stamp(now)
    for key in status:
        status.times[key] = stamp
    write(media_dir, status)
    return status


def assert_export_allowed(media_dir: Path | str) -> None:
    status = load(media_dir)
    missing = [key for key in ("ingest", "edl", "hud-record", "layout", "preview") if status.get(key) != DONE]
    if missing:
        raise ValueError("todo is not ready for export: " + ", ".join(missing))
    if status.get("subs") != "confirmed":
        raise ValueError(f"todo subs is {status.get('subs')}, export needs confirmed")


def assert_pack_allowed(media_dir: Path | str) -> None:
    status = load(media_dir)
    missing = [key for key in ("final-export", "final-qc") if status.get(key) != DONE]
    if missing:
        raise ValueError("todo is not ready to pack: " + ", ".join(missing))


def assert_publish_allowed(media_dir: Path | str) -> None:
    status = load(media_dir)
    missing = [key for key in ("pack-upload", "bilibili", "youtube") if status.get(key) != DONE]
    if missing:
        raise ValueError("todo is not ready to publish: " + ", ".join(missing))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update logs/todo.md.")
    parser.add_argument("--media-dir", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sub.add_parser("init")
    mark_p = sub.add_parser("mark")
    mark_p.add_argument("step")
    mark_p.add_argument("state")
    mark_p.add_argument("--confirmed", action="store_true")
    check_p = sub.add_parser("check")
    check_p.add_argument("gate", choices=("export", "pack", "publish"))
    args = parser.parse_args(argv)
    try:
        if args.cmd == "show":
            print(render(load(args.media_dir)), end="")
            return 0
        if args.cmd == "init":
            existed = todo_path(args.media_dir).is_file()
            init(args.media_dir)
            if existed:
                print("todo.md already exists; not rewritten", file=sys.stderr)
            print(render(load(args.media_dir)), end="")
            return 0
        if args.cmd == "mark":
            mark(args.media_dir, args.step, args.state, confirmed=args.confirmed)
            print(render(load(args.media_dir)), end="")
            return 0
        if args.gate == "export":
            assert_export_allowed(args.media_dir)
        elif args.gate == "pack":
            assert_pack_allowed(args.media_dir)
        else:
            assert_publish_allowed(args.media_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
