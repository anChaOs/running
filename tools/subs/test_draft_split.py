#!/usr/bin/env python3
"""draft_subs 切条后处理自检（无模型、无音频）。

运行：python3 tools/subs/test_draft_split.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import draft_subs as ds  # noqa: E402
import subs_core as sc  # noqa: E402


def W(s: float, e: float, w: str) -> sc.Word:
    return sc.Word(s, e, w, 1.0)


def texts(groups):
    return [ds.text_of(g) for g in groups]


def test_number_unit_merge():
    # 「18-19」|「度了」→ 一条
    groups = [
        [W(0.0, 0.4, "18-19")],
        [W(0.5, 0.8, "度了")],
    ]
    out = ds.merge_cut_fixes(groups)
    assert texts(out) == ["18-19度了"], texts(out)

    # 「2055」|「几」→ 一条
    groups = [
        [W(0.0, 0.3, "2055")],
        [W(0.4, 0.5, "几")],
    ]
    out = ds.merge_cut_fixes(groups)
    assert texts(out) == ["2055几"], texts(out)

    # 「10」|「公里」→ 一条
    groups = [
        [W(0.0, 0.2, "10")],
        [W(0.3, 0.6, "公里")],
    ]
    out = ds.merge_cut_fixes(groups)
    assert texts(out) == ["10公里"], texts(out)


def test_no_merge_without_number():
    groups = [
        [W(0.0, 0.4, "今天")],
        [W(0.5, 0.8, "度了")],
    ]
    out = ds.merge_cut_fixes(groups)
    assert texts(out) == ["今天", "度了"], texts(out)


def test_colloc_merge():
    groups = [
        [W(0.0, 0.4, "精神")],
        [W(0.5, 0.9, "图腾吧")],
    ]
    out = ds.merge_cut_fixes(groups)
    assert texts(out) == ["精神图腾吧"], texts(out)


def test_score_cut_penalizes_number_unit():
    ws = [W(0.0, 0.3, "2055"), W(0.4, 0.5, "几")]
    # cutting after 2055 should be strongly discouraged
    assert ds.score_cut(ws, 0) < 0, ds.score_cut(ws, 0)


def main() -> int:
    test_number_unit_merge()
    test_no_merge_without_number()
    test_colloc_merge()
    test_score_cut_penalizes_number_unit()
    print("ok: 4 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
