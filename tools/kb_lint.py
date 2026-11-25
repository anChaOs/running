#!/usr/bin/env python3
"""Lightweight linter for the running repository's LLM wiki (knowledge/).

Checks:
1. Frontmatter schema (type, category, title, updated, sources, related, optional aliases).
2. wiki/index.md sync (unindexed pages and dangling index links).
3. Broken [[wikilink]] and related references (ignoring fenced and inline code).
4. sources path validity (must be an existing file inside knowledge/raw/ or an http(s) URL).
5. Case-insensitive duplicate aliases, same-page duplicate aliases, alias/stem collisions,
   and full-width Chinese commas in aliases.
6. Hygiene warnings: oversized pages, missing concept sources, empty/stale log.md,
   and uncleaned incoming/ or legacy knowledge/running/ directories.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_TYPES = {"concept", "questions", "source-summary"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
FENCE_RE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
LOG_DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b", re.MULTILINE)


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    path: str
    message: str


@dataclass
class LintReport:
    pages_checked: int = 0
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    def add(self, severity: str, code: str, path: str, message: str) -> None:
        issue = Issue(severity=severity, code=code, path=path, message=message)
        if severity == "error":
            self.errors.append(issue)
        else:
            self.warnings.append(issue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages_checked": self.pages_checked,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [vars(i) for i in self.errors],
            "warnings": [vars(i) for i in self.warnings],
        }


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _parse_inline_list(raw: str) -> list[str]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    return [_strip_quotes(part) for part in inner.split(",") if _strip_quotes(part)]


def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Parse minimal YAML frontmatter without third-party dependencies."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None, text

    lines = text.splitlines()
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return None, text

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :])
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in fm_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if raw_line.startswith((" ", "\t", "-")) and stripped.startswith("- "):
            if current_list_key is not None:
                data[current_list_key].append(_strip_quotes(stripped[2:]))
            continue

        if ":" not in raw_line:
            continue

        key, val = raw_line.split(":", 1)
        key = key.strip()
        val = val.strip()
        current_list_key = None

        if val.startswith("[") and val.endswith("]"):
            data[key] = _parse_inline_list(val)
        elif val == "":
            # Could be an empty scalar or the start of a YAML block list.
            data[key] = []
            current_list_key = key
        else:
            data[key] = _strip_quotes(val)

    return data, body


def _as_list(value: Any) -> list[str] | None:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return None


def _extract_wikilinks(body: str) -> list[str]:
    cleaned = FENCE_RE.sub("", body)
    cleaned = INLINE_CODE_RE.sub("", cleaned)
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(cleaned)]


def _rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def lint_kb(kb_dir: Path, max_kb: float = 15.0) -> LintReport:
    report = LintReport()
    wiki_dir = kb_dir / "wiki"
    raw_dir = kb_dir / "raw"
    raw_root = raw_dir.resolve()
    index_path = wiki_dir / "index.md"
    log_path = wiki_dir / "log.md"

    if not wiki_dir.is_dir():
        report.add("error", "missing-wiki-dir", _rel(wiki_dir, kb_dir), "knowledge/wiki/ directory not found")
        return report

    # Collect all category wiki pages (exclude top-level index.md / log.md).
    page_paths = sorted(
        p for p in wiki_dir.rglob("*.md") if p.parent != wiki_dir
    )
    report.pages_checked = len(page_paths)

    # First pass: parse frontmatter, build stem & alias maps.
    parsed: dict[Path, tuple[dict[str, Any] | None, str]] = {}
    stem_to_paths: dict[str, list[Path]] = {}
    stem_to_paths_ci: dict[str, list[Path]] = {}
    stem_display_ci: dict[str, str] = {}
    alias_to_pages: dict[str, list[Path]] = {}
    alias_to_pages_ci: dict[str, list[Path]] = {}
    alias_display_ci: dict[str, str] = {}
    latest_updated = ""

    for path in page_paths:
        text = path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        parsed[path] = (fm, body)
        stem_to_paths.setdefault(path.stem, []).append(path)
        stem_ci = path.stem.casefold()
        stem_to_paths_ci.setdefault(stem_ci, []).append(path)
        stem_display_ci.setdefault(stem_ci, path.stem)

        rel_path = _rel(path, kb_dir)
        size_kb = path.stat().st_size / 1024.0
        if size_kb > max_kb:
            report.add(
                "warning",
                "oversized-page",
                rel_path,
                f"page size is {size_kb:.1f} KB (>{max_kb:.0f} KB); consider splitting into atomic pages",
            )

        if fm is None:
            report.add("error", "missing-frontmatter", rel_path, "missing YAML frontmatter block")
            continue

        # Validate required keys.
        page_type = fm.get("type")
        if not isinstance(page_type, str) or page_type not in VALID_TYPES:
            report.add(
                "error",
                "invalid-type",
                rel_path,
                f"invalid or missing type {page_type!r}; expected one of {sorted(VALID_TYPES)}",
            )

        category = fm.get("category")
        expected_category = path.parent.name
        if not isinstance(category, str) or not category:
            report.add("error", "missing-category", rel_path, "missing category in frontmatter")
        elif category != expected_category:
            report.add(
                "error",
                "category-mismatch",
                rel_path,
                f"frontmatter category {category!r} does not match folder {expected_category!r}",
            )

        title = fm.get("title")
        if not isinstance(title, str) or not title:
            report.add("error", "missing-title", rel_path, "missing title in frontmatter")

        updated = fm.get("updated")
        if not isinstance(updated, str) or not DATE_RE.match(updated):
            report.add(
                "error",
                "invalid-updated",
                rel_path,
                f"invalid or missing updated date {updated!r}; expected YYYY-MM-DD",
            )
        elif updated > latest_updated:
            latest_updated = updated

        # Validate aliases (optional).
        if "aliases" in fm:
            aliases = _as_list(fm.get("aliases"))
            if aliases is None:
                report.add("error", "invalid-aliases", rel_path, "aliases must be a YAML list")
            else:
                seen_in_page: set[str] = set()
                for alias in aliases:
                    if "，" in alias:
                        report.add(
                            "warning",
                            "chinese-comma-in-alias",
                            rel_path,
                            f"alias {alias!r} contains full-width comma '，'; split with ASCII ','",
                        )
                    alias_ci = alias.casefold()
                    if alias_ci in seen_in_page:
                        report.add(
                            "warning",
                            "duplicate-alias-in-page",
                            rel_path,
                            f"duplicate alias {alias!r} within the same page",
                        )
                        continue
                    seen_in_page.add(alias_ci)
                    alias_to_pages.setdefault(alias, []).append(path)
                    alias_to_pages_ci.setdefault(alias_ci, []).append(path)
                    alias_display_ci.setdefault(alias_ci, alias)

        # Validate sources.
        if "sources" not in fm or _as_list(fm.get("sources")) is None:
            report.add("error", "invalid-sources", rel_path, "sources must be a YAML list")
        else:
            sources = _as_list(fm["sources"]) or []
            if page_type == "concept" and not sources:
                report.add("warning", "empty-sources", rel_path, "concept page has empty sources list")
            for src in sources:
                if src.startswith(("http://", "https://")):
                    continue
                norm_src = src.removeprefix("knowledge/")
                if norm_src.startswith("wiki/"):
                    report.add(
                        "error",
                        "wiki-in-sources",
                        rel_path,
                        f"source {src!r} points to wiki/; move internal links to related",
                    )
                elif norm_src.startswith("incoming/"):
                    report.add(
                        "error",
                        "incoming-in-sources",
                        rel_path,
                        f"source {src!r} points to incoming/; migrate to raw/ first",
                    )
                elif not norm_src.startswith("raw/"):
                    report.add(
                        "error",
                        "non-raw-source",
                        rel_path,
                        f"source {src!r} must point under raw/ or be an http(s) URL",
                    )
                else:
                    target = (raw_dir / norm_src.removeprefix("raw/")).resolve()
                    if not target.is_relative_to(raw_root):
                        report.add(
                            "error",
                            "source-outside-raw",
                            rel_path,
                            f"source {src!r} resolves outside knowledge/raw/",
                        )
                    elif not target.is_file():
                        report.add(
                            "error",
                            "missing-source-file",
                            rel_path,
                            f"source file not found (or is a directory): {src}",
                        )

        # Validate related type.
        if "related" not in fm or _as_list(fm.get("related")) is None:
            report.add("error", "invalid-related", rel_path, "related must be a YAML list")

    # Check duplicate stems or case-insensitive alias collisions.
    for stem_ci, paths in stem_to_paths_ci.items():
        if len(paths) > 1:
            joined = ", ".join(_rel(p, kb_dir) for p in paths)
            report.add("error", "duplicate-stem", joined, f"duplicate wiki page name [[{stem_display_ci[stem_ci]}]]")

    for alias_ci, paths in alias_to_pages_ci.items():
        display = alias_display_ci[alias_ci]
        if len(paths) > 1:
            joined = ", ".join(_rel(p, kb_dir) for p in paths)
            report.add("warning", "duplicate-alias", joined, f"alias {display!r} is claimed by multiple pages")
        if alias_ci in stem_to_paths_ci:
            owners = set(stem_to_paths_ci[alias_ci])
            for conflicting_path in paths:
                if conflicting_path not in owners:
                    report.add(
                        "warning",
                        "alias-collides-stem",
                        _rel(conflicting_path, kb_dir),
                        f"alias {display!r} collides with existing page [[{stem_display_ci[alias_ci]}]]",
                    )

    valid_targets = set(stem_to_paths.keys()) | set(alias_to_pages.keys())

    # Second pass: validate [[wikilink]] and related targets.
    for path, (fm, body) in parsed.items():
        rel_path = _rel(path, kb_dir)
        for target in _extract_wikilinks(body):
            if target in valid_targets:
                continue
            norm_target = target.removeprefix("knowledge/")
            if norm_target.startswith("raw/"):
                raw_candidate = (raw_dir / norm_target.removeprefix("raw/")).resolve()
                raw_md_candidate = raw_candidate.with_suffix(".md")
                if raw_candidate.is_relative_to(raw_root) and (
                    raw_candidate.is_file() or raw_md_candidate.is_file()
                ):
                    continue
            report.add("error", "broken-wikilink", rel_path, f"broken wikilink [[{target}]]")

        if fm is not None:
            related = _as_list(fm.get("related")) or []
            for target in related:
                clean_target = target.strip("[]")
                if clean_target not in valid_targets:
                    report.add("error", "broken-related", rel_path, f"broken related entry {target!r}")

    # Third pass: check index.md sync.
    if not index_path.is_file():
        report.add("error", "missing-index", "wiki/index.md", "wiki/index.md not found")
    else:
        index_text = index_path.read_text(encoding="utf-8")
        indexed_links = set(_extract_wikilinks(index_text))
        for stem, paths in sorted(stem_to_paths.items()):
            if stem not in indexed_links:
                report.add(
                    "error",
                    "unindexed-page",
                    _rel(paths[0], kb_dir),
                    f"page [[{stem}]] is missing from wiki/index.md",
                )
        for link in sorted(indexed_links):
            if link not in stem_to_paths:
                report.add(
                    "error",
                    "dangling-index-link",
                    "wiki/index.md",
                    f"wiki/index.md links to missing page [[{link}]]",
                )

    # Fourth pass: check log.md freshness.
    if not log_path.is_file():
        report.add("warning", "missing-log", "wiki/log.md", "wiki/log.md not found")
    elif latest_updated:
        log_dates = LOG_DATE_RE.findall(log_path.read_text(encoding="utf-8"))
        latest_log = max(log_dates) if log_dates else ""
        if not latest_log:
            report.add(
                "warning",
                "stale-log",
                "wiki/log.md",
                "wiki/log.md has no '## YYYY-MM-DD' date headings",
            )
        elif latest_updated > latest_log:
            report.add(
                "warning",
                "stale-log",
                "wiki/log.md",
                f"latest wiki updated date ({latest_updated}) is newer than latest log.md entry ({latest_log})",
            )

    # Hygiene checks: residual incoming/ or legacy knowledge/running/.
    incoming_dir = kb_dir / "incoming"
    if incoming_dir.is_dir():
        leftovers = [p for p in incoming_dir.iterdir() if p.name != ".DS_Store"]
        if leftovers:
            report.add(
                "warning",
                "uncleaned-incoming",
                "incoming/",
                f"incoming/ has {len(leftovers)} item(s); clean up after ingest",
            )

    legacy_running = kb_dir / "running"
    if legacy_running.is_dir():
        report.add(
            "warning",
            "legacy-running-dir",
            "running/",
            "legacy knowledge/running/ directory still exists; content lives in knowledge/wiki/running/",
        )

    return report


def format_report(report: LintReport) -> str:
    lines = [
        f"KB lint: checked {report.pages_checked} wiki page(s) — "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)."
    ]
    if report.errors:
        lines.append("\nErrors:")
        for i in report.errors:
            lines.append(f"  [ERROR] {i.path} ({i.code}): {i.message}")
    if report.warnings:
        lines.append("\nWarnings:")
        for i in report.warnings:
            lines.append(f"  [WARN]  {i.path} ({i.code}): {i.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Lint knowledge/wiki/ pages and links.")
    parser.add_argument(
        "--kb-dir",
        type=Path,
        default=repo_root / "knowledge",
        help="Path to the knowledge directory (default: <repo>/knowledge).",
    )
    parser.add_argument(
        "--max-kb",
        type=float,
        default=15.0,
        help="Warn when a single wiki page exceeds this size in KB (default: 15).",
    )
    parser.add_argument("--json", action="store_true", help="Output report as JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code on warnings as well as errors.",
    )
    args = parser.parse_args(argv)

    report = lint_kb(args.kb_dir, max_kb=args.max_kb)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    if report.errors or (args.strict and report.warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
