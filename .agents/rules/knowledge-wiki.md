---
trigger: glob
globs: "knowledge/**"
description: "Enforce the running repository's three-layer LLM wiki schema (raw/wiki/production), frontmatter fields (including aliases), and ingest/query/lint rules when working under knowledge/."
---

# Knowledge Base Rules (Bridge)

Antigravity does not auto-load subdirectory `CLAUDE.md` files. Always follow the canonical knowledge schema in `knowledge/CLAUDE.md` whenever reading or editing under `knowledge/`:

@[Knowledge Schema](../../knowledge/CLAUDE.md)

## Quick Guardrails

- Never edit files under `knowledge/raw/` (read-only sources).
- Keep `sources` in wiki frontmatter pointing to `raw/...` or authoritative `http(s)` URLs; put internal wiki links in `related`.
- Use `aliases: []` for Chinese/English synonyms or abbreviations to improve lookup and avoid duplicate pages.
- After editing `knowledge/wiki/`, run `.venv/bin/python tools/kb_lint.py` to verify links, index sync, and frontmatter schema.
