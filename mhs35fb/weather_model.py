"""Shared weather data model and location constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

BEIJING_LAT = 39.9042
BEIJING_LON = 116.4074
CITY = "北京"


@dataclass
class Weather:
    city: str
    temperature: float
    high: float
    low: float
    humidity: int
    wind: str
    quality: str
    pm25: Optional[float]
    label: str
    kind: str
    is_day: bool
    updated: str
    fetched_at: str
    provider: str
