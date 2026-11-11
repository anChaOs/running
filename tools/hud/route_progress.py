"""Decide how much of the mini-map route is already run.

The drawable route is the whole activity in time order. Painting the prefix
through the spatially nearest vertex turns the unrun course sand whenever a
loop or out-and-back passes near the current fix. Progress follows the sample
clock (odometer only if a sample has no time), never lat/lon.
"""

from __future__ import annotations

import bisect
from datetime import datetime
from datetime import timezone
from typing import Sequence


def nearest_route_index(locs, location) -> int:
    """Index of the closest sample in squared degrees.

    Ties keep the earlier sample. A later sample wins as soon as it is
    strictly closer, which is wrong on a loop. Used only when the frame has
    no progress key.
    """
    if not locs:
        return 0
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(locs):
        d = (p.lat - location.lat) ** 2 + (p.lon - location.lon) ** 2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def route_progress_index(progress: Sequence[float], current: float) -> int:
    """Last vertex whose progress is at or before `current`.

    `progress` is non-decreasing along the route (sample time, or odometer).
    Spatial neighbors cannot move the index.
    """
    if not progress:
        return 0
    found = bisect.bisect_right(progress, current) - 1
    if found < 0:
        return 0
    return found


def completed_route_index(locs, progress, location, current_progress: float | None) -> int:
    """Vertex through which the sand 'already run' stroke may extend.

    Prefer the sample clock. Fall back to a spatial snap only when this frame
    has no progress key, so older callers still draw something.
    """
    if (
        locs
        and progress
        and len(progress) == len(locs)
        and current_progress is not None
    ):
        return route_progress_index(progress, current_progress)
    return nearest_route_index(locs, location)


def progress_from_entry(entry) -> float | None:
    """Monotonic key for one route sample or the current frame.

    Sample time orders the polyline. FIT distance lives on that same sample,
    so the colored prefix ends where the HUD distance is. Odometer is only a
    fallback for a sample that has no timestamp.
    """
    dt = getattr(entry, "dt", None)
    if isinstance(dt, datetime):
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    odo = getattr(entry, "odo", None)
    if odo is None:
        return None
    to_unit = getattr(odo, "to", None)
    if callable(to_unit):
        try:
            return float(to_unit("meter").magnitude)
        except Exception:
            pass
    magnitude = getattr(odo, "magnitude", None)
    if magnitude is not None:
        try:
            return float(magnitude)
        except (TypeError, ValueError):
            return None
    try:
        return float(odo)
    except (TypeError, ValueError):
        return None
