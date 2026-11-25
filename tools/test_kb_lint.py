"""Unit tests for tools/kb_lint.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.kb_lint import lint_kb


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestKbLint(unittest.TestCase):
    def _make_valid_kb(self, root: Path) -> None:
        _write(root / "raw" / "running" / "src-a.md", "# raw source\n")
        _write(
            root / "wiki" / "index.md",
            "# wiki index\n\n| 页 | 一句话 |\n|---|---|\n| [[VO2max]] | 最大摄氧量 |\n| [[乳酸阈]] | 乳酸拐点 |\n",
        )
        _write(root / "wiki" / "log.md", "# wiki log\n\n## 2026-11-25\n\n- init\n")
        _write(
            root / "wiki" / "running" / "VO2max.md",
            """---
type: concept
category: running
title: VO2max
aliases: [最大摄氧量, VO2peak]
updated: 2026-11-25
sources:
  - raw/running/src-a.md
related: [乳酸阈]
---

# VO2max

参考 [[乳酸阈]]。
""",
        )
        _write(
            root / "wiki" / "running" / "乳酸阈.md",
            """---
type: concept
category: running
title: 乳酸阈
aliases: [LT2, 阈值]
updated: 2026-11-25
sources: [raw/running/src-a.md]
related: [最大摄氧量]
---

# 乳酸阈

参考 [[最大摄氧量]]。
""",
        )

    def test_valid_kb_passes_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self._make_valid_kb(kb)
            report = lint_kb(kb)
            self.assertEqual(report.pages_checked, 2)
            self.assertEqual(report.errors, [])
            self.assertEqual(report.warnings, [])

    def test_detects_broken_links_and_bad_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self._make_valid_kb(kb)
            _write(
                kb / "wiki" / "running" / "新页.md",
                """---
type: concept
category: running
title: 新页
updated: 2026-11-25
sources:
  - wiki/running/VO2max.md
  - raw/running/not-found.md
related: [不存在]
---

链接到 [[幽灵页]]。
""",
            )
            report = lint_kb(kb)
            codes = {i.code for i in report.errors}
            self.assertIn("unindexed-page", codes)
            self.assertIn("wiki-in-sources", codes)
            self.assertIn("missing-source-file", codes)
            self.assertIn("broken-wikilink", codes)
            self.assertIn("broken-related", codes)

    def test_detects_alias_collision_and_hygiene_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self._make_valid_kb(kb)
            _write(
                kb / "wiki" / "running" / "乳酸阈.md",
                """---
type: concept
category: running
title: 乳酸阈
aliases: [最大摄氧量]
updated: 2026-11-26
sources: []
related: []
---

"""
                + ("测试正文" * 2000),
            )
            _write(kb / "incoming" / "2026-09-22" / "pack.txt", "leftover")
            _write(kb / "running" / "README.md", "legacy")

            report = lint_kb(kb, max_kb=10.0)
            warn_codes = {i.code for i in report.warnings}
            self.assertIn("duplicate-alias", warn_codes)
            self.assertIn("empty-sources", warn_codes)
            self.assertIn("oversized-page", warn_codes)
            self.assertIn("stale-log", warn_codes)
            self.assertIn("uncleaned-incoming", warn_codes)
            self.assertIn("legacy-running-dir", warn_codes)


if __name__ == "__main__":
    unittest.main()
