#!/usr/bin/env python3
"""成片发布前的进度清单。媒体目录 logs/todo.md。

和 logs/timeline.txt 一起写。导出、打包、发布都读这份文件，不靠文件名猜进度。
后面的阶段不能在前面没完成时标完成。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

STEPS: tuple[tuple[str, str], ...] = (
    ("ingest", "原片对齐 FIT"),
    ("edl", "句间刀已写入时间表"),
    ("hud-record", "HUD 数据已记录，还没渲"),
    ("layout", "冷开场、贴图、插入已入表"),
    ("preview", "低成本预览"),
    ("hud-render", "留下的区间已直接渲成 HUD 透明层"),
    ("loudness-measure", "成片混音已测响度"),
    ("subs", "字幕"),
    ("final-export", "确认导出"),
    ("final-qc", "最终片 QC"),
    ("pack-upload", "打包进 upload/"),
    ("bilibili", "B 站字数预检与投稿"),
    ("drive", "Drive 暂存"),
    ("youtube", "YouTube 公开上传"),
    ("published", "双链已写，status=published"),
)

# 标成完成之前，这些步骤必须已经是 done（subs 见下面的特例）。
# hud-render / loudness-measure 只要求预览已完成，不要求字幕确认，校对时可以先做。
# final-export 仍要字幕 confirmed；缺的透明层和响度由 final_export --confirmed 自己补。
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
}

PREP_STEPS = ("hud-render", "loudness-measure")

DONE = "done"
PENDING = "pending"
SUBS_STATES = ("pending", "waiting-review", "aligned", "confirmed", "stale")
_LINE = re.compile(r"^- \[[ x]\] ([a-z-]+): ([a-z-]+) — .+$")


def todo_path(media_dir: Path | str) -> Path:
    return Path(media_dir).expanduser().resolve() / "logs" / "todo.md"


def empty_status() -> dict[str, str]:
    return {key: PENDING for key in dict(STEPS)}


def render(status: dict[str, str]) -> str:
    lines = [
        "# 成片进度",
        "",
        "做到哪看每一行。有前置的步骤，前置没完成不能打勾。",
        "校对字幕时可以先做 HUD 透明层和响度测量；确认导出仍要字幕已确认。",
        "",
    ]
    for key, label in STEPS:
        value = status.get(key, PENDING)
        mark = "x" if value == DONE or (key == "subs" and value == "confirmed") else " "
        lines.append(f"- [{mark}] {key}: {value} — {label}")
    lines.append("")
    return "\n".join(lines)


def parse(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw in text.splitlines():
        match = _LINE.match(raw.strip())
        if match:
            found[match.group(1)] = match.group(2)
    status = empty_status()
    for key in dict(STEPS):
        if key in found:
            status[key] = found[key]
    return status


def load(media_dir: Path | str) -> dict[str, str]:
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


def mark(media_dir: Path | str, step: str, state: str, *, confirmed: bool = False) -> dict[str, str]:
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
    elif state != DONE:
        raise ValueError(f"{step} only moves to done")
    if state in {DONE, "confirmed", "waiting-review", "aligned"}:
        for need in REQUIRES[step]:
            if not _is_done(status, need):
                raise ValueError(f"cannot mark {step} {state} before {need} is done")
        if step == "final-export" and status.get("subs") != "confirmed":
            raise ValueError("cannot export before subtitles are confirmed")
    status[step] = state if step == "subs" else DONE
    write(media_dir, status)
    return status


def clear_prep(media_dir: Path | str, steps: tuple[str, ...] = PREP_STEPS) -> None:
    """时间表变了之后，把已经打勾的准备步骤改回 pending。文件还没写过就不动。"""
    status = load(media_dir)
    changed = False
    for key in steps:
        if key not in REQUIRES:
            raise ValueError(f"unknown todo step: {key}")
        if status.get(key) == DONE:
            status[key] = PENDING
            changed = True
    if changed:
        write(media_dir, status)


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
