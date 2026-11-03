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


def test_opener_goes_to_next_cue_ok():
    # 看看开表了 ⟨0.6s⟩ OK ⟨0.15s⟩ 我们开始了
    ws = [W(0.0, 0.8, "看看"), W(0.85, 1.6, "开表"), W(1.6, 1.8, "了"),
          W(2.4, 2.7, "OK"), W(2.85, 3.2, "我们"), W(3.25, 3.7, "开始"), W(3.7, 3.85, "了")]
    out = texts(ds.split_words(ws))
    assert out == ["看看开表了", "OK我们开始了"], out


def test_no_split_number_unit_or_english():
    ws = [W(0.0, 0.5, "今天跑了"), W(0.55, 0.9, "大概"), W(0.9, 1.2, "18"), W(2.0, 2.3, "公里"),
          W(2.35, 2.8, "然后用"), W(2.85, 3.1, "Grok"), W(3.9, 4.2, "Bot"), W(4.25, 4.9, "记录一下数据")]
    for g in ds.split_words(ws):
        t = ds.text_of(g)
        assert not t.startswith("公里") and not t.startswith("Bot"), texts(ds.split_words(ws))


def main() -> int:
    test_number_unit_merge()
    test_no_merge_without_number()
    test_colloc_merge()
    test_opener_goes_to_next_cue_ok()
    test_no_split_number_unit_or_english()
    print("ok: 5 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
