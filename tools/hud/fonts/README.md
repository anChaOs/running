# HUD preview fonts (Linux)

Bundled stand-ins so Linux CI/preview can approximate the **Mac production** face
**Hiragino Sans GB W6** (冬青黑体简体 W6) without dual-font Latin+CJK mixing.

| File | Role |
|------|------|
| `SourceHanSansSC-Heavy.otf` | **Primary Linux preview** — Source Han Sans SC Heavy (Adobe). Same design lineage as Noto CJK; Heavy ≈ athletic Black weight. |
| `NotoSansSC-VF.ttf` | Optional fallback; wrap uses `wght=900` if Heavy missing. |

Mac does **not** need these files (system Hiragino / PingFang).

Re-download Heavy if missing:
```bash
curl -fsSL -o tools/hud/fonts/SourceHanSansSC-Heavy.otf \
  https://raw.githubusercontent.com/adobe-fonts/source-han-sans/release/OTF/SimplifiedChinese/SourceHanSansSC-Heavy.otf
```
