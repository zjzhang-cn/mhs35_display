"""Beijing weather fetching and cartoon rendering for the MHS35 panel."""

from __future__ import annotations

import json
import math
import os
import random
import re
import socket
import struct
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux-only helper
    fcntl = None

from PIL import Image, ImageColor, ImageDraw

from .render import DEFAULT_SIZE, draw_text, gradient, render as render_text

ITBOY_URL = "http://t.weather.itboy.net/api/weather/city/101010100"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

BEIJING_LAT = 39.9042
BEIJING_LON = 116.4074
CITY = "北京"

_COMPASS = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")


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


def fetch_itboy(timeout: int = 8) -> Weather:
    request = urllib.request.Request(ITBOY_URL, headers={"User-Agent": "mhs35-weather/1.0"})
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


def fetch_weather(
    *,
    provider: str = "auto",
    lat: float = BEIJING_LAT,
    lon: float = BEIJING_LON,
    timeout: int = 8,
) -> Weather:
    attempts = []
    if provider in ("auto", "itboy"):
        attempts.append(("itboy", lambda: fetch_itboy(timeout)))
    if provider in ("auto", "open-meteo"):
        attempts.append(("open-meteo", lambda: fetch_open_meteo(lat, lon, timeout)))

    errors = []
    for name, attempt in attempts:
        try:
            return attempt()
        except Exception as exc:  # noqa: BLE001 - report every provider failure
            errors.append(f"{name}: {exc}")
    raise RuntimeError(" | ".join(errors))


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


def _palette(kind: str, is_day: bool):
    if not is_day:
        return {
            "moon": ("#1B2A4A", "#40587F"),
            "partly_night": ("#1D2C4E", "#4A628C"),
            "cloudy": ("#26344F", "#5A6E8C"),
            "rain": ("#1F2C44", "#50647F"),
            "storm": ("#1A2238", "#41506E"),
            "snow": ("#25384E", "#7188A0"),
            "fog": ("#2C394C", "#66788C"),
            "wind": ("#1E3348", "#536B84"),
        }.get(kind, ("#1B2A4A", "#40587F"))
    return {
        "sun": ("#57BDF5", "#D7F3FF"),
        "partly": ("#6CC4F2", "#DDF5FF"),
        "cloudy": ("#8AA7C2", "#D6E4EF"),
        "rain": ("#6D88A8", "#B9CFDF"),
        "storm": ("#4A5A78", "#8B9DB8"),
        "snow": ("#7FA8CB", "#E9F6FF"),
        "fog": ("#9AAAB8", "#DCE6EC"),
        "wind": ("#7EC8E3", "#E0F5FC"),
    }.get(kind, ("#66BFF0", "#DDF3FF"))


def _face(draw, cx, cy, radius, *, mood: str = "happy"):
    radius = int(radius)
    eye_dx = max(6, radius // 3)
    eye_r = max(2, radius // 8)
    eye_y = cy - radius // 8
    draw.ellipse((cx - eye_dx - eye_r, eye_y - eye_r, cx - eye_dx + eye_r, eye_y + eye_r), fill="#4E342E")
    draw.ellipse((cx + eye_dx - eye_r, eye_y - eye_r, cx + eye_dx + eye_r, eye_y + eye_r), fill="#4E342E")

    smile_width = max(2, radius // 10)
    if mood == "sad":
        draw.arc((cx - radius // 2, cy + radius // 6, cx + radius // 2, cy + radius // 2 + 6),
                 start=200, end=340, fill="#4E342E", width=smile_width)
    else:
        draw.arc((cx - radius // 2, cy - radius // 10, cx + radius // 2, cy + radius // 2),
                 start=20, end=160, fill="#4E342E", width=smile_width)

    cheek_r = max(3, radius // 6)
    cheek_y = eye_y + max(4, radius // 5)
    draw.ellipse((cx - eye_dx * 2 - cheek_r, cheek_y, cx - eye_dx * 2 + cheek_r, cheek_y + cheek_r * 2),
                 fill="#FFAB91")
    draw.ellipse((cx + eye_dx * 2 - cheek_r, cheek_y, cx + eye_dx * 2 + cheek_r, cheek_y + cheek_r * 2),
                 fill="#FFAB91")


def _sun(draw, cx, cy, radius, face: bool = True):
    for index in range(12):
        angle = math.tau * index / 12
        draw.line(
            (
                cx + math.cos(angle) * (radius + 7),
                cy + math.sin(angle) * (radius + 7),
                cx + math.cos(angle) * (radius + 18),
                cy + math.sin(angle) * (radius + 18),
            ),
            fill="#FFC107",
            width=4,
        )
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill="#FFD54F", outline="#F9A825", width=3)
    if face:
        _face(draw, cx, cy, radius)


def _moon(draw, cx, cy, radius, face: bool = True):
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill="#FFE082", outline="#FFC107", width=3)
    if face:
        _face(draw, cx, cy, radius)


def _cloud(draw, cx, cy, scale: float = 1.0, face: bool = True, mood: str = "happy"):
    color = "#FFFFFF"
    outline = "#B0BEC5"
    circles = ((-44, 6, 24), (-18, -12, 30), (14, -16, 32), (44, 0, 24), (2, 8, 28))
    base = (-54, 2, 58, 34)

    for dx, dy, radius in circles:
        draw.ellipse(
            (cx + (dx - radius) * scale, cy + (dy - radius) * scale,
             cx + (dx + radius) * scale, cy + (dy + radius) * scale),
            fill=outline,
        )
    draw.rounded_rectangle(
        (cx + base[0] * scale, cy + base[1] * scale,
         cx + base[2] * scale, cy + base[3] * scale),
        radius=int(16 * scale), fill=outline,
    )

    inset = 3
    for dx, dy, radius in circles:
        draw.ellipse(
            (cx + (dx - radius + inset) * scale, cy + (dy - radius + inset) * scale,
             cx + (dx + radius - inset) * scale, cy + (dy + radius - inset) * scale),
            fill=color,
        )
    draw.rounded_rectangle(
        (cx + (base[0] + inset) * scale, cy + (base[1] + inset) * scale,
         cx + (base[2] - inset) * scale, cy + (base[3] - inset) * scale),
        radius=max(2, int(13 * scale)), fill=color,
    )

    if face:
        _face(draw, cx + 2 * scale, cy + 8 * scale, 30 * scale, mood=mood)


def _rain(draw, cx, cy, count: int = 7):
    for index in range(count):
        x = cx - 44 + index * 14
        y = cy + 38 + (index % 3) * 13
        draw.polygon([(x - 4, y + 3), (x, y - 6), (x + 4, y + 3)], fill="#4FC3F7")
        draw.ellipse((x - 3, y, x + 3, y + 13), fill="#4FC3F7", outline="#0288D1")


def _snowflake(draw, x, y, radius):
    for angle in (0, math.pi / 3, 2 * math.pi / 3):
        dx = math.cos(angle) * radius
        dy = math.sin(angle) * radius
        draw.line((x - dx, y - dy, x + dx, y + dy), fill="#FFFFFF", width=2)


def _snow(draw, cx, cy, count: int = 8):
    rng = random.Random(7)
    for index in range(count):
        x = cx - 56 + index * 15 + rng.randint(-4, 4)
        y = cy + 34 + rng.randint(0, 36)
        _snowflake(draw, x, y, rng.choice((4, 5, 6)))


def _lightning(draw, cx, cy):
    draw.polygon(
        (
            (cx + 16, cy + 26),
            (cx, cy + 64),
            (cx + 14, cy + 64),
            (cx - 4, cy + 104),
            (cx + 32, cy + 56),
            (cx + 16, cy + 56),
        ),
        fill="#FFD54F",
        outline="#F9A825",
    )


def _fog_lines(draw, cx, cy):
    for index, offset in enumerate((16, 34, 52)):
        x0 = cx - 58 + (6 if index % 2 else 0)
        x1 = cx + 58 - (6 if index % 2 else 0)
        draw.rounded_rectangle((x0, cy + offset, x1, cy + offset + 9), radius=5, fill="#ECEFF1")


def _wind_lines(draw, cx, cy):
    for index, offset in enumerate((34, 50, 66)):
        draw.arc((cx - 62 + index * 8, cy + offset - 10, cx + 40 + index * 8, cy + offset + 10),
                 start=200, end=340, fill="#FFFFFF", width=3)
        draw.ellipse((cx + 38 + index * 8, cy + offset - 4, cx + 44 + index * 8, cy + offset + 2),
                     fill="#FFFFFF")


def _stars(draw, width):
    rng = random.Random(11)
    for _ in range(26):
        x = rng.randint(10, width - 10)
        y = rng.randint(8, 138)
        radius = rng.choice((1, 1, 2))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#FFF8E1")


def _format_interval(seconds: int) -> str:
    if seconds % 60 == 0 and seconds >= 60:
        return f"{seconds // 60} 分钟"
    return f"{seconds} 秒"


def _interface_addresses():
    if fcntl is None:
        return []
    addresses = []
    for _, name in socket.if_nameindex():
        if name == "lo" or name.startswith(("docker", "veth", "br-")):
            continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            request = struct.pack("256s", name[:15].encode("utf-8"))
            result = fcntl.ioctl(sock.fileno(), 0x8915, request)
            address = socket.inet_ntoa(result[20:24])
        except OSError:
            continue
        finally:
            sock.close()
        if address and not address.startswith("127."):
            addresses.append((name, address))
    return addresses


def _default_route_ip():
    for target in (("8.8.8.8", 80), ("223.5.5.5", 80)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(target)
            return sock.getsockname()[0]
        except OSError:
            pass
        finally:
            sock.close()
    return None


def local_ip():
    addresses = _interface_addresses()
    default = _default_route_ip()
    if default and not default.startswith("127."):
        for name, address in addresses:
            if address == default:
                return address, name
        return default, ""
    if addresses:
        addresses.sort(key=lambda item: (0 if item[0] in ("eth0", "wlan0") else 1, item[0]))
        name, address = addresses[0]
        return address, name
    return None, None


def ip_line() -> str:
    address, interface = local_ip()
    if not address:
        return "IP 未获取"
    return f"IP {address} ({interface})" if interface else f"IP {address}"


def _panel(canvas: Image.Image, x: int, y: int, width: int, height: int, lines, font_path):
    panel = render_text(
        width,
        height,
        lines,
        bg="#FFFFFF",
        fg="#263238",
        font_path=font_path,
        font_size=max(16, int(height * 0.19)),
        align="left",
        valign="middle",
        line_spacing=0.22,
        margin=16,
    )
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=18, fill=255)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x + 2, y + 5, x + width + 2, y + height + 5), radius=18, fill=(0, 0, 0, 65)
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
    canvas.paste(panel, (x, y), mask)
    return canvas


def render_weather(
    width: int,
    height: int,
    weather: Weather,
    *,
    font_path: Optional[str] = None,
    stale: bool = False,
    interval: int = 600,
    show_ip: bool = True,
) -> Image.Image:
    kind = weather.kind
    top, bottom = _palette(kind, weather.is_day)
    canvas = gradient((width, height), top, bottom)
    draw = ImageDraw.Draw(canvas)

    if not weather.is_day:
        _stars(draw, width)

    ground = "#6FBF63" if weather.is_day else "#2E4A3A"
    draw.ellipse((-90, int(height * 0.46), width + 90, height + 120), fill=ground)

    cx = int(width * 0.33)
    cy = int(height * 0.27)
    if kind == "sun":
        _sun(draw, cx, cy, 32)
    elif kind == "moon":
        _moon(draw, cx, cy, 32)
    elif kind == "partly":
        _sun(draw, cx - 28, cy - 10, 24)
        _cloud(draw, cx + 38, cy + 12, 0.82)
    elif kind == "partly_night":
        _moon(draw, cx - 28, cy - 10, 24)
        _cloud(draw, cx + 38, cy + 12, 0.82)
    elif kind == "rain":
        _cloud(draw, cx, cy - 4, 1.0)
        _rain(draw, cx, cy)
    elif kind == "storm":
        _cloud(draw, cx, cy - 4, 1.0, face=False)
        _lightning(draw, cx + 8, cy)
    elif kind == "snow":
        _cloud(draw, cx, cy - 4, 1.0)
        _snow(draw, cx, cy)
    elif kind == "fog":
        _cloud(draw, cx, cy - 10, 0.95)
        _fog_lines(draw, cx, cy)
    elif kind == "wind":
        _cloud(draw, cx - 14, cy - 4, 0.9)
        _wind_lines(draw, cx + 26, cy - 6)
    else:
        _cloud(draw, cx, cy, 1.0)
        _cloud(draw, cx + 74, cy - 24, 0.55, face=False)

    shadow = "#1F3A52" if weather.is_day else "#0B1220"
    draw_text(canvas, (18, 10), weather.city, 27, "#FFFFFF", font_path=font_path,
              shadow=shadow, shadow_offset=(2, 2))
    draw_text(canvas, (width - 18, int(height * 0.09)), f"{weather.temperature:.0f}°", 58,
              "#FFFFFF", font_path=font_path, align="right", shadow=shadow, shadow_offset=(3, 3))
    draw_text(canvas, (width - 18, int(height * 0.31)), weather.label, 25, "#FFFFFF",
              font_path=font_path, align="right", shadow=shadow, shadow_offset=(2, 2))

    if stale:
        badge = "离线 · 上次数据"
        scratch = Image.new("RGB", (1, 1))
        badge_width, _ = draw_text(scratch, (0, 0), badge, 14, "#FFFFFF", font_path=font_path)
        right = width - 10
        badge_y = int(height * 0.43)
        draw.rounded_rectangle((right - badge_width - 14, badge_y - 3, right, badge_y + 21),
                               radius=8, fill="#EF6C00")
        draw_text(canvas, (right - 7, badge_y + 1), badge, 14, "#FFFFFF",
                  font_path=font_path, align="right")

    panel_y = int(height * 0.55)
    panel_h = height - panel_y - 8
    panel_w = width - 16

    air = f"空气 {weather.quality}"
    if weather.pm25 is not None:
        air += f" · PM2.5 {weather.pm25:.0f}"
    lines = [
        f"最高 {weather.high:.0f}°C   最低 {weather.low:.0f}°C   湿度 {weather.humidity}%",
        f"{weather.wind}   {air}",
    ]
    if show_ip:
        lines.append(ip_line())
    if stale:
        lines.append(f"离线 · 上次 {weather.updated}")
    else:
        lines.append(f"更新 {weather.updated} · 每 {_format_interval(interval)}刷新")

    return _panel(canvas, 8, panel_y, panel_w, panel_h, lines, font_path)


def render_offline(width: int, height: int, message: str = "", font_path: Optional[str] = None,
                   show_ip: bool = True) -> Image.Image:
    canvas = gradient((width, height), "#8A9BAE", "#D7E0E6")
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((-90, int(height * 0.46), width + 90, height + 120), fill="#7C8B99")
    _cloud(draw, width // 2, int(height * 0.26), 1.15, face=True, mood="sad")

    lines = ["天气获取失败", "检查网络后会自动重试"]
    if show_ip:
        lines.append(ip_line())
    if message:
        short = " ".join(message.split())[:48]
        lines.append(short)

    panel_y = int(height * 0.55)
    panel_h = height - panel_y - 8
    return _panel(canvas, 8, panel_y, width - 16, panel_h, lines, font_path)


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
