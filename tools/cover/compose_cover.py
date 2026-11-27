#!/usr/bin/env python3
"""封面三比例排版：真人抠图 + 粗白描边 + 创意底 + 大字 → 16:9 / 4:3 / 3:4。

只做「排版 + 合成」这一步，把每期手工重复的活固定下来：
  - 人像：已抠好的 RGBA PNG（推荐），或原自拍 + 本机装了 rembg 时自动抠
  - 背景：AI／设计底图（任意尺寸，按比例 cover 裁切；不要用 HUD preview）
  - 字：多行封面句分出焦点（更大、强调色、略松字距、白边黑描边），其余行更小且换色；
    系列名「破三实验室」仍更小。人物缩放和落点不动，抠图里的手和手势保持入画。
三个比例各自重排人物和字，不是从 16:9 裁出来。脚本不打开任何图片查看器。

例：
  .venv/bin/python tools/cover/compose_cover.py \
    --person ~/Movies/running-content/YYYY-MM-DD-slug/cover-work/person-cutout.png \
    --bg ~/Movies/running-content/YYYY-MM-DD-slug/cover-work/bg.jpg \
    --title "凉快就能|更接近破三？" \
    --out-dir ~/Movies/running-content/YYYY-MM-DD-slug

封面句里用 `|` 手动断行；不写就按标点/字数自动断成 2～3 行。
产出仅三张：cover-4x3-1920x1440.jpg、cover-3x4-1080x1440.jpg、cover-16x9-1920x1080.jpg，
中间件 cover-work/person-outlined.png。每个比例打印「手机小图字高」自检。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import log_timeline  # noqa: E402
import media_layout  # noqa: E402

from PIL import Image, ImageFilter, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FONT = REPO / "tools/hud/fonts/SourceHanSansSC-Heavy.otf"

# name, W, H, 版式（landscape：人在一侧、字在另一侧；portrait：字在上、人在下）
FORMATS = [
    ("cover-4x3-1920x1440.jpg", 1920, 1440, "landscape"),
    ("cover-3x4-1080x1440.jpg", 1080, 1440, "portrait"),
    ("cover-16x9-1920x1080.jpg", 1920, 1080, "landscape"),
]

# 硬性字号下限（占画面高度的比例）。量的是焦点行；宁可少字多行也不缩到这之下。
TITLE_MIN_FRAC = {"landscape": 0.11, "portrait": 0.075}
SERIES_RATIO = 0.42      # 系列名 ≈ 焦点行的 42%
SERIES_MIN_FRAC = 0.045  # 系列名也有下限，保证可读
SERIES_TRACK_EM = 0.14   # 系列名当标签，字距略松
THUMB_W = 320            # 手机信息流小图宽度，自检用
THUMB_MIN_PX = 22        # 小图上焦点行字高至少这么多像素
# 焦点行默认琥珀金。次行白，更小的一档暖米。纯白焦点会和次行糊成一片，所以近白改回金。
FOCAL_RGB = (255, 208, 48)
SUPPORT_RGB = (255, 255, 255)
TERTIARY_RGB = (255, 228, 176)
SERIES_RGB = (255, 214, 0)
INK = (10, 10, 10, 255)
EDGE_RGB = (255, 255, 255, 255)


@dataclass(frozen=True)
class LineStyle:
    scale: float
    track_em: float
    fill: tuple[int, int, int, int]
    focal: bool


@dataclass(frozen=True)
class TitleLayout:
    styles: list[LineStyle]
    sizes: list[int]
    widths: list[int]
    gap: int
    block_w: int
    block_h: int


def _near(a: tuple[int, ...], b: tuple[int, ...], tol: int = 18) -> bool:
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a, b))


def resolve_focal_color(color: tuple[int, ...]) -> tuple[int, int, int, int]:
    """焦点行填色。接近纯白（旧的整句默认）改回琥珀金，保证和白字次行分开。"""
    rgb = tuple(int(c) for c in color[:3])
    if _near(rgb, (255, 255, 255)):
        rgb = FOCAL_RGB
    return (*rgb, 255)


def parse_title_color(text: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise SystemExit("--title-color 需要 R,G,B")
    try:
        rgb = tuple(int(p) for p in parts)
    except ValueError as exc:
        raise SystemExit("--title-color 需要 R,G,B 三个整数") from exc
    if any(c < 0 or c > 255 for c in rgb):
        raise SystemExit("--title-color 每个通道要在 0–255")
    return resolve_focal_color(rgb)


def _hook_line(line: str) -> bool:
    """数字或拉丁钩子（80/20、10km、Go Ultra）单独当焦点。"""
    if re.search(r"\d", line):
        return True
    compact = re.sub(r"\s+", "", line)
    if not compact:
        return False
    latin = sum(1 for ch in compact if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    return latin >= 2 and latin / len(compact) >= 0.5


def focal_index(lines: list[str]) -> int:
    if len(lines) <= 1:
        return 0
    hooks = [i for i, line in enumerate(lines) if _hook_line(line)]
    if len(hooks) == 1:
        return hooks[0]
    return len(lines) - 1


def title_styles(lines: list[str], focal_color: tuple[int, int, int, int]) -> list[LineStyle]:
    """多行字号阶梯 + 分色。焦点 1.0，相邻约 0.82，再远约 0.70。"""
    n = len(lines)
    focal = focal_index(lines)
    if n <= 1:
        scales = [1.0]
    elif n == 2:
        scales = [1.0, 0.78] if focal == 0 else [0.78, 1.0]
    else:
        scales = [0.70] * n
        scales[focal] = 1.0
        others = sorted((i for i in range(n) if i != focal), key=lambda i: (abs(i - focal), i))
        ladder = (0.82, 0.70, 0.64)
        for rank, i in enumerate(others):
            scales[i] = ladder[min(rank, len(ladder) - 1)]
    nonfocal = sorted({scales[i] for i in range(n) if i != focal}, reverse=True)
    secondary = nonfocal[0] if nonfocal else None
    support = (*SUPPORT_RGB, 255)
    tertiary = (*TERTIARY_RGB, 255)
    if _near(focal_color, tertiary, tol=28):
        tertiary = (186, 224, 255, 255)
    if _near(focal_color, support, tol=28):
        support = (210, 236, 255, 255)
    styles: list[LineStyle] = []
    for i, scale in enumerate(scales):
        if i == focal:
            styles.append(LineStyle(scale, 0.08, focal_color, True))
        elif scale == secondary:
            styles.append(LineStyle(scale, 0.03, support, False))
        else:
            styles.append(LineStyle(scale, 0.03, tertiary, False))
    return styles


def line_stroke(size: int, focal: bool) -> int:
    if focal:
        return max(4, size // 11)
    return max(3, size // 13)


def glyph_tracking(size: int, track_em: float) -> int:
    return max(0, int(round(size * track_em)))


def _char_advance(font: ImageFont.FreeTypeFont, ch: str) -> float:
    return float(font.getlength(ch))


def tracked_width(font: ImageFont.FreeTypeFont, text: str, tracking: int, stroke: int) -> int:
    if not text:
        return 0
    adv = sum(_char_advance(font, ch) for ch in text) + tracking * (len(text) - 1)
    return int(round(adv + stroke * 2))


def _draw_tracked(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    stroke_w: int,
    stroke_fill: tuple[int, int, int, int],
    tracking: int,
) -> None:
    cursor = float(x)
    for ch in text:
        draw.text((cursor, y), ch, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=stroke_fill)
        cursor += _char_advance(font, ch) + tracking


def layout_title(
    lines: list[str],
    font_path: str | Path,
    focal_size: int,
    styles: list[LineStyle],
) -> TitleLayout:
    sizes = [max(8, int(round(focal_size * style.scale))) for style in styles]
    for i, style in enumerate(styles):
        if style.focal:
            sizes[i] = focal_size
    widths: list[int] = []
    for line, style, size in zip(lines, styles, sizes):
        font = ImageFont.truetype(str(font_path), size)
        widths.append(tracked_width(font, line, glyph_tracking(size, style.track_em), line_stroke(size, style.focal)))
    gap = max(4, int(round(focal_size * 0.14))) if len(lines) > 1 else 0
    block_h = sum(sizes) + gap * (len(sizes) - 1)
    return TitleLayout(styles, sizes, widths, gap, max(widths, default=0), block_h)


U2NET_PATHS = [Path.home() / ".u2net/u2net.onnx",
               Path.home() / "Movies/running-content/.models/u2net.onnx"]


def u2net_cutout(im: Image.Image) -> Image.Image | None:
    """没装 rembg 时的兜底：onnxruntime + rembg 缓存里的 u2net.onnx（10-22 那期就是这么手抠的）。"""
    model = next((p for p in U2NET_PATHS if p.is_file()), None)
    if model is None:
        return None
    try:
        import numpy as np  # type: ignore
        import onnxruntime as ort  # type: ignore
    except ImportError:
        return None
    print(f"[cover] u2net 抠图中（{model}）…", file=sys.stderr)
    rgb = im.convert("RGB")
    x = np.asarray(rgb.resize((320, 320), Image.LANCZOS), dtype=np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    pred = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    pred = (pred - pred.min()) / max(float(pred.max() - pred.min()), 1e-6)
    mask = Image.fromarray((pred * 255).astype("uint8")).resize(rgb.size, Image.LANCZOS)
    out = rgb.copy()
    out.putalpha(mask)
    return out


def _person_cache_meta(path: Path) -> dict:
    st = path.stat()
    return {"name": path.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def load_person(path: Path, *, cache_dir: Path | None = None) -> Image.Image:
    with Image.open(path) as raw:
        if raw.mode == "RGBA" and raw.getextrema()[3][0] < 250:
            return raw.copy()
        rgb = raw.convert("RGB")
    cache_png = cache_dir / "person-cutout.png" if cache_dir else None
    cache_meta = cache_dir / "person-cutout.meta.json" if cache_dir else None
    meta = _person_cache_meta(path) if cache_dir else None
    if cache_png and cache_meta and cache_png.is_file() and cache_meta.is_file():
        try:
            if json.loads(cache_meta.read_text(encoding="utf-8")) == meta:
                with Image.open(cache_png) as cached:
                    if cached.mode == "RGBA" and cached.getextrema()[3][0] < 250:
                        print(f"[cover] 复用已抠人像缓存：{cache_png.name}", file=sys.stderr)
                        return cached.copy()
        except (OSError, json.JSONDecodeError, ValueError, SyntaxError):
            pass
    try:
        from rembg import remove  # type: ignore
    except ImportError:
        cut = u2net_cutout(rgb)
        if cut is None:
            sys.exit(f"{path} 没有透明通道，本机也没有 rembg 或 onnxruntime+u2net.onnx。先抠图存成 RGBA PNG 再跑。")
    else:
        print("[cover] rembg 抠图中…", file=sys.stderr)
        cut = remove(rgb)
    if cache_png and cache_meta and meta is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cut.save(cache_png)
        cache_meta.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")
    return cut


def precheck_title(lines: list[str], font_path: str | Path, focal_color: tuple[int, int, int, int]) -> None:
    """在耗时抠图之前先做快速字号预检，明显放不下时 0.05 秒直接失败。"""
    for _name, W, H, layout in FORMATS:
        margin = int(min(W, H) * 0.05)
        if layout == "portrait":
            box_w, box_h = W - 2 * margin, int(H * 0.30)
            # 竖版人物最高约占 60% 画高，字要停在这之上。
            person_top = H - int(H * 0.60)
            bottom = person_top - text_gap_above_person(H)
        else:
            # 抠图前未知人像精确宽高，按极保守人像占宽（20% 画宽）做上界预检；
            # 避免窄全身自拍被误杀，若连 20% 下界都放不下，抠完图一定放不下。
            box_w, box_h = W - 2 * margin - int(W * 0.20), int(H * 0.72)
            bottom = None
        min_px = max(int(H * TITLE_MIN_FRAC[layout]), -(-THUMB_MIN_PX * W // THUMB_W))
        if fit_title(
            lines, font_path, box_w, box_h, min_px, int(H * 0.30), focal_color,
            frame_h=H, margin=margin, bottom=bottom,
        ) is None:
            raise SystemExit(
                f"{W}x{H}：封面句在最小字号 {min_px}px 下放不下（{lines}）。"
                "按规则不缩字：用 | 多断一行，或减字。"
            )


def trim(im: Image.Image) -> Image.Image:
    box = im.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    return im.crop(box) if box else im


def outline(person: Image.Image, frac: float) -> Image.Image:
    """粗白描边：alpha 膨胀后垫白底。frac=描边宽度/人像高度。"""
    person = trim(person)
    w, h = person.size
    stroke = max(4, int(h * frac))
    pad = stroke + 4
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    canvas.paste(person, (pad, pad), person)
    alpha = canvas.getchannel("A")
    # 缩小做膨胀，快且边缘圆
    k = max(1, stroke // 12)
    small = alpha.resize((max(1, alpha.width // k), max(1, alpha.height // k)), Image.BILINEAR)
    r = max(1, stroke // k)
    for _ in range(max(1, r // 4)):
        small = small.filter(ImageFilter.MaxFilter(9))
    grown = small.resize(alpha.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
    grown = grown.point(lambda a: 255 if a > 100 else int(a * 2.5))
    white = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    white.putalpha(grown)
    white.alpha_composite(canvas)
    return white


def cover_fit(bg: Image.Image, W: int, H: int) -> Image.Image:
    s = max(W / bg.width, H / bg.height)
    im = bg.convert("RGB").resize((round(bg.width * s), round(bg.height * s)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H)).convert("RGBA")


def _boundaries(t: str) -> list[int]:
    """可断位置：词边界（jieba，装了就用；仓库 .venv 有）＋标点后。不在词中间断。"""
    try:
        import jieba  # type: ignore
        jieba.setLogLevel(60)
        pos, out = 0, []
        for w in jieba.cut(t):
            pos += len(w)
            out.append(pos)
        return out[:-1]
    except ImportError:
        return list(range(1, len(t)))


def split_title(title: str, max_lines: int = 3) -> list[str]:
    if "|" in title:
        return [t.strip() for t in title.split("|") if t.strip()]
    t = title.strip()
    if len(t) <= 6:
        return [t]
    n = 2 if len(t) <= 14 or max_lines < 3 else 3
    cuts = [c for c in _boundaries(t) if 2 <= c <= len(t) - 2]
    punct = {m.end() for m in re.finditer(r"[，,、：:！!？?]", t)}
    chosen, last = [], 0
    for k in range(1, n):
        target = len(t) * k / n
        cands = [c for c in cuts if c > last + 1]
        if not cands:
            break
        # 标点后优先（同等距离时），其次离等分点最近
        c = min(cands, key=lambda c: (abs(c - target) - (1.5 if c in punct else 0)))
        chosen.append(c)
        last = c
    parts, prev = [], 0
    for c in chosen + [len(t)]:
        parts.append(t[prev:c])
        prev = c
    return [p for p in parts if p]


def text_gap_above_person(frame_h: int) -> int:
    """竖版字块停在人物头顶之上，避免焦点行压住举起的手。"""
    return max(12, int(frame_h * 0.035))


def title_ink_overflow(size: int) -> int:
    """末行描边、投影和模糊会伸出 em 框，竖版要算进人物头顶的空隙。"""
    return line_stroke(size, True) + max(3, size // 18) + max(2, size // 30)


def fit_title(
    lines,
    font_path,
    box_w,
    box_h,
    min_px,
    max_px,
    focal_color=(*FOCAL_RGB, 255),
    *,
    frame_h: int = 0,
    margin: int = 0,
    bottom: int | None = None,
):
    """二分焦点行字号。次行按 title_styles 缩小，整块仍要落进字框。

    bottom 给定时（竖版），系列名起点之下的标题块必须停在人物头顶之上。
    """
    styles = title_styles(lines, focal_color)
    lo, hi, best = min_px, max_px, None
    while lo <= hi:
        mid = (lo + hi) // 2
        layout = layout_title(lines, font_path, mid, styles)
        ok = layout.block_w <= box_w and layout.block_h <= box_h
        if ok and bottom is not None:
            s_size = max(int(mid * SERIES_RATIO), int(frame_h * SERIES_MIN_FRAC))
            ty = margin + int(s_size * 1.4)
            ok = ty + layout.block_h + title_ink_overflow(mid) <= bottom
        if ok:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def _line_origin(x: int, align: str, block_w: int, line_w: int) -> int:
    if align == "left":
        return x
    return x + (block_w - line_w) // 2


def draw_label(img, x, y, text, size, font_path, color, align="left", track_em=SERIES_TRACK_EM):
    """系列名：小一号、略松字距，不跟焦点行抢同一套描边。"""
    font = ImageFont.truetype(str(font_path), size)
    stroke = max(3, size // 14)
    tracking = glyph_tracking(size, track_em)
    width = tracked_width(font, text, tracking, stroke)
    origin = _line_origin(x, align, width, width)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    off = max(2, size // 18)
    _draw_tracked(sd, origin + off, y + off, text, font, (0, 0, 0, 150), stroke, (0, 0, 0, 150), tracking)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(2, size // 28))))
    _draw_tracked(ImageDraw.Draw(img), origin, y, text, font, color, stroke, INK, tracking)
    return width, size


def draw_title_block(img, x, y, lines, layout: TitleLayout, font_path, align="left"):
    """焦点行：填色 + 白内边 + 黑外描边。其余行：填色 + 黑描边。字距按行分开。"""
    fonts = [ImageFont.truetype(str(font_path), size) for size in layout.sizes]
    strokes = [line_stroke(size, style.focal) for size, style in zip(layout.sizes, layout.styles)]
    trackings = [glyph_tracking(size, style.track_em) for size, style in zip(layout.sizes, layout.styles)]
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    cy = y
    for i, line in enumerate(lines):
        lx = _line_origin(x, align, layout.block_w, layout.widths[i])
        off = max(3, layout.sizes[i] // 18)
        _draw_tracked(sd, lx + off, cy + off, line, fonts[i], (0, 0, 0, 170), strokes[i], (0, 0, 0, 170), trackings[i])
        cy += layout.sizes[i] + layout.gap
    blur = max(2, max(layout.sizes) // 30)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(blur)))
    draw = ImageDraw.Draw(img)
    cy = y
    for i, line in enumerate(lines):
        lx = _line_origin(x, align, layout.block_w, layout.widths[i])
        style = layout.styles[i]
        if style.focal:
            _draw_tracked(draw, lx, cy, line, fonts[i], INK, strokes[i], INK, trackings[i])
            edge = max(2, layout.sizes[i] // 22)
            _draw_tracked(draw, lx, cy, line, fonts[i], EDGE_RGB, edge, EDGE_RGB, trackings[i])
            _draw_tracked(draw, lx, cy, line, fonts[i], style.fill, 0, style.fill, trackings[i])
        else:
            _draw_tracked(draw, lx, cy, line, fonts[i], style.fill, strokes[i], INK, trackings[i])
        cy += layout.sizes[i] + layout.gap
    return layout.block_w, layout.block_h


def compose(bg, person_ol, lines, series, font_path, W, H, layout, side, title_color):
    img = cover_fit(bg, W, H)
    margin = int(min(W, H) * 0.05)
    if layout == "landscape":
        ph = int(H * 0.96)
        p = person_ol.resize((int(person_ol.width * ph / person_ol.height), ph), Image.LANCZOS)
        if p.width > W * 0.55:
            pw = int(W * 0.55)
            p = person_ol.resize((pw, int(person_ol.height * pw / person_ol.width)), Image.LANCZOS)
        px = W - p.width - margin // 2 if side == "right" else margin // 2
        img.alpha_composite(p, (px, H - p.height))
        tx0 = margin if side == "right" else px + p.width + margin // 2
        tx1 = px - margin // 2 if side == "right" else W - margin
        box_w, box_h = tx1 - tx0, int(H * 0.72)
        text_bottom = None
    else:
        ph = int(H * 0.60)
        p = person_ol.resize((int(person_ol.width * ph / person_ol.height), ph), Image.LANCZOS)
        if p.width > W * 0.95:
            pw = int(W * 0.95)
            p = person_ol.resize((pw, int(person_ol.height * pw / person_ol.width)), Image.LANCZOS)
        img.alpha_composite(p, ((W - p.width) // 2, H - p.height))
        tx0, box_w, box_h = margin, W - 2 * margin, int(H * 0.30)
        text_bottom = (H - p.height) - text_gap_above_person(H)
    # 两条下限取大：画高比例，和 320px 小图字高门（16:9 下后者更严），免得排出来再被自检打回。
    # 下限量焦点行；次行按比例缩小，不把每一行都撑到同一字号。
    focal = title_color if len(title_color) == 4 else resolve_focal_color(title_color)
    min_px = max(int(H * TITLE_MIN_FRAC[layout]), -(-THUMB_MIN_PX * W // THUMB_W))
    size = fit_title(
        lines, font_path, box_w, box_h, min_px, int(H * 0.30), focal,
        frame_h=H, margin=margin, bottom=text_bottom,
    )
    if size is None:
        raise SystemExit(
            f"{W}x{H}：封面句在最小字号 {min_px}px 下放不下（{lines}）。"
            "按规则不缩字：用 | 多断一行，或减字。")
    styles = title_styles(lines, focal)
    placed = layout_title(lines, font_path, size, styles)
    s_size = max(int(size * SERIES_RATIO), int(H * SERIES_MIN_FRAC))
    ty = margin + int(s_size * 1.4)
    if layout == "landscape":
        ty = max(ty, (H - placed.block_h) // 2 - int(s_size * 0.7))
    draw_label(img, tx0, ty - int(s_size * 1.35), series, s_size, font_path, (*SERIES_RGB, 255))
    draw_title_block(img, tx0, ty, lines, placed, font_path)
    thumb_px = size * THUMB_W / W
    return img.convert("RGB"), size, s_size, thumb_px, placed.sizes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--person", required=True, help="已抠好的 RGBA PNG（或原自拍：本机 rembg，没有就用 onnxruntime + ~/.u2net/u2net.onnx）")
    ap.add_argument("--bg", required=True, help="创意底图（AI／设计；不要 HUD preview）")
    ap.add_argument("--title", required=True, help="封面句；| 手动断行")
    ap.add_argument("--series", default="破三实验室")
    ap.add_argument("--out-dir", required=True, help="媒体目录 ~/Movies/running-content/YYYY-MM-DD-slug")
    ap.add_argument("--side", choices=["right", "left"], default="right", help="横版人物在哪侧（默认右，字在左半）")
    ap.add_argument("--font", default=str(DEFAULT_FONT))
    ap.add_argument("--stroke-frac", type=float, default=0.018, help="白描边宽 / 人像高")
    ap.add_argument(
        "--title-color",
        default="255,208,48",
        help="焦点行填色 R,G,B（默认琥珀金）。其余行固定白/暖米。接近纯白时仍用琥珀金。",
    )
    ap.add_argument("--prefix", default="", help="出候选时加前缀，如 cover-candidates/b-")
    args = ap.parse_args()
    with log_timeline.span(Path(args.out_dir).expanduser(), "cover") as wall:
        wall.rc = _compose(args)
        return wall.rc


def _compose(args) -> int:
    out = Path(args.out_dir).expanduser()
    lines = split_title(args.title)
    color = parse_title_color(args.title_color)
    precheck_title(lines, args.font, color)
    work = out / "cover-work"
    work.mkdir(parents=True, exist_ok=True)
    person = load_person(Path(args.person).expanduser(), cache_dir=work)
    ol = outline(person, args.stroke_frac)
    ol.save(work / "person-outlined.png")
    bg = Image.open(Path(args.bg).expanduser())
    ok = True
    written = []
    dest_dir = media_layout.cover_dest_dir(out, args.prefix)
    for name, W, H, layout in FORMATS:
        img, size, s_size, thumb, sizes = compose(
            bg, ol, lines, args.series, args.font, W, H, layout, args.side, color
        )
        dst = dest_dir / f"{args.prefix}{name}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, quality=92)
        written.append(dst)
        flag = "OK" if thumb >= THUMB_MIN_PX else "偏小"
        ok &= thumb >= THUMB_MIN_PX
        print(f"{dst.name}: 焦点 {size}px（{size / H:.0%} 画高）行字号 {sizes} ×{len(lines)} 行 {lines}；"
              f"系列名 {s_size}px；{THUMB_W}px 小图焦点字高 {thumb:.0f}px [{flag}]")
    # 只留三张比例命名，不再写 cover.jpg / 无比例旧名
    if not ok:
        print("有比例小图字高偏小：减字或改断行，不要接受。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
