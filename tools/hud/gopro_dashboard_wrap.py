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

# ---------------------------------------------------------------------------
# Unified HUD typeface (ONE family for CJK + Latin — no dual-font mix).
#
# Prefer a heavier / slightly rounder athletic feel (old Noto Sans Black vibe),
# NOT the flat UI look of Noto CJK Bold / PingFang Regular.
#
# Mac production (preferred): Hiragino Sans GB W6 (冬青黑体简体 W6) — system,
#   CJK+Latin, bolder and a bit rounder than PingFang SC Regular/Medium.
# Mac alt: PingFang SC Semibold (heaviest common PingFang SC weight in TTC).
# Linux preview stand-in: Source Han Sans SC Heavy bundled under
#   tools/hud/fonts/ (Adobe — same design lineage as Noto CJK, Heavy ≈ Black).
#   Fallback: Noto Sans SC VF wght=900, then system Noto Sans CJK SC Bold.
#
# gopro-overlay --font path is overridden so every metric/text shares this face.
# ---------------------------------------------------------------------------

_HUD_DIR = Path(__file__).resolve().parent
_BUNDLED_HEAVY = _HUD_DIR / "fonts" / "SourceHanSansSC-Heavy.otf"
_BUNDLED_VF = _HUD_DIR / "fonts" / "NotoSansSC-VF.ttf"


def _ttc_face_names(path: Path) -> list[tuple[int, str, str]]:
    """Return [(index, family, subfamily)] for a TTC/TTF via the name table."""
    import struct

    data = path.read_bytes()
    if data[:4] == b"ttcf":
        num = struct.unpack(">I", data[8:12])[0]
        offsets = struct.unpack(f">{num}I", data[12 : 12 + 4 * num])
    else:
        offsets = (0,)

    faces: list[tuple[int, str, str]] = []
    for idx, offset in enumerate(offsets):
        _scaler, num_tables = struct.unpack(">4sH", data[offset : offset + 6])
        pos = offset + 12
        name_off = None
        name_len = 0
        for _ in range(num_tables):
            tag, _csum, off, length = struct.unpack(">4sIII", data[pos : pos + 16])
            pos += 16
            if tag == b"name":
                name_off, name_len = off, length
                break
        if name_off is None:
            faces.append((idx, "", ""))
            continue
        nd = data[name_off : name_off + name_len]
        _fmt, count, string_offset = struct.unpack(">HHH", nd[:6])
        names: dict[int, str] = {}
        for i in range(count):
            plat, enc, lang, name_id, length, soff = struct.unpack(
                ">HHHHHH", nd[6 + i * 12 : 6 + (i + 1) * 12]
            )
            raw = nd[string_offset + soff : string_offset + soff + length]
            text_val = None
            if plat == 3 and enc == 1:
                text_val = raw.decode("utf-16-be", errors="ignore")
            elif plat == 0:
                text_val = raw.decode("utf-16-be", errors="ignore")
            elif plat == 1 and enc == 0:
                text_val = raw.decode("mac-roman", errors="ignore")
            if text_val is None:
                continue
            if name_id not in names or (plat == 3 and lang == 0x409):
                names[name_id] = text_val
        family = names.get(16) or names.get(1) or ""
        sub = names.get(17) or names.get(2) or ""
        faces.append((idx, family, sub))
    return faces


def _pick_face(
    path: Path,
    family_needles: tuple[str, ...],
    prefer_subs: tuple[str, ...],
    exclude_needles: tuple[str, ...] = (),
) -> tuple[int, str] | None:
    try:
        faces = _ttc_face_names(path)
    except OSError:
        return None
    matched: list[tuple[int, int, str]] = []
    for idx, family, sub in faces:
        blob = f"{family} {sub}"
        if any(x.lower() in blob.lower() for x in exclude_needles):
            continue
        if not any(n.lower() in blob.lower() for n in family_needles):
            continue
        rank = len(prefer_subs)
        for i, pref in enumerate(prefer_subs):
            if pref.lower() in sub.lower() or pref.lower() in blob.lower():
                rank = i
                break
        label = f"{family} {sub}".strip() or path.name
        matched.append((rank, idx, label))
    if not matched:
        return None
    matched.sort()
    _rank, idx, label = matched[0]
    return idx, label


def resolve_hud_font() -> tuple[str, int, str, list[float] | None]:
    """Pick one CJK+Latin face. Returns (path, ttc_index, label, variation_axes|None)."""
    env_path = os.environ.get("HUD_FONT_PATH")
    env_index = os.environ.get("HUD_FONT_INDEX")
    env_wght = os.environ.get("HUD_FONT_WGHT")
    if env_path and Path(env_path).exists():
        idx = int(env_index) if env_index is not None else 0
        axes = [float(env_wght)] if env_wght else None
        return env_path, idx, f"env HUD_FONT_PATH ({Path(env_path).name}#{idx})", axes

    # Mac production: Hiragino Sans GB W6 (heavier / rounder than PingFang Regular)
    hira = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
    if hira.exists():
        picked = _pick_face(
            hira,
            family_needles=("Hiragino Sans GB", "冬青黑体"),
            prefer_subs=("W6", "W5", "W3"),
        )
        if picked:
            idx, label = picked
            return str(hira), idx, f"{label} [Mac production — heavy/rounder]", None
        return str(hira), 2, "Hiragino Sans GB#2 W6-ish [Mac production]", None

    # Mac alt: PingFang SC Semibold (heaviest typical SC weight in PingFang.ttc)
    for pf in (
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/PingFang.ttc"),
    ):
        if not pf.exists():
            continue
        picked = _pick_face(
            pf,
            family_needles=("PingFang SC", "苹方-简", "PingFangSC"),
            prefer_subs=("Semibold", "Medium", "Regular", "Bold"),
        )
        if picked:
            idx, label = picked
            return str(pf), idx, f"{label} [Mac alt — PingFang SC heavy]", None
        return str(pf), 0, "PingFang.ttc#0 [Mac alt]", None

    # Linux preview: Source Han Sans SC Heavy (bundled) ≈ athletic Black weight
    if _BUNDLED_HEAVY.exists():
        return (
            str(_BUNDLED_HEAVY),
            0,
            "Source Han Sans SC Heavy [Linux preview ≈ Hiragino GB W6 / Black]",
            None,
        )

    # Linux alt: Noto Sans SC variable at Black (900)
    if _BUNDLED_VF.exists():
        return (
            str(_BUNDLED_VF),
            0,
            "Noto Sans SC VF wght=900 [Linux preview alt]",
            [900.0],
        )

    # Last resort: system Noto CJK SC Bold (flatter UI look)
    for noto in (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ):
        if not noto.exists():
            continue
        picked = _pick_face(
            noto,
            family_needles=("Noto Sans CJK SC",),
            prefer_subs=("Bold", "Regular"),
            exclude_needles=("Mono",),
        )
        if picked:
            idx, label = picked
            return str(noto), idx, f"{label} [Linux last-resort — flatter than Heavy]", None
        return str(noto), 2, f"{noto.name}#2 [Linux last-resort]", None

    raise OSError(
        "No unified CJK+Latin HUD font found. On Mac use Hiragino Sans GB / "
        "PingFang SC; on Linux place SourceHanSansSC-Heavy.otf under tools/hud/fonts/ "
        "or set HUD_FONT_PATH."
    )


HUD_FONT_PATH, HUD_FONT_INDEX, HUD_FONT_LABEL, HUD_FONT_AXES = resolve_hud_font()
_hud_font_logged = False


def _load_hud_face(size: int):
    loaded = ImageFont.truetype(font=HUD_FONT_PATH, size=size, index=HUD_FONT_INDEX)
    if HUD_FONT_AXES and hasattr(loaded, "set_variation_by_axes"):
        try:
            loaded.set_variation_by_axes(list(HUD_FONT_AXES))
        except OSError:
            pass
    return loaded


def load_font(font: str, size: int = 32):
    """Always load the unified HUD face (path + TTC index + optional wght axis)."""
    global _hud_font_logged
    if not _hud_font_logged:
        print(f"HUD font (unified CJK+Latin, heavier): {HUD_FONT_LABEL}")
        print(f"  file: {HUD_FONT_PATH}  index={HUD_FONT_INDEX}  axes={HUD_FONT_AXES}")
        _hud_font_logged = True

    loaded = _load_hud_face(size)

    def font_variant(*args, **kwargs):
        new_size = size
        if args:
            new_size = args[0]
        new_size = kwargs.get("size", new_size)
        return _load_hud_face(int(new_size))

    loaded.font_variant = font_variant
    return loaded



def create_text(self, element, entry, **kwargs):
    """Weather value composites (right-aligned inside pills). Labels stay plain left text."""
    name = element.attrib.get("name", "")
    if name not in ("wx_env_values", "wx_body_values"):
        return _orig_create_text(self, element, entry, **kwargs)

    font = self._font(element, "size", d=14)

    def env_values():
        e = entry()
        temp = getattr(e, "wx_temp", None)
        rh = getattr(e, "wx_rh", None)
        t_s = "-" if temp is None else f"{int(round(float(temp.m)))}"
        r_s = "-" if rh is None else f"{int(round(float(rh.m)))}"
        return f"{r_s}% · {t_s}°"

    def body_values():
        e = entry()
        feels = getattr(e, "wx_feels", None)
        f_s = "-" if feels is None else f"{int(round(float(feels.m)))}"
        return f"{f_s}°"

    return text_widget(
        at=lx.at(element),
        value=env_values if name == "wx_env_values" else body_values,
        font=font,
        align=lx.attrib(element, "align", d="right"),
        direction=lx.attrib(element, "direction", d="ltr"),
        fill=lx.rgbattr(element, "rgb", d=(255, 255, 255)),
        stroke=lx.rgbattr(element, "outline", d=(0, 0, 0)),
        stroke_width=lx.iattrib(element, "outline_width", d=2),
    )


def metric_accessor_from(name: str):
    extra = {
        "wx_temp": lambda e: getattr(e, "wx_temp", None),
        "wx_feels": lambda e: getattr(e, "wx_feels", None),
        "wx_rh": lambda e: getattr(e, "wx_rh", None),
        "elapsed": lambda e: getattr(e, "elapsed", None),
        "shoe_odo": lambda e: getattr(e, "shoe_odo", None),
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
    drop_value_flags = {
        "--shoe-name",
        "--shoe-total-km-after-run",
        "-sn",
        "-sk",
    }
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
        # render_running_hud 会透传鞋参数；真值走环境变量 / 已解析 XML，不进 stock CLI
        if token in drop_value_flags:
            skip_next = True
            continue
        if any(token.startswith(f"{flag}=") for flag in drop_value_flags):
            continue
        filtered.append(token)
    parsed = _orig_arguments(filtered)
    if want_overlay:
        parsed.generate = "overlay"
    return parsed


# PIL 折线锯齿重：3 倍绘制再缩小，接头用 curve。
_ROUTE_SCALE = 3


def _draw_location_marker(draw, position, size: int = 12) -> None:
    # 白瓷圆点，褐边。loc-size 是半径（像素）。线宽约 10，点要比线明显更大。
    x, y = position
    outline_w = 3 if size >= 11 else 2
    draw.ellipse(
        [(x - size, y - size), (x + size, y + size)],
        fill=(255, 255, 255, 255),
        outline=(42, 26, 16, 255),
        width=outline_w,
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
        _draw_location_marker(frame_draw, self.scale(location), getattr(self, "_hud_marker_size", 12))
    image.alpha_composite(frame, (0, 0))


class _CircleKnobBar:
    """进度条末端画实心圆，而不是 Bar 自带的 5% 高亮方头。"""

    def __init__(self, bar, diameter: int, fill, outline):
        self.bar = bar
        self.diameter = diameter
        self.fill = fill
        self.outline = outline

    def draw(self, image, draw):
        self.bar.draw(image, draw)
        cx = self.bar.x_coord(self.bar.reading())
        cy = self.bar.size.y / 2
        radius = self.diameter / 2
        draw.ellipse(
            [(cx - radius, cy - radius), (cx + radius, cy + radius)],
            fill=self.fill,
            outline=self.outline,
            width=2,
        )


_orig_create_bar = lx.Widgets.create_bar
_orig_create_circuit_map = lx.Widgets.create_circuit_map


def create_bar(self, element, entry, **kwargs):
    knob = element.attrib.pop("knob", None)
    knob_size = element.attrib.pop("knob-size", None)
    try:
        bar = _orig_create_bar(self, element, entry, **kwargs)
    finally:
        if knob is not None:
            element.attrib["knob"] = knob
        if knob_size is not None:
            element.attrib["knob-size"] = knob_size
    if knob != "circle":
        return bar
    diameter = int(knob_size) if knob_size else 18
    return _CircleKnobBar(bar, diameter, (255, 255, 255, 255), (42, 26, 16, 255))


def create_circuit_map(self, element, entry, **kwargs):
    raw = element.attrib.pop("loc-size", None)
    try:
        widget = _orig_create_circuit_map(self, element, entry, **kwargs)
    finally:
        if raw is not None:
            element.attrib["loc-size"] = raw
    widget._hud_marker_size = int(raw) if raw else 12
    return widget


lx.Widgets.create_bar = create_bar
lx.Widgets.create_circuit_map = create_circuit_map
lx.Widgets.create_text = create_text
lx.quantity_formatter_for = quantity_formatter_for
lx.metric_accessor_from = metric_accessor_from
go_args.gopro_dashboard_arguments = gopro_dashboard_arguments
go_font.load_font = load_font
Overlay.__init__ = overlay_init
map_widgets.OutLine.draw = _outline_draw
map_widgets.Circuit.draw = _circuit_draw

dashboard = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "gopro-dashboard.py"
sys.argv = [str(dashboard), *sys.argv[1:]]
runpy.run_path(str(dashboard), run_name="__main__")
