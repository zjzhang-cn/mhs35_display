#!/usr/bin/env python3
"""Multi-card dashboard for the MHS35 panel with touch page switching.

Cards: weather, clock/calendar, host info. A tap anywhere advances to the
next card. Weather is refreshed in a background thread.

Examples:
    python3 mhs35dash.py --preview clock.png --card clock
    python3 mhs35dash.py --start weather
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from datetime import datetime
from typing import Optional, Sequence

from mhs35fb import Framebuffer, find_framebuffer, list_devices
from mhs35fb import cards
from mhs35fb import weather as weather_mod
from mhs35fb.render import DEFAULT_SIZE
from mhs35fb.touch import TouchReader

CARD_INDEX = {"weather": 0, "clock": 1, "host": 2}


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value}")
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _size(value: str):
    try:
        width, height = value.lower().split("x", 1)
        width, height = int(width), int(height)
    except ValueError:
        raise argparse.ArgumentTypeError("size must look like 480x320")
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size must be positive")
    return width, height


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MHS35 multi-card dashboard (weather / clock / host) with touch switching.",
    )
    parser.add_argument("--start", choices=tuple(CARD_INDEX), default="weather",
                        help="first card (default: weather)")
    parser.add_argument("--interval", type=_positive_int, default=600, metavar="SECONDS",
                        help="weather refresh interval (default: 600)")
    parser.add_argument("--retry", type=_positive_int, default=60, metavar="SECONDS",
                        help="weather retry delay (default: 60)")
    parser.add_argument("--timeout", type=_positive_int, default=8, metavar="SECONDS",
                        help="network timeout (default: 8)")
    parser.add_argument("--provider", choices=("auto", "cma", "itboy", "open-meteo"), default="auto")
    parser.add_argument("--lat", type=float, default=weather_mod.BEIJING_LAT)
    parser.add_argument("--lon", type=float, default=weather_mod.BEIJING_LON)
    parser.add_argument("--preview", metavar="PNG", help="render one card to PNG and exit")
    parser.add_argument("--card", choices=tuple(CARD_INDEX), help="card to render with --preview")
    parser.add_argument("--size", type=_size, metavar="WxH", help="preview size (default: panel size)")
    parser.add_argument("--fb", metavar="PATH", help="framebuffer device (default: auto-detect)")
    parser.add_argument("--font", metavar="TTF", help="font file (default: auto, CJK-aware)")
    parser.add_argument("--touch-device", metavar="PATH", help="touch event device (default: auto)")
    parser.add_argument("--no-touch", action="store_true", help="disable touch switching")
    parser.add_argument("--touch-debug", action="store_true", help="log raw touch events")
    parser.add_argument("--quiet", action="store_true", help="suppress status messages")
    return parser


def _detected_size(fb_path: Optional[str]):
    try:
        path = find_framebuffer(fb_path)
    except RuntimeError:
        return DEFAULT_SIZE
    for device in list_devices():
        if device.path == path and device.width > 0 and device.height > 0:
            return device.width, device.height
    return DEFAULT_SIZE


class WeatherWorker(threading.Thread):
    def __init__(self, args):
        super().__init__(daemon=True)
        self.args = args
        self._lock = threading.Lock()
        self._weather = weather_mod.load_cache()
        self._stale = self._weather is not None
        self._error = None
        self._version = 0
        self._stop_event = threading.Event()

    def snapshot(self):
        with self._lock:
            return self._weather, self._stale, self._error, self._version

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            delay = self.args.interval
            try:
                weather = weather_mod.fetch_weather(
                    provider=self.args.provider,
                    lat=self.args.lat,
                    lon=self.args.lon,
                    timeout=self.args.timeout,
                )
                weather_mod.save_cache(weather)
                with self._lock:
                    self._weather = weather
                    self._stale = False
                    self._error = None
                    self._version += 1
                if not self.args.quiet:
                    print(f"weather: {weather.temperature:.0f}°C {weather.label}", flush=True)
            except Exception as exc:  # noqa: BLE001 - keep the dashboard running
                with self._lock:
                    self._error = str(exc)
                    self._stale = self._weather is not None
                    self._version += 1
                if not self.args.quiet:
                    print(f"weather error: {exc}", flush=True)
                delay = self.args.retry
            if self._stop_event.wait(delay):
                break


def _preview(args) -> int:
    width, height = args.size or _detected_size(args.fb)
    card_height = height - cards.BOTTOM_STRIP
    name = args.card or args.start
    index = CARD_INDEX[name]

    if name == "weather":
        weather = weather_mod.load_cache()
        stale = weather is not None
        try:
            weather = weather_mod.fetch_weather(
                provider=args.provider, lat=args.lat, lon=args.lon, timeout=args.timeout
            )
            weather_mod.save_cache(weather)
            stale = False
        except Exception:  # noqa: BLE001 - preview can fall back to cache
            pass
        card = cards.render_weather_card(width, card_height, weather, stale=stale,
                                         interval=args.interval, font_path=args.font)
    elif name == "clock":
        card = cards.render_clock_card(width, card_height, datetime.now(), font_path=args.font)
    else:
        card = cards.render_host_card(width, card_height, font_path=args.font)

    cards.compose(card, index, width, height, args.font).save(args.preview)
    print(f"preview saved: {args.preview} ({width}x{height}, card={name})", flush=True)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.preview:
        return _preview(args)

    try:
        framebuffer = Framebuffer(args.fb)
    except PermissionError:
        print("error: permission denied opening the framebuffer; "
              "add your user to the 'video' group or run with sudo", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    width, height = framebuffer.size
    card_height = height - cards.BOTTOM_STRIP

    taps = queue.Queue()
    reader = None
    if not args.no_touch:
        reader = TouchReader(args.touch_device, taps, debug=args.touch_debug)
        reader.start()
        if not reader.available:
            print("warning: touchscreen not found; page switching disabled", file=sys.stderr)

    worker = WeatherWorker(args)
    worker.start()

    if not args.quiet:
        touch_info = reader.device if reader and reader.available else "none"
        print(f"dashboard on {framebuffer.path} {width}x{height}, touch={touch_info}", flush=True)

    index = CARD_INDEX[args.start]
    dirty = True
    last_clock_second = -1
    last_host_draw = 0.0
    last_weather_draw = 0.0
    last_weather_version = -1

    try:
        while True:
            while True:
                try:
                    taps.get_nowait()
                except queue.Empty:
                    break
                index = (index + 1) % len(cards.CARD_NAMES)
                dirty = True
                if not args.quiet:
                    print(f"card: {cards.CARD_NAMES[index]}", flush=True)

            now_mono = time.monotonic()
            if index == 0:
                weather, stale, _error, version = worker.snapshot()
                if dirty or version != last_weather_version or now_mono - last_weather_draw >= 30:
                    card = cards.render_weather_card(
                        width, card_height, weather, stale=stale,
                        interval=args.interval, font_path=args.font,
                    )
                    framebuffer.blit(cards.compose(card, index, width, height, args.font))
                    last_weather_version = version
                    last_weather_draw = now_mono
                    dirty = False
            elif index == 1:
                now = datetime.now()
                if dirty or now.second != last_clock_second:
                    card = cards.render_clock_card(width, card_height, now, font_path=args.font)
                    framebuffer.blit(cards.compose(card, index, width, height, args.font))
                    last_clock_second = now.second
                    dirty = False
            else:
                if dirty or now_mono - last_host_draw >= 2:
                    card = cards.render_host_card(width, card_height, font_path=args.font)
                    framebuffer.blit(cards.compose(card, index, width, height, args.font))
                    last_host_draw = now_mono
                    dirty = False

            time.sleep(0.15)
    except KeyboardInterrupt:
        return 0
    finally:
        if reader is not None:
            reader.stop()
        worker.stop()
        framebuffer.close()


if __name__ == "__main__":
    sys.exit(main())
