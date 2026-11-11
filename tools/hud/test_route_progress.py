#!/usr/bin/env python3
"""Mini-map progress must not follow the spatially nearest route sample.

A loop (or out-and-back) can put the current fix closer to a later or earlier
vertex than to the vertex for this frame. The old nearest-in-degrees search
then paints the unrun course sand for a frame and snaps back.

Run: python3 tools/hud/test_route_progress.py
"""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

import route_progress as rp


class P:
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon


def _dist2(a: P, b: P) -> float:
    return (a.lat - b.lat) ** 2 + (a.lon - b.lon) ** 2


def test_loop_close_pass_does_not_paint_unrun_sand():
    # 15.35 km loop. At 6.44 km the fix sits a few meters toward a later pass
    # of the same course (the failure in the 0:37:48 frame). 14 s / 0.04 km
    # earlier the fix is on the true vertex (the 0:37:34 frame).
    start = P(31.22000, 121.46000)
    at_640 = P(31.23000, 121.47000)
    at_644 = P(31.23000, 121.47040)
    far = P(31.25000, 121.49000)
    later_pass = P(31.23006, 121.47040)  # ~7 m north of the 6.44 km vertex
    locs = [start, at_640, at_644, far, later_pass]
    progress_km = [0.0, 6.40, 6.44, 10.0, 14.90]

    fix_644 = P(31.23004, 121.47040)
    assert _dist2(fix_644, later_pass) < _dist2(fix_644, at_644)
    assert rp.nearest_route_index(locs, fix_644) == 4

    idx = rp.completed_route_index(locs, progress_km, fix_644, 6.44)
    assert idx == 2, idx
    assert progress_km[idx] == 6.44
    assert all(km <= 6.44 for km in progress_km[: idx + 1])
    assert progress_km[idx + 1] > 6.44

    fix_640 = P(31.23000, 121.47000)
    assert rp.nearest_route_index(locs, fix_640) == 1
    idx_640 = rp.completed_route_index(locs, progress_km, fix_640, 6.40)
    assert idx_640 == 1, idx_640
    # The bad frame must not jump ahead of the good one by the rest of the lap.
    assert progress_km[idx] - progress_km[idx_640] < 1.0


def test_out_and_back_return_leg_stays_gray():
    # Out along a street, back 9 m to the north. Halfway out, the fix drifts
    # toward the return lane and is closer to that later vertex.
    outbound = P(31.23000, 121.47100)
    turn = P(31.23000, 121.47500)
    return_leg = P(31.23008, 121.47100)
    locs = [
        P(31.23000, 121.47000),
        outbound,
        turn,
        return_leg,
        P(31.23008, 121.47000),
    ]
    progress_km = [0.0, 1.0, 5.0, 9.0, 10.0]
    fix = P(31.23005, 121.47100)
    assert _dist2(fix, return_leg) < _dist2(fix, outbound)
    assert rp.nearest_route_index(locs, fix) == 3
    idx = rp.completed_route_index(locs, progress_km, fix, 1.0)
    assert idx == 1, idx
    assert 9.0 not in progress_km[: idx + 1]


def test_revisit_does_not_rewind_completed_prefix():
    # Late on the same loop the fix is closer to the 6.44 km vertex than to
    # the later pass. Nearest would erase the sand already run.
    at_644 = P(31.23000, 121.47040)
    later_pass = P(31.23006, 121.47040)
    locs = [
        P(31.22000, 121.46000),
        P(31.23000, 121.47000),
        at_644,
        P(31.25000, 121.49000),
        later_pass,
    ]
    progress_km = [0.0, 6.40, 6.44, 10.0, 14.90]
    fix = P(31.23001, 121.47040)
    assert _dist2(fix, at_644) < _dist2(fix, later_pass)
    assert rp.nearest_route_index(locs, fix) == 2
    idx = rp.completed_route_index(locs, progress_km, fix, 14.90)
    assert idx == 4, idx
    assert progress_km[idx] == 14.90


def test_between_samples_does_not_include_the_next_vertex():
    progress = [0.0, 6.40, 6.44, 15.35]
    assert rp.route_progress_index(progress, 6.42) == 1
    assert rp.route_progress_index(progress, 6.44) == 2
    assert rp.route_progress_index(progress, 0.0) == 0
    assert rp.route_progress_index(progress, 16.0) == 3
    assert rp.route_progress_index([], 1.0) == 0


def test_sample_time_not_odo_orders_a_loop_fix():
    # Same geometry as the flicker, but the key is the frame clock the HUD
    # actually stores on each sample.
    t0 = datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc)
    samples = [
        SimpleNamespace(dt=t0, lat=31.22000, lon=121.46000),
        SimpleNamespace(dt=t0 + timedelta(seconds=37 * 60 + 34), lat=31.23000, lon=121.47000),
        SimpleNamespace(dt=t0 + timedelta(seconds=37 * 60 + 48), lat=31.23000, lon=121.47040),
        SimpleNamespace(dt=t0 + timedelta(seconds=5300), lat=31.23006, lon=121.47040),
    ]
    for sample in samples:
        sample.point = sample
    progress = [rp.progress_from_entry(sample) for sample in samples]
    assert progress == sorted(progress)
    current = samples[2]
    fix = P(31.23004, 121.47040)
    assert rp.nearest_route_index(samples, fix) == 3
    idx = rp.completed_route_index(samples, progress, fix, rp.progress_from_entry(current))
    assert idx == 2, idx


def test_missing_progress_still_draws():
    locs = [P(0, 0), P(0, 1), P(1, 1)]
    assert rp.completed_route_index(locs, None, P(1, 1), None) == 2
    assert rp.completed_route_index([], None, P(0, 0), None) == 0


def test_circuit_draw_asks_for_progress_index():
    src = Path(__file__).with_name("gopro_dashboard_wrap.py").read_text(encoding="utf-8")
    assert "completed_route_index(" in src


def main() -> int:
    tests = [
        test_loop_close_pass_does_not_paint_unrun_sand,
        test_out_and_back_return_leg_stays_gray,
        test_revisit_does_not_rewind_completed_prefix,
        test_between_samples_does_not_include_the_next_vertex,
        test_sample_time_not_odo_orders_a_loop_fix,
        test_missing_progress_still_draws,
        test_circuit_draw_asks_for_progress_index,
    ]
    for test in tests:
        test()
    print(f"ok: {len(tests)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
