"""Weather façade: data model, providers and cache."""

from .weather_cache import cache_file, load_cache, save_cache
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
    "save_cache",
]
