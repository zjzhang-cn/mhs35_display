"""Weather façade: providers, cache, display and the weather-only loop.

Provider implementations live in weather_providers.py, cartoon rendering in
weather_display.py, cache helpers in weather_cache.py and IP helpers in net.py.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from .render import DEFAULT_SIZE
from .weather_cache import cache_file, load_cache, save_cache
from .weather_display import render_offline, render_weather
from .weather_model import BEIJING_LAT, BEIJING_LON, CITY, Weather
from .weather_providers import (
    AIR_QUALITY_URL,
    CMA_STATION_ID,
    CMA_URL,
    ITBOY_URL,
    OPEN_METEO_URL,
    classify,
    fetch_air_quality,
    fetch_cma,
    fetch_itboy,
    fetch_open_meteo,
    fetch_weather,
)

__all__ = [
    "AIR_QUALITY_URL",
    "BEIJING_LAT",
    "BEIJING_LON",
    "CITY",
    "CMA_STATION_ID",
    "CMA_URL",
    "ITBOY_URL",
    "OPEN_METEO_URL",
    "Weather",
    "cache_file",
    "classify",
    "fetch_air_quality",
    "fetch_cma",
    "fetch_itboy",
    "fetch_open_meteo",
    "fetch_weather",
    "load_cache",
    "render_offline",
    "render_weather",
    "run",
    "save_cache",
]


def run(
    *,
    fb=None,
    width: int = DEFAULT_SIZE[0],
    height: int = DEFAULT_SIZE[1],
    provider: str = "auto",
    lat: float = BEIJING_LAT,
    lon: float = BEIJING_LON,
    timeout: int = 8,
    interval: int = 600,
    retry: int = 60,
    once: bool = False,
    preview: Optional[str] = None,
    font_path: Optional[str] = None,
    quiet: bool = False,
) -> int:
    last_good = load_cache()
    while True:
        warning = None
        try:
            weather = fetch_weather(provider=provider, lat=lat, lon=lon, timeout=timeout)
            last_good = weather
            save_cache(weather)
        except Exception as exc:  # noqa: BLE001 - keep showing the last frame
            warning = str(exc)
            weather = last_good

        if weather is None:
            image = render_offline(width, height, warning or "", font_path=font_path)
        else:
            image = render_weather(width, height, weather, font_path=font_path,
                                   stale=warning is not None, interval=interval)

        if preview:
            image.save(preview)
            if not quiet:
                print(f"preview saved: {preview} ({width}x{height})", flush=True)
            return 0

        fb.blit(image)
        if not quiet:
            status = f"{datetime.now():%H:%M:%S}  {weather.temperature:.0f}°C {weather.label}" if weather else "offline"
            if warning:
                status += "  [using cached data]"
            print(status, flush=True)
        if once:
            return 0

        time.sleep(retry if warning else interval)
