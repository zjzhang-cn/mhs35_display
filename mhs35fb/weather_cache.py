"""Weather cache helpers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .weather_model import CITY, Weather


def cache_file() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "mhs35_weather.json"


def save_cache(weather: Weather) -> None:
    path = cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(weather), ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def load_cache() -> Optional[Weather]:
    try:
        payload = json.loads(cache_file().read_text(encoding="utf-8"))
        if payload.get("city") != CITY:
            return None
        return Weather(**payload)
    except (OSError, ValueError, TypeError):
        return None
