"""Dashboard cards for the MHS35 panel: weather, clock/calendar, host info."""

from __future__ import annotations

import calendar
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from .render import draw_text, gradient
from .weather import Weather, local_ip, render_offline, render_weather

BOTTOM_STRIP = 14
CARD_NAMES = ("天气", "时间日历", "主机信息")
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _white_panel(canvas: Image.Image, x: int, y: int, width: int, height: int, radius: int = 18):
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x + 2, y + 5, x + width + 2, y + height + 5), radius=radius, fill=(0, 0, 0, 60)
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
    ImageDraw.Draw(canvas).rounded_rectangle((x, y, x + width, y + height), radius=radius, fill="#FFFFFF")
    return canvas


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _cpu_temperature() -> Optional[float]:
    text = _read("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(text) / 1000.0
    except (TypeError, ValueError):
        return None


def _memory():
    values = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if key and parts:
            try:
                values[key] = int(parts[0])
            except ValueError:
                continue
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return max(0, total - available) * 1024, total * 1024


def _disk():
    stats = os.statvfs("/")
    total = stats.f_blocks * stats.f_frsize
    free = stats.f_bavail * stats.f_frsize
    return max(0, total - free), total


def _uptime() -> str:
    parts = _read("/proc/uptime").split()
    try:
        seconds = int(float(parts[0]))
    except (IndexError, ValueError):
        return "—"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days}天 {hours:02d}小时"
    if hours:
        return f"{hours}小时 {minutes:02d}分"
    return f"{minutes}分"


def _gb(value: int) -> float:
    return value / (1024 ** 3)


def collect_host_info() -> dict:
    address, interface = local_ip()
    if address and interface:
        ip_text = f"{address} ({interface})"
    else:
        ip_text = address or "未获取"

    temperature = _cpu_temperature()
    if temperature is None:
        temperature_text = "—"
        temperature_color = "#263238"
    else:
        temperature_text = f"{temperature:.1f} °C"
        if temperature >= 70:
            temperature_color = "#C62828"
        elif temperature >= 55:
            temperature_color = "#EF6C00"
        else:
            temperature_color = "#2E7D32"

    memory_used, memory_total = _memory()
    disk_used, disk_total = _disk()
    load = os.getloadavg()

    return {
        "hostname": f"{platform.node()} · {os.cpu_count()} 核",
        "ip": ip_text,
        "kernel": platform.release(),
        "temperature": temperature_text,
        "temperature_color": temperature_color,
        "load": f"{load[0]:.2f}  {load[1]:.2f}  {load[2]:.2f}",
        "memory": f"{_gb(memory_used):.1f} / {_gb(memory_total):.1f} GB   "
        f"{100 * memory_used / memory_total if memory_total else 0:.0f}%",
        "memory_pct": 100 * memory_used / memory_total if memory_total else 0,
        "disk": f"{_gb(disk_used):.1f} / {_gb(disk_total):.1f} GB   "
        f"{100 * disk_used / disk_total if disk_total else 0:.0f}%",
        "disk_pct": 100 * disk_used / disk_total if disk_total else 0,
        "uptime": _uptime(),
    }


def _clock_icon(draw, cx: int, cy: int, radius: int):
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill="#FFFFFF", outline="#FFB74D", width=3)
    draw.line((cx, cy, cx, cy - radius * 0.62), fill="#37474F", width=3)
    draw.line((cx, cy, cx + radius * 0.48, cy + radius * 0.22), fill="#37474F", width=3)
    draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill="#FF7043")


def _draw_calendar(canvas, x: int, y: int, width: int, height: int, now: datetime, font_path):
    draw = ImageDraw.Draw(canvas)
    margin = 12
    cell_width = (width - margin * 2) / 7
    header_y = y + 10
    rows_y = y + 36
    row_height = (height - 46) / 6

    for index, label in enumerate(("一", "二", "三", "四", "五", "六", "日")):
        cx = x + margin + cell_width * (index + 0.5)
        draw_text(canvas, (int(cx), header_y), label, 14, "#90A4AE",
                  font_path=font_path, align="center")

    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(now.year, now.month)
    for row, week in enumerate(weeks[:6]):
        for column, day in enumerate(week):
            if day == 0:
                continue
            cx = x + margin + cell_width * (column + 0.5)
            cy = rows_y + row_height * (row + 0.5)
            is_today = day == now.day
            if is_today:
                radius = 11
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill="#FF7043")
                color = "#FFFFFF"
            elif column >= 5:
                color = "#D84315"
            else:
                color = "#37474F"
            draw_text(canvas, (int(cx), int(cy) - 8), str(day), 15, color,
                      font_path=font_path, align="center")


def render_clock_card(width: int, height: int, now: Optional[datetime] = None,
                      font_path: Optional[str] = None) -> Image.Image:
    now = now or datetime.now()
    canvas = gradient((width, height), "#16324F", "#3C6E91")
    draw = ImageDraw.Draw(canvas)
    _clock_icon(draw, width - 46, 42, 22)
    draw_text(canvas, (20, 8), "时间 · 日历", 20, "#CFE8FF", font_path=font_path)

    time_text = now.strftime("%H:%M")
    time_width, _ = draw_text(canvas, (20, 30), time_text, 66, "#FFFFFF", font_path=font_path,
                              shadow="#0E2237", shadow_offset=(3, 3))
    draw_text(canvas, (20 + time_width + 10, 62), now.strftime("%S"), 26, "#FFD180",
              font_path=font_path, shadow="#0E2237", shadow_offset=(2, 2))

    date_text = f"{now.year}年{now.month}月{now.day}日  {WEEKDAYS[now.weekday()]}"
    draw_text(canvas, (20, 102), date_text, 21, "#DCEBFF", font_path=font_path)

    panel_x, panel_y = 12, 132
    panel_width, panel_height = width - 24, height - panel_y - 8
    canvas = _white_panel(canvas, panel_x, panel_y, panel_width, panel_height)
    _draw_calendar(canvas, panel_x, panel_y, panel_width, panel_height, now, font_path)
    return canvas


def _host_rows(info: dict):
    return (
        ("主机", info["hostname"], None, None, None),
        ("IP", info["ip"], None, None, None),
        ("内核", info["kernel"], None, None, None),
        ("温度", info["temperature"], None, None, info["temperature_color"]),
        ("负载", info["load"], None, None, None),
        ("内存", info["memory"], info["memory_pct"], "#42A5F5", None),
        ("磁盘", info["disk"], info["disk_pct"], "#66BB6A", None),
        ("运行", info["uptime"], None, None, None),
    )


def render_host_card(width: int, height: int, info: Optional[dict] = None,
                     font_path: Optional[str] = None) -> Image.Image:
    info = info or collect_host_info()
    canvas = gradient((width, height), "#0B1E2B", "#1F4A5F")
    draw = ImageDraw.Draw(canvas)
    draw_text(canvas, (20, 8), "主机信息", 24, "#E0F7FA", font_path=font_path)
    draw_text(canvas, (width - 20, 14), "在线", 14, "#69F0AE",
              font_path=font_path, align="right")
    draw.ellipse((width - 20 - 52, 20, width - 20 - 44, 28), fill="#69F0AE")

    panel_x, panel_y = 12, 44
    panel_width, panel_height = width - 24, height - panel_y - 8
    canvas = _white_panel(canvas, panel_x, panel_y, panel_width, panel_height)
    draw = ImageDraw.Draw(canvas)

    rows = _host_rows(info)
    row_height = (panel_height - 24) / len(rows)
    y = panel_y + 12
    for label, value, bar_pct, bar_color, value_color in rows:
        draw_text(canvas, (panel_x + 16, y), label, 18, "#78909C", font_path=font_path)
        draw_text(canvas, (panel_x + 96, y - 1), value, 19, value_color or "#263238",
                  font_path=font_path)
        if bar_pct is not None:
            bar_x, bar_y, bar_w, bar_h = panel_x + 330, int(y) + 5, 100, 9
            draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
                                   radius=4, fill="#ECEFF1")
            fill_w = max(2, int(bar_w * bar_pct / 100))
            draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h),
                                   radius=4, fill=bar_color or "#42A5F5")
        y += row_height
    return canvas


def render_weather_card(width: int, height: int, weather: Optional[Weather], *,
                        stale: bool = False, interval: int = 600,
                        font_path: Optional[str] = None, show_ip: bool = True) -> Image.Image:
    if weather is None:
        return render_offline(width, height, "正在获取天气数据…", font_path=font_path,
                              show_ip=show_ip)
    return render_weather(width, height, weather, stale=stale, interval=interval,
                          font_path=font_path, show_ip=show_ip)


def compose(card: Image.Image, index: int, width: int, height: int,
            font_path: Optional[str] = None) -> Image.Image:
    frame = Image.new("RGB", (width, height), "#0B1220")
    frame.paste(card, (0, 0))

    draw_text(frame, (12, height - BOTTOM_STRIP + 2), "轻触切换", 11, "#8FA3B8",
              font_path=font_path)
    center_x = width // 2
    center_y = height - 7
    for dot in range(len(CARD_NAMES)):
        x = center_x + (dot - (len(CARD_NAMES) - 1) / 2) * 18
        radius = 4 if dot == index else 3
        color = "#FFFFFF" if dot == index else "#546E7A"
        ImageDraw.Draw(frame).ellipse((x - radius, center_y - radius,
                                       x + radius, center_y + radius), fill=color)
    return frame
