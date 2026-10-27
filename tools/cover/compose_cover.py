#!/usr/bin/env python3
"""封面三比例排版：真人抠图 + 粗白描边 + 创意底 + 大字 → 16:9 / 4:3 / 3:4。

只做「排版 + 合成」这一步，把每期手工重复的活固定下来：
  - 人像：已抠好的 RGBA PNG（推荐），或原自拍 + 本机装了 rembg 时自动抠
  - 背景：AI／设计底图（任意尺寸，按比例 cover 裁切；不要用 HUD preview）
  - 字：封面句大字（硬性下限，小图可读）+ 系列名「破三实验室」（较小但可读）
三个比例各自重排人物和字，不是从 16:9 裁出来。脚本不打开任何图片查看器。

例：
  .venv/bin/python tools/cover/compose_cover.py \
    --person ~/Movies/running-content/YYYY-MM-DD-slug/cover-work/person-cutout.png \
    --bg ~/Movies/running-content/YYYY-MM-DD-slug/cover-work/bg.jpg \
    --title "凉快就能|更接近破三？" \
    --out-dir ~/Movies/running-content/YYYY-MM-DD-slug

封面句里用 `|` 手动断行；不写就按标点/字数自动断成 2～3 行。
产出：cover-1920x1080.jpg、cover-4x3-1920x1440.jpg、cover-1080x1440.jpg、cover.jpg（=16:9），
中间件 cover-work/person-outlined.png。每个比例打印「手机小图字高」自检。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FONT = REPO / "tools/hud/fonts/SourceHanSansSC-Heavy.otf"

# name, W, H, 版式（landscape：人在一侧、字在另一侧；portrait：字在上、人在下）
FORMATS = [
    ("cover-1920x1080.jpg", 1920, 1080, "landscape"),
    ("cover-4x3-1920x1440.jpg", 1920, 1440, "landscape"),
    ("cover-1080x1440.jpg", 1080, 1440, "portrait"),
]

# 硬性字号下限（占画面高度的比例）。封面句宁可少字多行也不缩到这之下。
TITLE_MIN_FRAC = {"landscape": 0.11, "portrait": 0.075}
SERIES_RATIO = 0.42      # 系列名 ≈ 封面句的 42%
SERIES_MIN_FRAC = 0.045  # 系列名也有下限，保证可读
THUMB_W = 320            # 手机信息流小图宽度，自检用
THUMB_MIN_PX = 22        # 小图上封面句字高至少这么多像素


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


def load_person(path: Path) -> Image.Image:
    im = Image.open(path)
    if im.mode == "RGBA" and im.getextrema()[3][0] < 250:
        return im
    try:
        from rembg import remove  # type: ignore
    except ImportError:
        cut = u2net_cutout(im)
        if cut is None:
            sys.exit(f"{path} 没有透明通道，本机也没有 rembg 或 onnxruntime+u2net.onnx。先抠图存成 RGBA PNG 再跑。")
        return cut
    print("[cover] rembg 抠图中…", file=sys.stderr)
    return remove(im.convert("RGB"))


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


def text_size(font: ImageFont.FreeTypeFont, s: str, stroke: int) -> tuple[int, int]:
    b = font.getbbox(s, stroke_width=stroke)
    return b[2] - b[0], b[3] - b[1]


def fit_title(lines, font_path, box_w, box_h, min_px, max_px):
    lo, hi, best = min_px, max_px, None
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(str(font_path), mid)
        st = max(3, mid // 12)
        ws = [text_size(f, l, st)[0] for l in lines]
        total_h = int(mid * 1.18 * len(lines))
        if max(ws) <= box_w and total_h <= box_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def draw_block(img, x, y, lines, size, font_path, align="left", color=(255, 255, 255, 255)):
    f = ImageFont.truetype(str(font_path), size)
    st = max(3, size // 12)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    d = ImageDraw.Draw(img)
    lh = int(size * 1.18)
    widths = [text_size(f, l, st)[0] for l in lines]
    block_w = max(widths)
    for i, l in enumerate(lines):
        lx = x if align == "left" else x + (block_w - widths[i]) // 2
        ly = y + i * lh
        off = max(3, size // 18)
        sd.text((lx + off, ly + off), l, font=f, fill=(0, 0, 0, 170), stroke_width=st, stroke_fill=(0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(2, size // 30))))
    for i, l in enumerate(lines):
        lx = x if align == "left" else x + (block_w - widths[i]) // 2
        d.text((lx, y + i * lh), l, font=f, fill=color, stroke_width=st, stroke_fill=(10, 10, 10, 255))
    return block_w, lh * len(lines)


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
    else:
        ph = int(H * 0.60)
        p = person_ol.resize((int(person_ol.width * ph / person_ol.height), ph), Image.LANCZOS)
        if p.width > W * 0.95:
            pw = int(W * 0.95)
            p = person_ol.resize((pw, int(person_ol.height * pw / person_ol.width)), Image.LANCZOS)
        img.alpha_composite(p, ((W - p.width) // 2, H - p.height))
        tx0, box_w, box_h = margin, W - 2 * margin, int(H * 0.30)
    # 两条下限取大：画高比例，和 320px 小图字高门（16:9 下后者更严），免得排出来再被自检打回
    min_px = max(int(H * TITLE_MIN_FRAC[layout]), -(-THUMB_MIN_PX * W // THUMB_W))
    size = fit_title(lines, font_path, box_w, box_h, min_px, int(H * 0.30))
    if size is None:
        raise SystemExit(
            f"{W}x{H}：封面句在最小字号 {min_px}px 下放不下（{lines}）。"
            "按规则不缩字：用 | 多断一行，或减字。")
    s_size = max(int(size * SERIES_RATIO), int(H * SERIES_MIN_FRAC))
    ty = margin + int(s_size * 1.4)
    if layout == "landscape":
        ty = max(ty, (H - int(size * 1.18 * len(lines))) // 2 - int(s_size * 0.7))
    draw_block(img, tx0, ty - int(s_size * 1.35), [series], s_size, font_path, color=(255, 214, 0, 255))
    draw_block(img, tx0, ty, lines, size, font_path, color=title_color)
    thumb_px = size * THUMB_W / W
    return img.convert("RGB"), size, s_size, thumb_px


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
    ap.add_argument("--title-color", default="255,255,255", help="封面句颜色 R,G,B（默认白，配深描边）")
    ap.add_argument("--prefix", default="", help="出候选时加前缀，如 cover-candidates/b-")
    args = ap.parse_args()

    out = Path(args.out_dir).expanduser()
    work = out / "cover-work"
    work.mkdir(parents=True, exist_ok=True)
    person = load_person(Path(args.person).expanduser())
    ol = outline(person, args.stroke_frac)
    ol.save(work / "person-outlined.png")
    bg = Image.open(Path(args.bg).expanduser())
    color = tuple(int(c) for c in args.title_color.split(",")) + (255,)
    ok = True
    written = []
    for name, W, H, layout in FORMATS:
        lines = split_title(args.title)
        img, size, s_size, thumb = compose(bg, ol, lines, args.series, args.font, W, H, layout, args.side, color)
        dst = out / f"{args.prefix}{name}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, quality=92)
        written.append(dst)
        flag = "OK" if thumb >= THUMB_MIN_PX else "偏小"
        ok &= thumb >= THUMB_MIN_PX
        print(f"{dst.name}: 封面句 {size}px（{size / H:.0%} 画高）×{len(lines)} 行 {lines}；"
              f"系列名 {s_size}px；{THUMB_W}px 小图字高 {thumb:.0f}px [{flag}]")
    if not args.prefix:
        shutil.copyfile(written[0], out / "cover.jpg")
        print("cover.jpg = 16:9")
    if not ok:
        print("有比例小图字高偏小：减字或改断行，不要接受。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
