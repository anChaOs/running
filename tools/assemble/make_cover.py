#!/usr/bin/env python3
"""从跑中画面抽一帧，做成 16:9 / 4:3 / 3:4 封面。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")


def extract_frame(src: Path, dest: Path, ss: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    png = dest.with_suffix(".png")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(ss),
            "-i",
            str(src),
            "-frames:v",
            "1",
            str(png),
        ],
        check=True,
    )
    Image.open(png).convert("RGB").save(dest, quality=95, subsampling=0)
    png.unlink(missing_ok=True)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def draw_bottom_text(img: Image.Image, title: str, sub: str) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top = int(h * 0.57)
    for y in range(top, h):
        t = (y - top) / max(1, h - top)
        a = int(30 + 170 * t * t)
        draw.line([(0, y), (w - 1, y)], fill=(18, 12, 8, a))
    out = Image.alpha_composite(img, overlay)
    d = ImageDraw.Draw(out)
    title_font = load_font(max(36, w // 26))
    sub_font = load_font(max(18, w // 48))

    def center(text: str, font: ImageFont.FreeTypeFont, y: int, fill: tuple[int, int, int, int]) -> None:
        bbox = d.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        d.text(((w - tw) // 2, y), text, font=font, fill=fill)

    center(sub, sub_font, int(h * 0.76), (246, 239, 228, 220))
    center(title, title_font, int(h * 0.81), (255, 255, 255, 255))
    return out.convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make 16:9, 4:3, and 3:4 covers from a run clip.")
    parser.add_argument("--src", required=True, help="Source mp4, usually run-a")
    parser.add_argument("--title", required=True)
    parser.add_argument("--sub", default="破三实验室")
    parser.add_argument("--ss", type=float, default=40.0, help="Timestamp in seconds")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    src = Path(args.src).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "cover-frame.jpg"
    extract_frame(src, raw, args.ss)

    src_img = Image.open(raw).convert("RGB")
    if src_img.size != (1920, 1080):
        src_img = src_img.resize((1920, 1080), Image.Resampling.LANCZOS)

    # 16:9 — B 站个人空间 / 视频号
    land = draw_bottom_text(src_img, args.title, args.sub)
    land_path = out_dir / "cover-1920x1080.jpg"
    land.save(land_path, quality=95, subsampling=0)
    cover_alias = out_dir / "cover.jpg"
    land.save(cover_alias, quality=95, subsampling=0)

    # 4:3 — B 站首页推荐（规范 1920×1440；从 16:9 中心裁 1440×1080 再放大）
    four_three = src_img.crop((240, 0, 1680, 1080)).resize((1920, 1440), Image.Resampling.LANCZOS)
    four_three = draw_bottom_text(four_three, args.title, args.sub)
    four_path = out_dir / "cover-4x3-1920x1440.jpg"
    four_three.save(four_path, quality=95, subsampling=0)

    # 3:4 — 小红书
    crop = src_img.crop((200, 0, 1010, 1080)).resize((1080, 1440), Image.Resampling.LANCZOS)
    portrait = draw_bottom_text(crop, args.title, args.sub)
    port_path = out_dir / "cover-1080x1440.jpg"
    portrait.save(port_path, quality=95, subsampling=0)

    print(f"Wrote {land_path}")
    print(f"Wrote {four_path}")
    print(f"Wrote {port_path}")
    print(f"Wrote {cover_alias} (alias → 16:9)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
