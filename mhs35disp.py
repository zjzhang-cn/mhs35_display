#!/usr/bin/env python3
"""Display user-specified content on an MHS35 3.5" LCD (480x320, fbtft).

Examples:
    python3 mhs35disp.py "Hello" "MHS35"
    python3 mhs35disp.py --text "Temperature: 42C" --bg '#101820' --fg '#00ff88'
    python3 mhs35disp.py --image logo.png --fit contain --text "Booting..."
    python3 mhs35disp.py --demo --preview demo.png
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from mhs35fb import Framebuffer, find_framebuffer, list_devices
from mhs35fb.render import DEFAULT_SIZE, render, render_test_pattern


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
        description='Show specified text or an image on an MHS35 3.5" LCD.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Framebuffer selection is automatic: the program looks for the fbtft/ILI9486\n"
            "device (normally /dev/fb1 at 480x320). Use --fb to override.\n\n"
            "Without the panel enabled, render to a PNG with --preview."
        ),
    )
    parser.add_argument("lines", nargs="*", help="text lines to display")
    parser.add_argument("--text", action="append", default=[], metavar="LINE", help="text line (repeatable)")
    parser.add_argument(
        "--text-file",
        action="append",
        default=[],
        metavar="PATH",
        help="read text lines from a UTF-8 file (repeatable)",
    )
    parser.add_argument("--image", metavar="PATH", help="background image (PNG/JPEG/...)")
    parser.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain",
                        help="how the image fills the screen (default: contain)")
    parser.add_argument("--bg", default="#000000", metavar="COLOR", help="background color (default: #000000)")
    parser.add_argument("--fg", default="#ffffff", metavar="COLOR", help="text color (default: #ffffff)")
    parser.add_argument("--font", metavar="TTF", help="font file (default: auto, CJK-aware)")
    parser.add_argument("--font-size", type=_positive_int, metavar="PX", help="font size (default: auto-fit)")
    parser.add_argument("--align", choices=("left", "center", "right"), default="center")
    parser.add_argument("--valign", choices=("top", "middle", "bottom"), default="middle")
    parser.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0,
                        help="rotate content clockwise before display (default: 0)")
    parser.add_argument("--fb", metavar="PATH", help="framebuffer device (default: auto-detect)")
    parser.add_argument("--size", type=_size, metavar="WxH", help="render size for --preview (default: 480x320)")
    parser.add_argument("--preview", metavar="PNG", help="save the rendered image instead of writing the panel")
    parser.add_argument("--list", action="store_true", help="list framebuffer devices and exit")
    parser.add_argument("--demo", action="store_true", help="draw color bars and a resolution label")
    parser.add_argument("--quiet", action="store_true", help="suppress the success message")
    return parser


def _collect_lines(args) -> list:
    lines = []
    for item in list(args.lines) + list(args.text):
        lines.extend(item.splitlines() if item else [""])
    for path in args.text_file:
        with open(path, encoding="utf-8") as handle:
            lines.extend(handle.read().splitlines())
    return lines


def _detected_size(fb_path: Optional[str]):
    try:
        path = find_framebuffer(fb_path)
    except RuntimeError:
        return DEFAULT_SIZE
    for device in list_devices():
        if device.path == path and device.width > 0 and device.height > 0:
            return device.width, device.height
    return DEFAULT_SIZE


def _print_devices() -> int:
    try:
        selected = find_framebuffer()
    except RuntimeError:
        selected = None
    devices = list_devices()
    if not devices:
        print("no framebuffer devices found")
        return 1
    for device in devices:
        print(("*" if device.path == selected else " ") + " " + str(device))
    if selected is None:
        sys.stdout.flush()
        print("\nno MHS35 framebuffer: enable it with `sudo ./MHS35-show 90` and reboot", file=sys.stderr)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return _print_devices()

    try:
        lines = _collect_lines(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.demo and not lines and not args.image:
        parser.print_help(sys.stderr)
        print("\nerror: specify text, --text-file, --image, or --demo", file=sys.stderr)
        return 2

    framebuffer = None
    if args.preview:
        width, height = args.size or _detected_size(args.fb)
    else:
        try:
            framebuffer = Framebuffer(args.fb)
        except PermissionError:
            print(
                "error: permission denied opening the framebuffer; "
                "add your user to the 'video' group or run with sudo",
                file=sys.stderr,
            )
            return 1
        except (RuntimeError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        width, height = framebuffer.size
        if args.size and tuple(args.size) != (width, height) and not args.quiet:
            print(f"note: ignoring --size {args.size[0]}x{args.size[1]}; panel is {width}x{height}", file=sys.stderr)

    render_width, render_height = (height, width) if args.rotate in (90, 270) else (width, height)
    try:
        if args.demo:
            image = render_test_pattern(render_width, render_height)
        else:
            image = render(
                render_width,
                render_height,
                lines,
                bg=args.bg,
                fg=args.fg,
                font_path=args.font,
                font_size=args.font_size,
                align=args.align,
                valign=args.valign,
                image_path=args.image,
                fit=args.fit,
            )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if framebuffer is not None:
            framebuffer.close()
        return 1

    if args.rotate:
        image = image.rotate(-args.rotate, expand=True)

    if args.preview:
        try:
            image.save(args.preview)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"preview saved: {args.preview} ({image.width}x{image.height})")
        return 0

    try:
        framebuffer.blit(image)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        framebuffer.close()

    if not args.quiet:
        print(f"displayed on {framebuffer.path} ({width}x{height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
