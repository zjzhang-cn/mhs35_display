#!/usr/bin/env python3
"""Show Beijing weather as a cartoon scene on an MHS35 3.5" LCD.

Examples:
    python3 mhs35weather.py --once
    python3 mhs35weather.py --preview weather.png
    python3 mhs35weather.py --interval 600
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from mhs35fb import Framebuffer, find_framebuffer, list_devices
from mhs35fb import weather as weather_mod
from mhs35fb.render import DEFAULT_SIZE


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
        description="Beijing weather cartoon for the MHS35 480x320 LCD.",
        epilog="Default behavior refreshes every 10 minutes; use --once for a single frame.",
    )
    parser.add_argument("--interval", type=_positive_int, default=600, metavar="SECONDS",
                        help="weather refresh interval (default: 600)")
    parser.add_argument("--retry", type=_positive_int, default=60, metavar="SECONDS",
                        help="retry delay after a fetch failure (default: 60)")
    parser.add_argument("--timeout", type=_positive_int, default=8, metavar="SECONDS",
                        help="network timeout (default: 8)")
    parser.add_argument("--provider", choices=("auto", "cma", "itboy", "open-meteo"), default="auto",
                        help="weather source (default: auto, cma -> itboy -> open-meteo)")
    parser.add_argument("--lat", type=float, default=weather_mod.BEIJING_LAT)
    parser.add_argument("--lon", type=float, default=weather_mod.BEIJING_LON)
    parser.add_argument("--once", action="store_true", help="draw one frame and exit")
    parser.add_argument("--preview", metavar="PNG", help="save one frame instead of writing the panel")
    parser.add_argument("--size", type=_size, metavar="WxH", help="preview size (default: panel size)")
    parser.add_argument("--fb", metavar="PATH", help="framebuffer device (default: auto-detect)")
    parser.add_argument("--font", metavar="TTF", help="font file (default: auto, CJK-aware)")
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    common = dict(
        provider=args.provider,
        lat=args.lat,
        lon=args.lon,
        timeout=args.timeout,
        interval=args.interval,
        retry=args.retry,
        once=args.once,
        preview=args.preview,
        font_path=args.font,
        quiet=args.quiet,
    )

    if args.preview:
        width, height = args.size or _detected_size(args.fb)
        return weather_mod.run(width=width, height=height, **common)

    try:
        framebuffer = Framebuffer(args.fb)
    except PermissionError:
        print("error: permission denied opening the framebuffer; "
              "add your user to the 'video' group or run with sudo", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        return weather_mod.run(fb=framebuffer, width=framebuffer.width,
                               height=framebuffer.height, **common)
    except KeyboardInterrupt:
        return 0
    finally:
        framebuffer.close()


if __name__ == "__main__":
    sys.exit(main())
