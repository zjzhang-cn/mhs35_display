"""Cartoon weather scenes and panel rendering."""

from __future__ import annotations

import math
import random
import re
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw

from .render import draw_text, gradient, render as render_text
from .weather_model import Weather

_DAWN_PALETTES = {
    "sun": ("#F6A77B", "#FFE1C4"),
    "partly": ("#E89A8C", "#FFD8C2"),
    "cloudy": ("#B49A9A", "#EAD9D2"),
    "rain": ("#8C7E96", "#C7B9C7"),
    "storm": ("#5E4B6B", "#9A7F9C"),
    "snow": ("#C9A9B4", "#F5E6EA"),
    "fog": ("#A9929B", "#E4D6D7"),
    "wind": ("#D99A86", "#FFE0CC"),
}

_DAY_PALETTES = {
    "sun": ("#57BDF5", "#D7F3FF"),
    "partly": ("#6CC4F2", "#DDF5FF"),
    "cloudy": ("#8AA7C2", "#D6E4EF"),
    "rain": ("#6D88A8", "#B9CFDF"),
    "storm": ("#4A5A78", "#8B9DB8"),
    "snow": ("#7FA8CB", "#E9F6FF"),
    "fog": ("#9AAAB8", "#DCE6EC"),
    "wind": ("#7EC8E3", "#E0F5FC"),
}

_DUSK_PALETTES = {
    "sun": ("#FF7E5F", "#FEB47B"),
    "partly": ("#D96C7E", "#F8B195"),
    "cloudy": ("#6C5B7B", "#C06C84"),
    "rain": ("#4B3F5E", "#8E6C88"),
    "storm": ("#2E2238", "#6A4C6D"),
    "snow": ("#7A6A8A", "#D8C7D8"),
    "fog": ("#7D6B7A", "#C9B8C2"),
    "wind": ("#B56576", "#EAAC8B"),
}

_NIGHT_PALETTES = {
    "moon": ("#1B2A4A", "#40587F"),
    "partly_night": ("#1D2C4E", "#4A628C"),
    "cloudy": ("#26344F", "#5A6E8C"),
    "rain": ("#1F2C44", "#50647F"),
    "storm": ("#1A2238", "#41506E"),
    "snow": ("#25384E", "#7188A0"),
    "fog": ("#2C394C", "#66788C"),
    "wind": ("#1E3348", "#536B84"),
}

_GROUND_COLORS = {
    "dawn": "#5B7F57",
    "day": "#6FBF63",
    "dusk": "#456B47",
    "night": "#2E4A3A",
}


def _parse_clock(text: str) -> Optional[int]:
    match = re.search(r"(\d{1,2}):(\d{2})", str(text or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _time_slot(weather: Optional[Weather] = None, now: Optional[datetime] = None) -> str:
    current = now or datetime.now()
    minutes = current.hour * 60 + current.minute
    sunrise = _parse_clock(weather.sunrise) if weather else None
    sunset = _parse_clock(weather.sunset) if weather else None
    if sunrise is not None and sunset is not None and sunrise < sunset:
        if minutes < sunrise - 60 or minutes >= sunset + 60:
            return "night"
        if minutes < sunrise + 60:
            return "dawn"
        if minutes < sunset - 60:
            return "day"
        return "dusk"
    if 5 <= current.hour < 8:
        return "dawn"
    if 8 <= current.hour < 17:
        return "day"
    if 17 <= current.hour < 20:
        return "dusk"
    return "night"


def _scene_kind(kind: str, slot: str) -> str:
    if slot == "night":
        return {"sun": "moon", "partly": "partly_night"}.get(kind, kind)
    return {"moon": "sun", "partly_night": "partly"}.get(kind, kind)


def _palette(kind: str, slot: str):
    table = {
        "dawn": _DAWN_PALETTES,
        "day": _DAY_PALETTES,
        "dusk": _DUSK_PALETTES,
        "night": _NIGHT_PALETTES,
    }[slot]
    return table.get(kind, table["cloudy"])


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
) -> Image.Image:
    slot = _time_slot(weather)
    kind = _scene_kind(weather.kind, slot)
    top, bottom = _palette(kind, slot)
    canvas = gradient((width, height), top, bottom)
    draw = ImageDraw.Draw(canvas)

    if slot == "night":
        _stars(draw, width)

    ground = _GROUND_COLORS[slot]
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

    shadow = "#1F3A52" if slot in ("dawn", "day") else "#0B1220"
    draw_text(canvas, (18, 10), weather.city, 27, "#FFFFFF", font_path=font_path,
              shadow=shadow, shadow_offset=(2, 2))
    draw_text(canvas, (width - 18, int(height * 0.09)), f"{weather.temperature:.1f}°", 58,
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

    air_parts = []
    if weather.quality and weather.quality != "—":
        air_parts.append(f"空气 {weather.quality}")
    if weather.pm25 is not None:
        air_parts.append(f"PM2.5 {weather.pm25:.0f}")
    wind_line = weather.wind
    if air_parts:
        wind_line += "   " + " · ".join(air_parts)
    lines = [
        f"最高 {weather.high:.0f}°C   最低 {weather.low:.0f}°C   湿度 {weather.humidity}%",
        wind_line,
    ]
    if stale:
        lines.append(f"离线 · 上次 {weather.updated}")
    else:
        lines.append(f"更新 {weather.updated} · 每 {_format_interval(interval)}刷新")

    return _panel(canvas, 8, panel_y, panel_w, panel_h, lines, font_path)


def render_offline(width: int, height: int, message: str = "", font_path: Optional[str] = None) -> Image.Image:
    canvas = gradient((width, height), "#8A9BAE", "#D7E0E6")
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((-90, int(height * 0.46), width + 90, height + 120), fill="#7C8B99")
    _cloud(draw, width // 2, int(height * 0.26), 1.15, face=True, mood="sad")

    lines = ["天气获取失败", "检查网络后会自动重试"]
    if message:
        short = " ".join(message.split())[:48]
        lines.append(short)

    panel_y = int(height * 0.55)
    panel_h = height - panel_y - 8
    return _panel(canvas, 8, panel_y, width - 16, panel_h, lines, font_path)
