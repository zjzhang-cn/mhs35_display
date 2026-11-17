"""Weather data providers and multi-source merging."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

from .weather_model import BEIJING_LAT, BEIJING_LON, CITY, Weather

CMA_URL = "http://weather.cma.cn/api/weather/view"
CMA_STATION_ID = "54511"  # 中国气象局北京站
ITBOY_URL = "http://t.weather.itboy.net/api/weather/city/101010100"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

_COMPASS = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")


def _parse_number(text) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(match.group()) if match else 0.0


def _clean_fl(value) -> str:
    return re.sub(r"<!\[CDATA\[|\]\]>", "", str(value or "")).strip()


def _is_day(sunrise: Optional[str], sunset: Optional[str]) -> bool:
    now = datetime.now()
    try:
        rise = tuple(int(part) for part in str(sunrise).split(":"))
        fall = tuple(int(part) for part in str(sunset).split(":"))
        now_minutes = now.hour * 60 + now.minute
        return rise[0] * 60 + rise[1] <= now_minutes < fall[0] * 60 + fall[1]
    except (TypeError, ValueError):
        return 6 <= now.hour < 18


def classify(label: str, is_day: bool) -> str:
    text = label or ""
    if "雷" in text:
        return "storm"
    if "雪" in text or "冰" in text:
        return "snow"
    if "雨" in text:
        return "rain"
    if "雾" in text or "霾" in text or "尘" in text or "沙" in text:
        return "fog"
    if "阴" in text:
        return "cloudy"
    if "多云" in text:
        return "partly" if is_day else "partly_night"
    if "晴" in text:
        return "sun" if is_day else "moon"
    if "风" in text:
        return "wind"
    return "cloudy"


def _short_update_time(text: str) -> str:
    match = re.match(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}:\d{2})", text)
    if not match:
        return text
    year, month, day, clock = match.groups()
    today = datetime.now()
    if (int(year), int(month), int(day)) == (today.year, today.month, today.day):
        return clock
    return f"{month}/{day} {clock}"


def fetch_cma(timeout: int = 8) -> Weather:
    url = f"{CMA_URL}?stationid={CMA_STATION_ID}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg", "cma request failed"))

    data = payload.get("data") or {}
    now = data.get("now") or {}
    daily = data.get("daily") or []
    if not daily:
        raise RuntimeError("cma response has no daily forecast")
    today = daily[0]
    if now.get("temperature") is None or now.get("humidity") is None:
        raise RuntimeError("cma response is missing current fields")
    if today.get("high") is None or today.get("low") is None:
        raise RuntimeError("cma response is missing daily temperatures")
    if not (today.get("dayText") or today.get("nightText")):
        raise RuntimeError("cma response is missing weather text")

    is_day = _is_day(None, None)
    label = str(
        (today.get("dayText") if is_day else today.get("nightText"))
        or today.get("dayText")
        or "未知"
    ).strip()
    humidity = int(_parse_number(now.get("humidity")))
    if not 0 <= humidity <= 100:
        humidity = 0
    location = data.get("location") or {}

    return Weather(
        city=str(location.get("name") or CITY).strip(),
        temperature=_parse_number(now.get("temperature")),
        high=_parse_number(today.get("high")),
        low=_parse_number(today.get("low")),
        humidity=humidity,
        wind=f"{now.get('windDirection', '')} {now.get('windScale', '')}".strip() or "—",
        quality="—",
        pm25=None,
        label=label,
        is_day=is_day,
        kind=classify(label, is_day),
        updated=_short_update_time(str(data.get("lastUpdate") or "—").strip()),
        fetched_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        provider="cma",
    )


def fetch_itboy(timeout: int = 8) -> Weather:
    request = urllib.request.Request(ITBOY_URL, headers={"User-Agent": "mhs35-dashboard/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("status") != 200:
        raise RuntimeError(payload.get("message", "itboy request failed"))

    data = payload.get("data") or {}
    forecasts = data.get("forecast") or []
    if not forecasts:
        raise RuntimeError("itboy response has no forecast")
    today = forecasts[0]

    label = str(today.get("type") or "未知").strip()
    is_day = _is_day(today.get("sunrise"), today.get("sunset"))
    try:
        humidity = int(float(str(data.get("shidu", "0")).rstrip("%")))
    except ValueError:
        humidity = 0
    try:
        pm25 = float(data.get("pm25"))
    except (TypeError, ValueError):
        pm25 = None
    wind = f"{today.get('fx', '')} {_clean_fl(today.get('fl'))}".strip() or "—"
    updated = str((payload.get("cityInfo") or {}).get("updateTime") or payload.get("time") or "—").strip()

    return Weather(
        city=CITY,
        temperature=_parse_number(data.get("wendu")),
        high=_parse_number(today.get("high")),
        low=_parse_number(today.get("low")),
        humidity=humidity,
        wind=wind,
        quality=str(data.get("quality") or "—").strip(),
        pm25=pm25,
        label=label,
        kind=classify(label, is_day),
        is_day=is_day,
        updated=updated,
        fetched_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        provider="itboy",
    )


def _describe_wmo(code: int, is_day: bool):
    if code == 0:
        return ("晴" if is_day else "晴夜", "sun" if is_day else "moon")
    if code in (1, 2):
        return ("晴间多云" if is_day else "夜间多云", "partly" if is_day else "partly_night")
    if code == 3:
        return ("阴", "cloudy")
    if code in (45, 48):
        return ("雾", "fog")
    if code in (51, 53, 55, 56, 57):
        return ("毛毛雨", "rain")
    if code in (61, 63, 65, 66, 67):
        return ("雨", "rain")
    if code in (71, 73, 75, 77, 85, 86):
        return ("雪", "snow")
    if code in (80, 81, 82):
        return ("阵雨", "rain")
    if code in (95, 96, 99):
        return ("雷雨", "storm")
    return ("未知", "cloudy")


def _wind_direction(degrees: float) -> str:
    return _COMPASS[int(((degrees % 360) + 22.5) // 45) % 8] + "风"


def fetch_open_meteo(lat: float = BEIJING_LAT, lon: float = BEIJING_LON, timeout: int = 8) -> Weather:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,relative_humidity_2m,is_day,weather_code,"
            "wind_speed_10m,wind_direction_10m"
        ),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "Asia/Shanghai",
        "forecast_days": 1,
        "wind_speed_unit": "kmh",
    }
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)

    current = payload["current"]
    daily = payload["daily"]
    is_day = bool(current.get("is_day", 1))
    label, kind = _describe_wmo(int(current.get("weather_code", -1)), is_day)

    return Weather(
        city=CITY,
        temperature=float(current["temperature_2m"]),
        high=float(daily["temperature_2m_max"][0]),
        low=float(daily["temperature_2m_min"][0]),
        humidity=int(current.get("relative_humidity_2m", 0)),
        wind=f"{_wind_direction(float(current.get('wind_direction_10m', 0)))} "
        f"{float(current.get('wind_speed_10m', 0)):.0f} km/h",
        quality="—",
        pm25=None,
        label=label,
        kind=kind,
        is_day=is_day,
        updated=str(current.get("time", "")).split("T")[-1] or "—",
        fetched_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        provider="open-meteo",
    )


def _quality_from_pm25(pm25: Optional[float]) -> str:
    if pm25 is None:
        return "—"
    for limit, label in (
        (35, "优"),
        (75, "良"),
        (115, "轻度污染"),
        (150, "中度污染"),
        (250, "重度污染"),
    ):
        if pm25 <= limit:
            return label
    return "严重污染"


def _fetch_open_meteo_air(
    lat: float = BEIJING_LAT,
    lon: float = BEIJING_LON,
    timeout: int = 8,
) -> tuple[Optional[float], str]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "pm2_5",
        "timezone": "Asia/Shanghai",
    }
    url = AIR_QUALITY_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "mhs35-dashboard/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    value = (payload.get("current") or {}).get("pm2_5")
    if value is None:
        return None, "—"
    pm25 = float(value)
    return pm25, _quality_from_pm25(pm25)


def fetch_air_quality(
    lat: float = BEIJING_LAT,
    lon: float = BEIJING_LON,
    timeout: int = 8,
    include_itboy: bool = True,
) -> tuple[Optional[float], str]:
    errors = []
    if include_itboy:
        try:
            weather = fetch_itboy(timeout)
            if weather.pm25 is not None:
                quality = weather.quality
                if not quality or quality == "—":
                    quality = _quality_from_pm25(weather.pm25)
                return weather.pm25, quality
            errors.append("itboy: no pm25")
        except Exception as exc:  # noqa: BLE001 - try the next air quality source
            errors.append(f"itboy: {exc}")

    try:
        return _fetch_open_meteo_air(lat, lon, timeout)
    except Exception as exc:  # noqa: BLE001 - report every air quality failure
        errors.append(f"open-meteo: {exc}")
    raise RuntimeError(" | ".join(errors))


def fetch_weather(
    *,
    provider: str = "auto",
    lat: float = BEIJING_LAT,
    lon: float = BEIJING_LON,
    timeout: int = 8,
) -> Weather:
    attempts = []
    if provider in ("auto", "cma"):
        attempts.append(("cma", lambda: fetch_cma(timeout)))
    if provider in ("auto", "itboy"):
        attempts.append(("itboy", lambda: fetch_itboy(timeout)))
    if provider in ("auto", "open-meteo"):
        attempts.append(("open-meteo", lambda: fetch_open_meteo(lat, lon, timeout)))

    errors = []
    for name, attempt in attempts:
        try:
            weather = attempt()
        except Exception as exc:  # noqa: BLE001 - report every provider failure
            errors.append(f"{name}: {exc}")
            continue

        if weather.pm25 is None:
            air_lat, air_lon = (lat, lon) if name == "open-meteo" else (BEIJING_LAT, BEIJING_LON)
            try:
                pm25, quality = fetch_air_quality(
                    air_lat, air_lon, timeout, include_itboy=(name != "itboy")
                )
            except Exception:  # noqa: BLE001 - air quality is optional
                pass
            else:
                if pm25 is not None:
                    weather.pm25 = pm25
                    weather.quality = quality
        return weather

    raise RuntimeError(" | ".join(errors))
