"""留下区间的 HUD 取样点。不依赖 gopro-overlay，渲染和单测共用。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


def iter_kept_ticks(ticks: Iterable[T], start: T, end: T) -> Iterator[T]:
    """半开区间 [start, end) 上的取样点。

    gopro 每 0.1 秒画一帧。句间刀留下的最短语音可以只有 0.08 秒，
    落在两个取样点之间时一个点都没有。这时补上区间起点，整段渲染才不会退出。
    已经有取样点时不补，避免把后面的帧整体往后推。
    """
    if not end > start:
        raise ValueError(f"HUD range is empty: {start}..{end}")
    yielded = False
    for tick in ticks:
        if tick < start:
            continue
        if tick >= end:
            break
        yielded = True
        yield tick
    if not yielded:
        yield start
