#!/usr/bin/env python3
"""成片时间表：原片时钟先锁，成片时钟后排。

预览和 final_export 只读这一份。句间刀、冷开场、插入段改的是成片时间，
不改 HUD 取样用的原片时间。文件在媒体目录 logs/program.json。

schema version 1
----------------
- source_sync[]: clip、fit、offset_s。原片第 0 秒对应 FIT 开始后再过 offset_s 秒。锁死后不随成片改动。
- keeps[]: 句间刀留下的原片区间（含 open / run / close）。
- program[]: 成片片段。program_start_s 是这段第一帧在成片上的时间。
  hud 为真时，成片时间 t 的数据取样在 src_start_s + (t - program_start_s)，
  再加上 source_sync.offset_s 才是 FIT 时间。绝不拿 program 时间去查 FIT。
- overlays[]: 贴图。asset、program_start_s、program_end_s，可带 x/y/width/opacity/fade。
  手写的图必须带上量取时的成片时长；对不上，或之后时间表变了，就拒绝导出。
- transitions[]: 只在导出时做。两种，不要混：
  xfade：冷开场进第一段跑、最后一段跑进 close。at_program_s 等于下一段的
  program_start_s，两段重叠 duration_s（默认 0.2s），成片因此变短。
  wind：不同原片的跑步段接缝。不重叠、不缩短总时长。duration_s 默认 0.08s，
  导出时落到整数帧，把上一段的尾巴和下一段的开头换成风刮，并在接缝前叠 whoosh。
  同一条原片上的句间刀仍是硬切。插入段默认硬切；insert.transition 为 wind 或 xfade 才过渡。
- inserts[]: 外部视频或图文。不套跑步 HUD，只把后面的成片时间往后推。
- lead: 可选。冷开场若取自某段跑步原片，写在这里，用那段自己的原片时间画 HUD。
- hud: 记录鞋、天气、透明层规格。recorded=true 表示只记了数据，还没渲。
- frozen: 对口型前必须为 true。改刀点会清掉 frozen 并把 subs_stale 设为 true。
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import todo_list

VERSION = 1
PROGRAM_FILENAME = "program.json"
XFADE_S = 0.2
WIND_S = 0.08
DEFAULT_OVERLAY_PROFILE = "qtrle"
# 手写贴图允许的成片时长误差。小于一次 0.2s xfade，大于容器时长的零头。
OVERLAY_DURATION_TOLERANCE_S = 0.15
ROLE_ORDER = {"cold_open": 0, "run": 1, "close": 2}


def program_path(media_dir: Path | str) -> Path:
    return Path(media_dir).expanduser().resolve() / "logs" / PROGRAM_FILENAME


def empty_program(episode: str) -> dict:
    return {
        "version": VERSION,
        "episode": episode,
        "frozen": False,
        "subs_stale": False,
        "source_sync": [],
        "keeps": [],
        "program": [],
        "overlays": [],
        "transitions": [],
        "inserts": [],
        "lead": None,
        "xfade_s": XFADE_S,
        "wind_s": WIND_S,
        "hud": {"recorded": False, "overlay_profile": DEFAULT_OVERLAY_PROFILE},
    }


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("program timeline must be a JSON object")
    return data


def load_media(media_dir: Path | str) -> dict:
    path = program_path(media_dir)
    if not path.is_file():
        raise ValueError(f"program timeline not found: {path}")
    return load(path)


def save(media_dir: Path | str, table: dict) -> Path:
    path = program_path(media_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_or_init(media_dir: Path | str, episode: str) -> dict:
    path = program_path(media_dir)
    if path.is_file():
        return load(path)
    return empty_program(episode)


def classify_clip(name: str) -> str:
    stem = Path(name).stem
    if stem.endswith("-open") or stem.endswith("-open-raw"):
        return "cold_open"
    if "-close" in stem:
        return "close"
    if "-run-" in stem:
        return "run"
    raise ValueError(f"cannot classify clip role: {name}")


def seg_duration(seg: dict) -> float:
    return float(seg["src_end_s"]) - float(seg["src_start_s"])


def program_duration(table: dict) -> float:
    if not table["program"]:
        return 0.0
    last = table["program"][-1]
    return float(last["program_start_s"]) + seg_duration(last)


def _finite(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _check_range(start: float, end: float, label: str) -> None:
    if end <= start:
        raise ValueError(f"{label} end must be greater than start")
    if start < 0:
        raise ValueError(f"{label} start must be >= 0")


def _refuse_if_frozen(table: dict) -> None:
    if table.get("frozen"):
        raise ValueError("program is frozen; cuts, cold open, and inserts cannot change")


def _mark_stale_if_needed(table: dict, *, had_program: bool) -> None:
    if had_program:
        table["subs_stale"] = True
        table["frozen"] = False


def set_source_sync(table: dict, rows: list[dict]) -> dict:
    """锁原片 ↔ FIT。已有成片片段时不允许改 offset，避免 HUD 取样被悄悄换掉。"""
    _refuse_if_frozen(table)
    if table.get("program"):
        raise ValueError("source sync is locked once the program timeline exists")
    cleaned = []
    seen: set[str] = set()
    for row in rows:
        clip = str(row["clip"])
        if clip in seen:
            raise ValueError(f"duplicate source sync clip: {clip}")
        seen.add(clip)
        cleaned.append(
            {
                "clip": clip,
                "fit": str(row["fit"]),
                "offset_s": _finite(row.get("offset_s", 0.0), f"{clip} offset_s"),
            }
        )
    table["source_sync"] = cleaned
    return table


def record_hud(
    table: dict,
    *,
    shoe_name: str,
    shoe_km_after: float,
    weather_city: str | None,
    overlay_profile: str = DEFAULT_OVERLAY_PROFILE,
    video_end_time_mode: str = "file-modified",
) -> dict:
    """只记录 HUD 要用的数据，不渲染。"""
    if overlay_profile not in {"qtrle", "png", "prores4444"}:
        raise ValueError(f"unsupported overlay profile: {overlay_profile}")
    table["hud"] = {
        "recorded": True,
        "shoe_name": shoe_name,
        "shoe_km_after": _finite(shoe_km_after, "shoe_km_after"),
        "weather_city": weather_city,
        "overlay_profile": overlay_profile,
        "video_end_time_mode": video_end_time_mode,
    }
    return table


def _keep(clip: str, start: float, end: float) -> dict:
    _check_range(start, end, clip)
    return {"clip": clip, "src_start_s": start, "src_end_s": end}


def _sort_keeps(keeps: list[dict]) -> list[dict]:
    def key(row: dict) -> tuple:
        return (ROLE_ORDER[classify_clip(row["clip"])], row["clip"], float(row["src_start_s"]))

    ordered = sorted(keeps, key=key)
    by_clip: dict[str, float] = {}
    for row in ordered:
        prev = by_clip.get(row["clip"])
        if prev is not None and float(row["src_start_s"]) < prev:
            raise ValueError(f"overlapping keeps on {row['clip']}")
        by_clip[row["clip"]] = float(row["src_end_s"])
    return ordered


def upsert_keeps(table: dict, rows: list[dict]) -> dict:
    """按片段替换句间刀。不编码。已有成片时把字幕标成过期。"""
    _refuse_if_frozen(table)
    had = bool(table.get("program"))
    incoming = [_keep(str(r["clip"]), _finite(r["src_start_s"], "src_start_s"), _finite(r["src_end_s"], "src_end_s")) for r in rows]
    clips = {row["clip"] for row in incoming}
    kept = [row for row in table.get("keeps", []) if row["clip"] not in clips]
    table["keeps"] = _sort_keeps(kept + incoming)
    _rebuild(table)
    _mark_stale_if_needed(table, had_program=had)
    return table


def set_lead(table: dict, lead: dict | None) -> dict:
    """冷开场取自跑步原片时用。hud 取样走这段自己的原片时间，不是成片第 0 秒。"""
    _refuse_if_frozen(table)
    had = bool(table.get("program"))
    if lead is None:
        table["lead"] = None
    else:
        start = _finite(lead["src_start_s"], "lead src_start_s")
        end = _finite(lead["src_end_s"], "lead src_end_s")
        _check_range(start, end, "lead")
        table["lead"] = {
            "id": str(lead.get("id") or "lead"),
            "clip": str(lead["clip"]),
            "src_start_s": start,
            "src_end_s": end,
            "hud": bool(lead.get("hud", False)),
        }
    _rebuild(table)
    _mark_stale_if_needed(table, had_program=had)
    return table


def add_insert(table: dict, insert: dict) -> dict:
    _refuse_if_frozen(table)
    had = bool(table.get("program"))
    start = _finite(insert["src_start_s"], "insert src_start_s")
    end = _finite(insert["src_end_s"], "insert src_end_s")
    _check_range(start, end, "insert")
    transition = insert.get("transition") or "cut"
    if transition not in {"cut", "wind", "xfade"}:
        raise ValueError(f"insert transition must be cut, wind, or xfade, not {transition}")
    row = {
        "id": str(insert["id"]),
        "clip": str(insert["clip"]),
        "src_start_s": start,
        "src_end_s": end,
        "after_id": str(insert["after_id"]),
        "transition": transition,
    }
    inserts = [item for item in table.get("inserts", []) if item["id"] != row["id"]]
    inserts.append(row)
    table["inserts"] = inserts
    _rebuild(table)
    _mark_stale_if_needed(table, had_program=had)
    return table


def layout_signature(table: dict) -> list[list]:
    """贴图落笔时的成片分段。之后刀点、冷开场或插入一变，这张签名就对不上。"""
    signature = []
    for seg in table.get("program", []):
        signature.append(
            [
                str(seg["id"]),
                round(float(seg["program_start_s"]), 3),
                round(float(seg["src_start_s"]), 3),
                round(float(seg["src_end_s"]), 3),
            ]
        )
    return signature


def _normalize_signature(signature: object) -> list[list]:
    if not isinstance(signature, list):
        return []
    normalized = []
    for row in signature:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            return []
        try:
            normalized.append(
                [
                    str(row[0]),
                    round(float(row[1]), 3),
                    round(float(row[2]), 3),
                    round(float(row[3]), 3),
                ]
            )
        except (TypeError, ValueError):
            return []
    return normalized


def signatures_match(got: object, want: object) -> bool:
    return _normalize_signature(got) == _normalize_signature(want)


def add_close_stats(table: dict, assets: list[str]) -> dict:
    """把数据图按 close 在成片上的时长均分，写进 overlays。不改刀点。

    句间刀会把 close 切成多段。数据图覆盖整块 close，不是只盖第一段。
    """
    program = table.get("program") or []
    idxs = [i for i, seg in enumerate(program) if seg["type"] == "close"]
    if not idxs:
        raise ValueError("close stats need a close segment")
    if idxs != list(range(idxs[0], idxs[-1] + 1)):
        raise ValueError("close stats need one contiguous close block")
    if not assets:
        raise ValueError("close stats need at least one image")
    table["overlays"] = [ov for ov in table.get("overlays", []) if ov.get("role") != "stats"]
    first = program[idxs[0]]
    last = program[idxs[-1]]
    start = float(first["program_start_s"])
    end = float(last["program_start_s"]) + seg_duration(last)
    step = (end - start) / len(assets)
    for index, asset in enumerate(assets):
        ov_end = end if index == len(assets) - 1 else start + (index + 1) * step
        add_overlay(
            table,
            {
                "asset": asset,
                "program_start_s": start + index * step,
                "program_end_s": ov_end,
                "role": "stats",
                "x": "40",
                "y": "(H-h)/2",
            },
        )
    return table


def add_overlay(table: dict, overlay: dict, *, expect_duration_s: float | None = None) -> dict:
    """贴图只占成片时间，不改刀点，也不把字幕标过期。

    手写的图（不是按 close 算出来的数据图）必须声明量取时的成片时长。
    和当前表差过容差就拒绝写入，避免把另一条成片的秒数套过来。
    """
    start = _finite(overlay["program_start_s"], "overlay program_start_s")
    end = _finite(overlay["program_end_s"], "overlay program_end_s")
    _check_range(start, end, "overlay")
    role = overlay.get("role")
    if role != "stats" and expect_duration_s is None:
        raise ValueError("graphic overlay requires expect_duration_s from the cut it was measured on")
    if expect_duration_s is not None:
        got = program_duration(table)
        want = _finite(expect_duration_s, "expect_duration_s")
        if abs(got - want) > OVERLAY_DURATION_TOLERANCE_S:
            raise ValueError(
                f"overlay {overlay.get('asset')} was measured on a {want:.3f}s cut "
                f"but this program is {got:.3f}s; refusing a misplaced graphic"
            )
    row = {
        "asset": str(overlay["asset"]),
        "program_start_s": start,
        "program_end_s": end,
        "authored_signature": layout_signature(table),
    }
    for key in ("x", "y", "width", "opacity", "fade_in", "fade_out", "role"):
        if overlay.get(key) is not None:
            row[key] = overlay[key]
    overlays = [ov for ov in table.get("overlays", []) if ov.get("asset") != row["asset"]]
    overlays.append(row)
    table["overlays"] = overlays
    return table


def _segment_from_keep(keep: dict, index: int) -> dict:
    role = classify_clip(keep["clip"])
    stem = Path(keep["clip"]).stem
    return {
        "id": f"{stem}-{index}",
        "type": role,
        "clip": keep["clip"],
        "src_start_s": float(keep["src_start_s"]),
        "src_end_s": float(keep["src_end_s"]),
        "program_start_s": 0.0,
        "hud": role == "run",
    }


def default_fades(segments: list[dict], xfade: float) -> list[float]:
    """冷开场进第一段跑、最后一段跑进 close，以及明确要求 xfade 的插入段，才重叠。

    跑步段之间的风刮不在这里。风刮不缩短成片。
    """
    fades = [0.0] * len(segments)
    run_idx = [i for i, seg in enumerate(segments) if seg["type"] == "run"]
    if run_idx and xfade > 0:
        first = run_idx[0]
        last = run_idx[-1]
        if first > 0 and segments[first - 1]["type"] == "cold_open":
            fades[first] = xfade
        if last + 1 < len(segments) and segments[last + 1]["type"] == "close":
            fades[last + 1] = xfade
    if xfade > 0:
        for index, seg in enumerate(segments):
            if seg["type"] == "insert" and seg.get("transition") == "xfade":
                fades[index] = xfade
    return fades


def wind_seams(placed: list[dict], wind_s: float) -> list[dict]:
    """不同原片的跑步段接缝记风刮。同一条原片的句间刀、以及没点名的插入段，保持硬切。"""
    if wind_s <= 0:
        return []
    seams = []
    for index in range(1, len(placed)):
        prev, seg = placed[index - 1], placed[index]
        explicit = seg["type"] == "insert" and seg.get("transition") == "wind"
        auto = (
            prev["type"] == "run"
            and seg["type"] == "run"
            and prev["clip"] != seg["clip"]
        )
        if not explicit and not auto:
            continue
        seams.append(
            {
                "type": "wind",
                "at_program_s": float(seg["program_start_s"]),
                "duration_s": float(wind_s),
                "before_id": seg["id"],
            }
        )
    return seams


def reflow(segments: list[dict], fades: list[float]) -> tuple[list[dict], list[dict]]:
    if len(fades) != len(segments):
        raise ValueError("fade list does not match segments")
    placed: list[dict] = []
    transitions: list[dict] = []
    for index, seg in enumerate(segments):
        fade = float(fades[index])
        if index == 0:
            if fade:
                raise ValueError("the first segment cannot start with a transition")
            start = 0.0
        else:
            prev = placed[-1]
            start = float(prev["program_start_s"]) + seg_duration(prev) - fade
        if start < -1e-9:
            raise ValueError("transition is longer than the previous segment")
        placed.append({**seg, "program_start_s": start})
        if fade > 0:
            transitions.append(
                {
                    "type": "xfade",
                    "at_program_s": start,
                    "duration_s": fade,
                    "before_id": seg["id"],
                }
            )
    return placed, transitions


def _rebuild(table: dict) -> dict:
    counts: dict[str, int] = {}
    segments: list[dict] = []
    lead = table.get("lead")
    if lead:
        segments.append(
            {
                "id": lead["id"],
                "type": "cold_open",
                "clip": lead["clip"],
                "src_start_s": float(lead["src_start_s"]),
                "src_end_s": float(lead["src_end_s"]),
                "program_start_s": 0.0,
                "hud": bool(lead.get("hud")),
            }
        )
    for keep in table.get("keeps", []):
        stem = Path(keep["clip"]).stem
        counts[stem] = counts.get(stem, 0) + 1
        segments.append(_segment_from_keep(keep, counts[stem]))
    ids = {seg["id"] for seg in segments}
    for insert in table.get("inserts", []):
        if insert["after_id"] not in ids:
            raise ValueError(f"insert {insert['id']} after_id {insert['after_id']} is not in the program")
        if any(item["id"] == insert["id"] for item in segments):
            raise ValueError(f"duplicate segment id: {insert['id']}")
        at = next(i for i, seg in enumerate(segments) if seg["id"] == insert["after_id"])
        segments.insert(
            at + 1,
            {
                "id": insert["id"],
                "type": "insert",
                "clip": insert["clip"],
                "src_start_s": float(insert["src_start_s"]),
                "src_end_s": float(insert["src_end_s"]),
                "program_start_s": 0.0,
                "hud": False,
                "transition": insert.get("transition") or "cut",
            },
        )
        ids.add(insert["id"])
    xfade = float(table.get("xfade_s") if table.get("xfade_s") is not None else XFADE_S)
    wind_s = float(table.get("wind_s") if table.get("wind_s") is not None else WIND_S)
    placed, overlaps = reflow(segments, default_fades(segments, xfade))
    table["program"] = placed
    table["transitions"] = overlaps + wind_seams(placed, wind_s)
    return table


def sync_runs_from_disk(table: dict, media_dir: Path) -> dict:
    """按 HUD 的口径锁偏移：mtime 是原片结束，开始 = 结束 − 时长，再减 FIT 开始。"""
    import ingest_run_media as ingest

    if table.get("program"):
        raise ValueError("source sync is locked once the program timeline exists")
    fits = sorted(Path(media_dir).glob("*-run-data.fit"))
    if len(fits) != 1:
        raise ValueError("need exactly one *-run-data.fit to lock source sync")
    fit_start = ingest.fit_window(fits[0])[0]
    if fit_start is None:
        raise ValueError(f"FIT has no start time: {fits[0].name}")
    rows = []
    for path in sorted(Path(media_dir).glob("*-run-*.mp4")):
        if any(part in path.stem for part in ("hud", "raw", "preview", "final", "stats")):
            continue
        duration = ingest.run_ffprobe_duration(path)
        if not duration:
            raise ValueError(f"cannot read duration: {path.name}")
        video_start = ingest.video_window(path, duration)[0]
        rows.append(
            {
                "clip": path.name,
                "fit": fits[0].name,
                "offset_s": (video_start - fit_start).total_seconds(),
            }
        )
    if not rows:
        raise ValueError("no run clips to lock")
    return set_source_sync(table, rows)


def adopt_full_clips(table: dict, clips: list[dict]) -> dict:
    """把现成工作片整段记成保留区间。不探测、不重编码。用于字幕已经对准当前成片的试跑。"""
    rows = []
    for clip in clips:
        rows.append(
            {
                "clip": clip["clip"],
                "src_start_s": 0.0,
                "src_end_s": _finite(clip["duration_s"], f"{clip['clip']} duration"),
            }
        )
    return upsert_keeps(table, rows)


def freeze(table: dict) -> dict:
    problems = validate(table, require_frozen=False)
    if problems:
        raise ValueError("; ".join(problems))
    if not table.get("hud", {}).get("recorded"):
        raise ValueError("cannot freeze before HUD data is recorded")
    if not any(seg["type"] == "run" for seg in table["program"]):
        raise ValueError("cannot freeze without a run segment")
    table["frozen"] = True
    return table


def validate(table: dict, *, require_frozen: bool = False) -> list[str]:
    """返回问题列表。空列表表示时间表自洽。"""
    problems: list[str] = []
    if table.get("version") != VERSION:
        problems.append(f"unsupported version {table.get('version')}")
        return problems
    sync = {row["clip"]: row for row in table.get("source_sync", [])}
    if len(sync) != len(table.get("source_sync", [])):
        problems.append("duplicate source_sync clip")
    for row in table.get("source_sync", []):
        try:
            _finite(row["offset_s"], "offset_s")
        except ValueError as exc:
            problems.append(str(exc))
    try:
        ordered = _sort_keeps(list(table.get("keeps", [])))
    except ValueError as exc:
        problems.append(str(exc))
        ordered = list(table.get("keeps", []))
    if ordered != list(table.get("keeps", [])):
        problems.append("keeps are not in program order")
    expected_segments, expected_transitions = _expected_layout(table)
    program = table.get("program", [])
    if len(program) != len(expected_segments):
        problems.append("program does not match keeps, lead, and inserts")
    else:
        for got, want in zip(program, expected_segments, strict=True):
            for key in ("id", "type", "clip", "hud"):
                if got.get(key) != want.get(key):
                    problems.append(f"segment {want['id']} {key} drifted")
                    break
            if abs(float(got["src_start_s"]) - float(want["src_start_s"])) > 1e-6:
                problems.append(f"segment {got['id']} source start drifted")
            if abs(float(got["src_end_s"]) - float(want["src_end_s"])) > 1e-6:
                problems.append(f"segment {got['id']} source end drifted")
            if abs(float(got["program_start_s"]) - float(want["program_start_s"])) > 1e-4:
                problems.append(f"segment {got['id']} program_start drifted")
    if table.get("transitions") != expected_transitions and _transitions_close(table.get("transitions", []), expected_transitions):
        pass
    elif not _transitions_close(table.get("transitions", []), expected_transitions):
        problems.append("transitions do not match the program layout")
    for seg in program:
        if seg["type"] == "insert" and seg.get("hud"):
            problems.append(f"insert {seg['id']} cannot carry a running HUD")
        if seg["type"] == "run" and not seg.get("hud"):
            problems.append(f"run {seg['id']} must carry HUD")
        if seg.get("hud") and seg["clip"] not in sync and seg["type"] != "run":
            problems.append(f"{seg['id']} HUD clip is not in source_sync")
        if seg["type"] == "run" and seg["clip"] not in sync:
            problems.append(f"run clip {seg['clip']} has no source sync")
    _check_keep_partition(table, problems)
    total = program_duration(table) if program else 0.0
    current_signature = layout_signature(table)
    for ov in table.get("overlays", []):
        if "authored_signature" not in ov:
            problems.append(f"overlay {ov.get('asset')} has no timeline signature; place it again before export")
        elif not signatures_match(ov.get("authored_signature"), current_signature):
            problems.append(f"overlay {ov.get('asset')} no longer matches the program timeline; refusing export")
        try:
            start = _finite(ov["program_start_s"], "overlay start")
            end = _finite(ov["program_end_s"], "overlay end")
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if end <= start:
            problems.append(f"overlay {ov.get('asset')} ends before it starts")
        elif program and end > total + 1e-3:
            problems.append(f"overlay {ov.get('asset')} extends past the program")
    try:
        frame_timeline(table)
    except ValueError as exc:
        problems.append(str(exc))
    if require_frozen and not table.get("frozen"):
        problems.append("program is not frozen")
    if table.get("subs_stale"):
        problems.append("subtitles are stale; realign them to this timeline")
    return problems


def _expected_layout(table: dict) -> tuple[list[dict], list[dict]]:
    scratch = {
        "keeps": table.get("keeps", []),
        "lead": table.get("lead"),
        "inserts": table.get("inserts", []),
        "xfade_s": table.get("xfade_s", XFADE_S),
        "wind_s": table.get("wind_s", WIND_S),
        "program": [],
        "transitions": [],
    }
    try:
        _rebuild(scratch)
    except ValueError:
        return [], []
    return scratch["program"], scratch["transitions"]


def _transitions_close(got: list[dict], want: list[dict]) -> bool:
    if len(got) != len(want):
        return False
    for left, right in zip(got, want, strict=True):
        if left.get("type") != right.get("type") or left.get("before_id") != right.get("before_id"):
            return False
        if abs(float(left["duration_s"]) - float(right["duration_s"])) > 1e-6:
            return False
        if abs(float(left["at_program_s"]) - float(right["at_program_s"])) > 1e-4:
            return False
    return True


def _check_keep_partition(table: dict, problems: list[str]) -> None:
    """open / run / close 的成片片段必须刚好盖住 keeps。lead 和插入段不参与对账。"""
    lead_id = (table.get("lead") or {}).get("id")
    from_program: dict[str, list[tuple[float, float]]] = {}
    for seg in table.get("program", []):
        if seg["type"] == "insert" or seg["id"] == lead_id:
            continue
        from_program.setdefault(seg["clip"], []).append((float(seg["src_start_s"]), float(seg["src_end_s"])))
    keep_map: dict[str, list[tuple[float, float]]] = {}
    for keep in table.get("keeps", []):
        keep_map.setdefault(keep["clip"], []).append((float(keep["src_start_s"]), float(keep["src_end_s"])))
    if set(from_program) != set(keep_map):
        problems.append("program clips do not match keeps")
        return
    for clip, want in keep_map.items():
        if from_program.get(clip) != want:
            problems.append(f"program ranges for {clip} do not match keeps")


def layers_at(table: dict, program_t: float) -> list[dict]:
    """这个成片时间上还露着的片段。xfade 重叠时两段都在，后一段在上面。"""
    hits = []
    for seg in table.get("program", []):
        end = float(seg["program_start_s"]) + seg_duration(seg)
        if float(seg["program_start_s"]) <= program_t < end:
            src = float(seg["src_start_s"]) + (program_t - float(seg["program_start_s"]))
            hits.append({**seg, "src_s": src})
    return hits


def hud_source_time(table: dict, program_t: float) -> tuple[str, float] | None:
    """成片时间 → 最上面那层的原片时间。没有 HUD 就返回 None。"""
    hits = [layer for layer in layers_at(table, program_t) if layer.get("hud")]
    if not hits:
        return None
    top = hits[-1]
    return top["clip"], top["src_s"]


def fit_time(table: dict, clip: str, src_s: float) -> float:
    for row in table.get("source_sync", []):
        if row["clip"] == clip:
            return float(row["offset_s"]) + src_s
    raise ValueError(f"no source sync for {clip}")


def source_to_program(table: dict, clip: str, src_s: float) -> float | None:
    """原片时间 → 成片时间。被剪掉的秒返回 None。"""
    for seg in table.get("program", []):
        if seg["clip"] != clip:
            continue
        if float(seg["src_start_s"]) <= src_s < float(seg["src_end_s"]):
            return float(seg["program_start_s"]) + (src_s - float(seg["src_start_s"]))
    return None


def program_slices(table: dict) -> list[dict]:
    """预览和导出共用的切片。只含原片区间和成片起点，不含第二套刀法。"""
    return [
        {
            "id": seg["id"],
            "type": seg["type"],
            "clip": seg["clip"],
            "src_start_s": float(seg["src_start_s"]),
            "src_end_s": float(seg["src_end_s"]),
            "program_start_s": float(seg["program_start_s"]),
            "hud": bool(seg.get("hud")),
        }
        for seg in table.get("program", [])
    ]


def preview_presentation(table: dict, fps: int = 30) -> list[dict]:
    """预览不做叠化，只把 xfade 的时长从非跑步那一侧剪掉，让成片时长和导出一致。

    跑步段的原片区间不动。窗口和 xfade 都落到和导出同一组整数帧上。
    """
    timeline = frame_timeline(table, fps)
    out = []
    for index, sl in enumerate(timeline):
        trim_head = sl["fade_frames"] / fps if sl["fade_frames"] and sl["type"] != "run" else 0.0
        next_fade = timeline[index + 1]["fade_frames"] if index + 1 < len(timeline) else 0
        trim_tail = next_fade / fps if next_fade and sl["type"] != "run" else 0.0
        out.append(
            {
                "id": sl["id"],
                "type": sl["type"],
                "clip": sl["clip"],
                "src_start_s": sl["src_start_s"],
                "src_end_s": sl["src_end_s"],
                "program_start_s": sl["program_start_frame"] / fps,
                "hud": bool(sl["hud"]),
                "trim_head_s": trim_head,
                "trim_tail_s": trim_tail,
            }
        )
    return out


def preview_actions(table: dict, durations: dict[str, float]) -> list[dict]:
    """整段且格式能接上的记 copy。只有被切开的段才轻压，不按原片码率重压长段。"""
    actions = []
    for sl in preview_presentation(table):
        full = durations.get(sl["clip"])
        partial = full is None or sl["src_start_s"] > 0.02 or sl["src_end_s"] < full - 0.02
        boundary = sl["trim_head_s"] > 0 or sl["trim_tail_s"] > 0
        if partial or boundary:
            reason = "kept-range" if partial else "xfade-boundary"
            actions.append({**sl, "mode": "preview-crf", "reason": reason})
        else:
            actions.append({**sl, "mode": "copy", "reason": ""})
    return actions


def wind_transitions(table: dict) -> list[dict]:
    return [item for item in table.get("transitions", []) if item.get("type") == "wind"]


def export_slices(table: dict, fps: int = 30) -> list[dict]:
    """和预览同一组落帧后的原片区间。"""
    return [
        {
            "id": sl["id"],
            "type": sl["type"],
            "clip": sl["clip"],
            "src_start_s": sl["src_start_s"],
            "src_end_s": sl["src_end_s"],
            "program_start_s": sl["program_start_frame"] / fps,
            "hud": bool(sl["hud"]),
        }
        for sl in frame_timeline(table, fps)
    ]


def hud_jobs(table: dict, fps: int = 30) -> list[dict]:
    """导出时只给留下的、要画 HUD 的区间渲透明层。区间和画面裁切是同一组帧。"""
    profile = table.get("hud", {}).get("overlay_profile") or DEFAULT_OVERLAY_PROFILE
    jobs = []
    for sl in frame_timeline(table, fps):
        if not sl["hud"]:
            continue
        jobs.append(
            {
                "clip": sl["clip"],
                "src_start_s": sl["src_start_s"],
                "src_end_s": sl["src_end_s"],
                "overlay_profile": profile,
            }
        )
    return jobs


def kept_alpha_mtime(original_end: float, duration: float, src_end: float) -> float:
    """裁下来的片段把 mtime 设成这个值，gopro 用「结束减时长」才会对上原片时间。"""
    return float(original_end) - (float(duration) - float(src_end))


def frame_range(start: float, end: float, fps: int = 30) -> tuple[int, int]:
    """预览和导出共用的帧边界。"""
    start_frame = int(round(float(start) * fps))
    end_frame = int(round(float(end) * fps))
    if end_frame <= start_frame:
        raise ValueError("range is shorter than one frame")
    return start_frame, end_frame


def snap_frames(seconds: float, fps: int = 30) -> int:
    return max(0, int(round(float(seconds) * fps)))


def frame_timeline(table: dict, fps: int = 30) -> list[dict]:
    """原片窗口和 xfade 都落到整数帧。

    xfade 的 offset 用这一帧数，不用未对齐的浮点累计。浮点 offset 一旦
    越过 fps 滤镜实际吐出的长度，下一段（常见是 close）会被丢掉。
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    fades = {
        item["before_id"]: float(item["duration_s"])
        for item in table.get("transitions", [])
        if item.get("type", "xfade") == "xfade"
    }
    placed: list[dict] = []
    acc = 0
    for index, sl in enumerate(program_slices(table)):
        start_f, end_f = frame_range(sl["src_start_s"], sl["src_end_s"], fps)
        count = end_f - start_f
        fade_n = 0
        if index:
            fade = fades.get(sl["id"], 0.0)
            if fade > 0:
                fade_n = max(1, snap_frames(fade, fps))
                if fade_n >= acc:
                    raise ValueError(
                        f"xfade of {fade_n} frames before {sl['id']} is longer than the "
                        f"previous {acc} frames; refusing to drop {sl['id']}"
                    )
        program_start = 0 if index == 0 else acc - fade_n
        placed.append(
            {
                **sl,
                "src_start_s": start_f / fps,
                "src_end_s": end_f / fps,
                "src_start_frame": start_f,
                "src_end_frame": end_f,
                "frames": count,
                "fade_frames": fade_n,
                "program_start_frame": program_start,
            }
        )
        acc = program_start + count
    return placed


def frame_program_duration(table: dict, fps: int = 30) -> float:
    timeline = frame_timeline(table, fps)
    if not timeline:
        return 0.0
    last = timeline[-1]
    return (last["program_start_frame"] + last["frames"]) / fps


def light_video_args(target_codec: str) -> list[str]:
    """轻压。禁止靠近原片的 49Mbps。"""
    if target_codec in {"hevc", "h265"}:
        return ["-c:v", "hevc_videotoolbox", "-b:v", "8M", "-tag:v", "hvc1"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read and update logs/program.json.")
    parser.add_argument("--media-dir", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init")
    init_p.add_argument("--episode", required=True)

    sub.add_parser("sync-from-disk", help="Lock run clip offsets from mtime and FIT before any program segments exist")

    sync_p = sub.add_parser("sync")
    sync_p.add_argument("--clip", required=True)
    sync_p.add_argument("--fit", required=True)
    sync_p.add_argument("--offset", type=float, required=True)

    keeps_p = sub.add_parser("keeps")
    keeps_p.add_argument("--clip", required=True)
    keeps_p.add_argument("--windows", required=True, help="start-end,start-end in source seconds")

    adopt_p = sub.add_parser("adopt")
    adopt_p.add_argument("--episode", required=True, help="YYYY-MM-DD-slug；用来初始化时间表")

    hud_p = sub.add_parser("record-hud")
    hud_p.add_argument("-sn", "--shoe-name", required=True)
    hud_p.add_argument("-sk", "--shoe-km-after", type=float, required=True)
    hud_p.add_argument("--weather-city", default="shanghai")
    hud_p.add_argument("--no-weather", action="store_true")
    hud_p.add_argument("--overlay-profile", default=DEFAULT_OVERLAY_PROFILE, choices=("qtrle", "png", "prores4444"))

    lead_p = sub.add_parser("lead")
    lead_p.add_argument("--clip", required=True)
    lead_p.add_argument("--start", type=float, required=True)
    lead_p.add_argument("--end", type=float, required=True)
    lead_p.add_argument("--hud", action="store_true")

    ins_p = sub.add_parser("insert")
    ins_p.add_argument("--id", required=True)
    ins_p.add_argument("--clip", required=True)
    ins_p.add_argument("--start", type=float, required=True)
    ins_p.add_argument("--end", type=float, required=True)
    ins_p.add_argument("--after-id", required=True)
    ins_p.add_argument("--transition", choices=("cut", "wind", "xfade"), default="cut")

    ov_p = sub.add_parser("overlay")
    ov_p.add_argument("--asset", required=True)
    ov_p.add_argument("--start", type=float, required=True)
    ov_p.add_argument("--end", type=float, required=True)
    ov_p.add_argument("--x")
    ov_p.add_argument("--y")
    ov_p.add_argument("--width", type=int)
    ov_p.add_argument("--opacity", type=float)
    ov_p.add_argument("--role", choices=("stats", "graphic"))
    ov_p.add_argument(
        "--expect-duration",
        type=float,
        required=True,
        help="Duration in seconds of the cut these overlay times were measured on. Refuses if this program differs by more than 0.15s",
    )

    stats_p = sub.add_parser("close-stats")
    stats_p.add_argument("--assets", required=True, help="Comma-separated image names, in order")

    sub.add_parser("layout", help="Mark cold open / overlays / inserts as entered. Does not freeze")
    sub.add_parser("freeze")
    sub.add_parser("validate")
    sub.add_parser("show")
    args = parser.parse_args(argv)
    media = Path(args.media_dir)
    try:
        if args.cmd == "init":
            table = empty_program(args.episode)
            save(media, table)
        elif args.cmd == "sync-from-disk":
            table = load_or_init(media, media.name)
            save(media, sync_runs_from_disk(table, media))
            todo_list.mark(media, "ingest", "done")
        elif args.cmd == "sync":
            table = load_media(media)
            rows = [row for row in table["source_sync"] if row["clip"] != args.clip]
            rows.append({"clip": args.clip, "fit": args.fit, "offset_s": args.offset})
            save(media, set_source_sync(table, rows))
            todo_list.mark(media, "ingest", "done")
        elif args.cmd == "keeps":
            table = load_media(media)
            windows = []
            for part in args.windows.split(","):
                left, right = part.split("-", 1)
                windows.append({"clip": args.clip, "src_start_s": float(left), "src_end_s": float(right)})
            save(media, upsert_keeps(table, windows))
        elif args.cmd == "adopt":
            table = load_or_init(media, args.episode)
            save(media, adopt_clips_on_disk(table, media))
            todo_list.mark(media, "edl", "done")
        elif args.cmd == "close-stats":
            table = load_media(media)
            assets = [part.strip() for part in args.assets.split(",") if part.strip()]
            save(media, add_close_stats(table, assets))
        elif args.cmd == "layout":
            table = load_media(media)
            if not table.get("frozen"):
                before = [round(float(seg["program_start_s"]), 4) for seg in table.get("program", [])]
                _rebuild(table)
                after = [round(float(seg["program_start_s"]), 4) for seg in table.get("program", [])]
                if before and before != after:
                    table["subs_stale"] = True
                save(media, table)
            if not any(seg["type"] == "run" for seg in table.get("program", [])):
                raise SystemExit("program has no run segment")
            structural = [item for item in validate(table) if "stale" not in item]
            if structural:
                raise SystemExit("program timeline: " + "; ".join(structural))
            todo_list.mark(media, "layout", "done")
        elif args.cmd == "record-hud":
            table = load_media(media)
            city = None if args.no_weather else args.weather_city
            save(media, record_hud(
                table,
                shoe_name=args.shoe_name,
                shoe_km_after=args.shoe_km_after,
                weather_city=city,
                overlay_profile=args.overlay_profile,
            ))
            todo_list.mark(media, "hud-record", "done")
        elif args.cmd == "lead":
            table = load_media(media)
            save(media, set_lead(table, {
                "clip": args.clip, "src_start_s": args.start, "src_end_s": args.end, "hud": args.hud,
            }))
        elif args.cmd == "insert":
            table = load_media(media)
            save(media, add_insert(table, {
                "id": args.id, "clip": args.clip, "src_start_s": args.start,
                "src_end_s": args.end, "after_id": args.after_id,
                "transition": args.transition,
            }))
        elif args.cmd == "overlay":
            table = load_media(media)
            save(media, add_overlay(table, {
                "asset": args.asset, "program_start_s": args.start, "program_end_s": args.end,
                "x": args.x, "y": args.y, "width": args.width, "opacity": args.opacity, "role": args.role,
            }, expect_duration_s=args.expect_duration))
        elif args.cmd == "freeze":
            table = load_media(media)
            save(media, freeze(table))
            if todo_list.load(media).get("layout") != "done":
                todo_list.mark(media, "layout", "done")
        elif args.cmd == "validate":
            table = load_media(media)
            problems = validate(table, require_frozen=False)
            if problems:
                raise SystemExit("program timeline: " + "; ".join(problems))
            print(f"ok frozen={table.get('frozen')} duration={program_duration(table):.3f}s")
            return 0
        else:
            table = load_media(media)
            print(json.dumps(table, ensure_ascii=False, indent=2))
            return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from None
    print(program_path(media))
    return 0


def adopt_clips_on_disk(table: dict, media_dir: Path) -> dict:
    """把目录里的 open / run / close 整段收进 keeps。给试跑用，不重跑句间检测。"""
    import subprocess

    clips = []
    for pattern in ("*-open.mp4", "*-run-*.mp4", "*-close.mp4"):
        for path in sorted(media_dir.glob(pattern)):
            if any(part in path.stem for part in ("hud", "raw", "stats", "preview", "final")):
                continue
            raw = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                text=True,
            ).strip()
            clips.append({"clip": path.name, "duration_s": float(raw)})
    if not clips:
        raise ValueError(f"no open/run/close clips to adopt in {media_dir}")
    return adopt_full_clips(table, clips)


if __name__ == "__main__":
    raise SystemExit(main())
