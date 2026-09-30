"""按跑步地点和时间拉小时天气：气温、体感、湿度。"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,apparent_temperature,relative_humidity_2m"


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "running-hud/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_hours(payload: dict) -> list[dict]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    feels = hourly.get("apparent_temperature") or []
    rhs = hourly.get("relative_humidity_2m") or []
    rows: list[dict] = []
    for t, temp, feel, rh in zip(times, temps, feels, rhs, strict=False):
        if temp is None or feel is None or rh is None:
            continue
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SHANGHAI)
        rows.append(
            {
                "t": dt.isoformat(),
                "temp": float(temp),
                "feels": float(feel),
                "rh": float(rh),
            }
        )
    return rows


def fetch_hourly_weather(lat: float, lon: float, start: datetime, end: datetime) -> list[dict]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start_d = start.astimezone(SHANGHAI).date().isoformat()
    end_d = end.astimezone(SHANGHAI).date().isoformat()
    query = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": start_d,
        "end_date": end_d,
        "hourly": HOURLY,
        "timezone": "Asia/Shanghai",
    }
    archive = f"{ARCHIVE_URL}?{urllib.parse.urlencode(query)}"
    try:
        rows = _parse_hours(_get_json(archive))
        if rows:
            return rows
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Open-Meteo archive failed: {exc}")
    forecast_q = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": HOURLY,
        "timezone": "Asia/Shanghai",
        "past_days": "14",
        "forecast_days": "1",
    }
    forecast = f"{FORECAST_URL}?{urllib.parse.urlencode(forecast_q)}"
    return _parse_hours(_get_json(forecast))


CITIES = {
    "shanghai": (31.2304, 121.4737),
}


def write_weather_json(path: Path, lat: float, lon: float, hours: list[dict]) -> None:
    path.write_text(
        json.dumps({"lat": lat, "lon": lon, "hours": hours}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_local(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI)
    return dt


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch hourly weather JSON without using FIT GPS.")
    parser.add_argument("--city", choices=sorted(CITIES), default="shanghai")
    parser.add_argument("--lat", type=float, help="Override city latitude")
    parser.add_argument("--lon", type=float, help="Override city longitude")
    parser.add_argument("--start", required=True, help="ISO datetime; naive values are Asia/Shanghai")
    parser.add_argument("--end", required=True, help="ISO datetime; naive values are Asia/Shanghai")
    parser.add_argument("--out", required=True, help="Write weather-hourly.json here")
    args = parser.parse_args()
    lat, lon = CITIES[args.city]
    if args.lat is not None:
        lat = args.lat
    if args.lon is not None:
        lon = args.lon
    hours = fetch_hourly_weather(lat, lon, parse_local(args.start), parse_local(args.end))
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    write_weather_json(out, lat, lon, hours)
    print(f"Wrote {len(hours)} hours to {out} ({lat:.4f},{lon:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
