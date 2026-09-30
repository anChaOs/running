#!/usr/bin/env python3
"""调用 gopro-dashboard 前注入 pace_quote、特粗字重，并允许 FIT-only 出透明图层。"""

from __future__ import annotations

import json
import math
import os
import runpy
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

import fitdecode
from gopro_overlay import arguments as go_args
from gopro_overlay import font as go_font
from gopro_overlay import layout_xml as lx
from gopro_overlay.dimensions import Dimension
from gopro_overlay.journey import Journey
from gopro_overlay.layout import Overlay
from gopro_overlay.layout_components import text as text_widget
from gopro_overlay.rdp import rdp
from gopro_overlay.units import units
from gopro_overlay.widgets import map as map_widgets
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


_orig_formatter = lx.quantity_formatter_for
_orig_arguments = go_args.gopro_dashboard_arguments
_orig_load_font = go_font.load_font
_orig_metric_accessor_from = lx.metric_accessor_from
_orig_overlay_init = Overlay.__init__
_orig_create_text = lx.Widgets.create_text

# 跑鞋名含汉字时用冬青黑体 W6。SF Compact Rounded 没有 CJK 字形。
CJK_FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
CJK_FONT_INDEX = 2

# 对齐预览 Compact 特粗。font_variant 会掉回 Regular，每次都要再设一次。
HUD_FONT_VARIATION = "Black"


def _apply_hud_weight(loaded_font):
    if not hasattr(loaded_font, "set_variation_by_name"):
        return loaded_font
    try:
        loaded_font.set_variation_by_name(HUD_FONT_VARIATION)
    except OSError:
        if hasattr(loaded_font, "set_variation_by_axes"):
            loaded_font.set_variation_by_axes([900])
    return loaded_font


def _needs_cjk_font(element) -> bool:
    name = element.attrib.get("name", "")
    body = element.text or ""
    if name == "shoe_name_text":
        return True
    return any("一" <= ch <= "鿿" for ch in body)


def create_text(self, element, entry, **kwargs):
    if not _needs_cjk_font(element):
        return _orig_create_text(self, element, entry, **kwargs)
    if element.text is None:
        raise OSError("Text components should have the text in the element like <component...>Text</component>")
    size = lx.iattrib(element, "size", d=16, r=range(1, 2000))
    font = ImageFont.truetype(font=CJK_FONT, size=size, index=CJK_FONT_INDEX)
    return text_widget(
        at=lx.at(element),
        value=lambda: element.text,
        font=font,
        align=lx.attrib(element, "align", d="left"),
        direction=lx.attrib(element, "direction", d="ltr"),
        fill=lx.rgbattr(element, "rgb", d=(255, 255, 255)),
        stroke=lx.rgbattr(element, "outline", d=(0, 0, 0)),
        stroke_width=lx.iattrib(element, "outline_width", d=2),
    )


def load_font(font: str, size: int = 32):
    loaded = _orig_load_font(font, size)
    _apply_hud_weight(loaded)
    orig_variant = loaded.font_variant

    def font_variant(*args, **kwargs):
        return _apply_hud_weight(orig_variant(*args, **kwargs))

    loaded.font_variant = font_variant
    return loaded


def metric_accessor_from(name: str):
    extra = {
        "wx_temp": lambda e: getattr(e, "wx_temp", None),
        "wx_feels": lambda e: getattr(e, "wx_feels", None),
        "wx_rh": lambda e: getattr(e, "wx_rh", None),
        "elapsed": lambda e: getattr(e, "elapsed", None),
    }
    if name in extra:
        return extra[name]
    return _orig_metric_accessor_from(name)


def _fit_path_from_argv() -> Path | None:
    argv = sys.argv
    for i, token in enumerate(argv):
        if token in {"--gpx", "--fit"} and i + 1 < len(argv):
            path = Path(argv[i + 1])
            return path if path.exists() else None
        for prefix in ("--gpx=", "--fit="):
            if token.startswith(prefix):
                path = Path(token.split("=", 1)[1])
                return path if path.exists() else None
    return None


def _event_type_name(value) -> str:
    if value is None:
        return ""
    return str(getattr(value, "name", value))


def _parse_timer_intervals(fit_path: Path) -> list[tuple[datetime, datetime]]:
    # 运动时长跟 COROS「运动时间」：只累计 timer start→stop，不含暂停。
    events: list[tuple[datetime, str]] = []
    first_record = last_record = None
    with fitdecode.FitReader(fit_path) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            fields = {field.name: field.value for field in frame.fields}
            ts = fields.get("timestamp")
            if ts is None:
                continue
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if frame.name == "record":
                if first_record is None:
                    first_record = ts
                last_record = ts
            if frame.name == "event" and str(fields.get("event")) == "timer":
                events.append((ts, _event_type_name(fields.get("event_type"))))
    intervals: list[tuple[datetime, datetime]] = []
    start = None
    for ts, event_type in events:
        if event_type == "start":
            start = ts
        elif event_type in {"stop", "stop_all"} and start is not None:
            intervals.append((start, ts))
            start = None
    if start is not None and last_record is not None:
        intervals.append((start, last_record))
    if not intervals and first_record is not None and last_record is not None:
        intervals = [(first_record, last_record)]
    return intervals


def apply_elapsed_timer(framemeta) -> None:
    fit_path = _fit_path_from_argv()
    intervals = _parse_timer_intervals(fit_path) if fit_path else []
    if not intervals:
        first_dt = None
        for pts in framemeta.framelist:
            first_dt = framemeta.frames[pts].dt
            break
        if first_dt is None:
            return

        def wall_updater(entry):
            dt = entry.dt
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            start = first_dt if first_dt.tzinfo else first_dt.replace(tzinfo=timezone.utc)
            seconds = max(0.0, (dt - start).total_seconds())
            return {"elapsed": units.Quantity(seconds, units.second)}

        framemeta.process(wall_updater)
        return

    def timer_seconds(dt: datetime) -> float:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        total = 0.0
        for start, stop in intervals:
            if dt <= start:
                break
            total += (min(dt, stop) - start).total_seconds()
        return max(0.0, total)

    def updater(entry):
        if entry.dt is None:
            return None
        return {"elapsed": units.Quantity(timer_seconds(entry.dt), units.second)}

    framemeta.process(updater)


def _load_weather_hours() -> list[tuple[datetime, float, float, float]]:
    path = os.environ.get("HUD_WEATHER_JSON")
    if not path or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    hours: list[tuple[datetime, float, float, float]] = []
    for row in payload.get("hours") or []:
        t = datetime.fromisoformat(row["t"])
        hours.append((t, float(row["temp"]), float(row["feels"]), float(row["rh"])))
    hours.sort(key=lambda item: item[0])
    return hours


def apply_weather(framemeta) -> None:
    hours = _load_weather_hours()
    if not hours:
        return

    def lookup(dt: datetime) -> tuple[float, float, float]:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        _stamp, temp, feels, rh = min(hours, key=lambda item: abs((item[0] - dt).total_seconds()))
        return temp, feels, rh

    def updater(entry):
        temp, feels, rh = lookup(entry.dt)
        return {
            "wx_temp": units.Quantity(temp, units.degC),
            "wx_feels": units.Quantity(feels, units.degC),
            "wx_rh": units.Quantity(rh, units.dimensionless),
        }

    framemeta.process(updater)


def _odo_km(entry) -> float | None:
    if entry.odo is None:
        return None
    try:
        return float(entry.odo.to(units.km).magnitude)
    except Exception:
        return None


def _max_odo_km(framemeta) -> float:
    total = 0.0
    for pts in framemeta.framelist:
        km = _odo_km(framemeta.frames[pts])
        if km is not None and km > total:
            total = km
    return total


def apply_shoe_odometer(framemeta) -> None:
    # 开跑前 = 跑完后累计 - 整场 FIT 总距离。
    # 不能用本段视频窗口的 max(odo)：那样每段都会在片尾顶到 -sk。
    raw_sk = os.environ.get("HUD_SHOE_TOTAL_KM_AFTER_RUN")
    if not raw_sk:
        return
    try:
        shoe_after = float(raw_sk)
    except ValueError:
        return
    raw_run = os.environ.get("HUD_SHOE_RUN_TOTAL_KM")
    run_total = None
    if raw_run:
        try:
            run_total = float(raw_run)
        except ValueError:
            run_total = None
    if run_total is None or run_total <= 0:
        full = getattr(framemeta, "full_route_meta", None) or framemeta
        run_total = _max_odo_km(full)
    shoe_before = max(0.0, shoe_after - run_total)

    def updater(entry):
        current = _odo_km(entry)
        if current is None:
            return None
        return {"shoe_odo": units.Quantity(shoe_before + current, units.km)}

    framemeta.process(updater)


def overlay_init(self, framemeta, *args, **kwargs):
    apply_weather(framemeta)
    apply_shoe_odometer(framemeta)
    apply_elapsed_timer(framemeta)
    _orig_overlay_init(self, framemeta, *args, **kwargs)


def quantity_formatter_for(format_string, dp):
    if format_string == "pace_quote":
        return lambda q: "{:d}′{:02d}″".format(*divmod(math.ceil(60.0 * q.m), 60))
    if format_string == "hms":
        def _hms(q):
            secs = int(max(0, round(float(q.m))))
            hours, rem = divmod(secs, 3600)
            minutes, seconds = divmod(rem, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}"

        return _hms
    return _orig_formatter(format_string, dp)


def gopro_dashboard_arguments(args=None):
    # gopro-overlay 禁止 --generate overlay 搭配 --use-fit-only。
    # 本工作流必须用 --use-fit-only 对齐视频 mtime，所以先拿掉 generate 让校验通过，再改回 overlay。
    argv = list(sys.argv[1:] if args is None else args)
    want_overlay = False
    filtered: list[str] = []
    skip_next = False
    for i, token in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if token == "--generate" and i + 1 < len(argv) and argv[i + 1] == "overlay":
            want_overlay = True
            skip_next = True
            continue
        if token.startswith("--generate=") and token.split("=", 1)[1] == "overlay":
            want_overlay = True
            continue
        filtered.append(token)
    parsed = _orig_arguments(filtered)
    if want_overlay:
        parsed.generate = "overlay"
    return parsed


# PIL 折线锯齿重：3 倍绘制再缩小，接头用 curve。
_ROUTE_SCALE = 3


def _draw_location_marker(draw, position, size: int = 6) -> None:
    # 小白瓷点，细褐边。比沙色路线亮一档，但不做成靶心。
    x, y = position
    draw.ellipse(
        [(x - size, y - size), (x + size, y + size)],
        fill=(255, 255, 255, 255),
        outline=(42, 26, 16, 255),
        width=2,
    )


def _outline_draw(self, draw, points):
    if len(points) < 2:
        return
    line_kw = {"joint": "curve"}
    if self.outline_width > 0:
        draw.line(points, fill=self.outline, width=self.fill_width, **line_kw)
    inner = max(1, self.fill_width - self.outline_width)
    draw.line(points, fill=self.fill, width=inner, **line_kw)


def _circuit_draw(self, image, draw):
    if self.image is None:
        journey = Journey()
        self.framemeta.process(journey.accept)
        self.bbox = journey.bounding_box
        self.size = self.bbox.size() * 1.1

        orig_dim = self.dimensions
        orig_fill = self.outline.fill_width
        orig_out = self.outline.outline_width
        self.dimensions = Dimension(orig_dim.x * _ROUTE_SCALE, orig_dim.y * _ROUTE_SCALE)
        self.outline.fill_width = orig_fill * _ROUTE_SCALE
        self.outline.outline_width = orig_out * _ROUTE_SCALE

        hi = Image.new("RGBA", self.dimensions.tuple(), (0, 0, 0, 0))
        hi_draw = ImageDraw.Draw(hi)
        points = [self.scale(p) for p in journey.locations if not self.privacy_zone.encloses(p)]
        self.outline.draw(hi_draw, rdp(points, 1))
        self.image = hi.resize(orig_dim.tuple(), Image.Resampling.LANCZOS)

        self.dimensions = orig_dim
        self.outline.fill_width = orig_fill
        self.outline.outline_width = orig_out

    location = self.location()
    frame = self.image.copy()
    frame_draw = ImageDraw.Draw(frame)
    if not self.privacy_zone.encloses(location):
        _draw_location_marker(frame_draw, self.scale(location), 7)
    image.alpha_composite(frame, (0, 0))


lx.quantity_formatter_for = quantity_formatter_for
lx.metric_accessor_from = metric_accessor_from
lx.Widgets.create_text = create_text
go_args.gopro_dashboard_arguments = gopro_dashboard_arguments
go_font.load_font = load_font
Overlay.__init__ = overlay_init
map_widgets.OutLine.draw = _outline_draw
map_widgets.Circuit.draw = _circuit_draw

dashboard = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "gopro-dashboard.py"
sys.argv = [str(dashboard), *sys.argv[1:]]
runpy.run_path(str(dashboard), run_name="__main__")
