# HUD fonts (bundled)

**Production default on Mac and Linux:** `SourceHanSansSC-Heavy.otf`
(Source Han Sans SC Heavy / Adobe). Same file everywhere so HUD renders match
across machines — no dual-font Latin+CJK mixing, no Mac-only Hiragino preference.

| File | Role |
|------|------|
| `SourceHanSansSC-Heavy.otf` | **Default** — athletic ≈ Black weight; preferred by `resolve_hud_font()` first |
| `NotoSansSC-VF.ttf` | Fallback if Heavy missing; wrap uses `wght=900` |

Override with `HUD_FONT_PATH` / `HUD_FONT_INDEX` / `HUD_FONT_WGHT` (e.g. system
Hiragino Sans GB W6 on Mac). System faces are only auto-picked when the bundle
is absent.

Re-download Heavy if missing:
```bash
curl -fsSL -o tools/hud/fonts/SourceHanSansSC-Heavy.otf \
  https://raw.githubusercontent.com/adobe-fonts/source-han-sans/release/OTF/SimplifiedChinese/SourceHanSansSC-Heavy.otf
```
