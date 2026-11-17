"""Pillow-based scene rendering for the MHS35 panel."""

from __future__ import annotations

import os
from typing import Optional, Sequence

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

DEFAULT_SIZE = (480, 320)

_LATIN_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)

_CJK_FONTS = (
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x2E80 <= code <= 0x9FFF
        or 0xA000 <= code <= 0xA4CF
        or 0xAC00 <= code <= 0xD7AF
        or 0xF900 <= code <= 0xFAFF
        or 0xFE30 <= code <= 0xFE4F
        or 0xFF00 <= code <= 0xFFEF
        or 0x20000 <= code <= 0x2FA1F
    )


def _first_existing(paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def _pick_font_paths(text: str, explicit: Optional[str]):
    if explicit:
        return explicit, explicit
    latin = _first_existing(_LATIN_FONTS)
    cjk = _first_existing(_CJK_FONTS) if any(_is_cjk(char) for char in text) else latin
    return latin, cjk or latin


def _load_font(path: Optional[str], size: int):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _split_runs(line: str, latin_font, cjk_font, mixed: bool):
    if not line:
        return [(" ", latin_font)]
    if not mixed:
        return [(line, latin_font)]

    runs = []
    buffer = []
    use_cjk = None
    for char in line:
        cjk = _is_cjk(char)
        if use_cjk is None or cjk == use_cjk:
            buffer.append(char)
            use_cjk = cjk
        else:
            runs.append(("".join(buffer), cjk_font if use_cjk else latin_font))
            buffer = [char]
            use_cjk = cjk
    runs.append(("".join(buffer), cjk_font if use_cjk else latin_font))
    return runs


def _measure_line(runs, scratch):
    measured = []
    line_width = 0
    line_height = 1
    for text, font in runs:
        box = scratch.textbbox((0, 0), text, font=font)
        run_width = max(1, box[2] - box[0])
        run_height = max(1, box[3] - box[1])
        measured.append((text, font, box, run_width))
        line_width += run_width
        line_height = max(line_height, run_height)
    return measured, line_width, line_height


def _layout(lines, width, height, latin_path, cjk_path, font_size, margin, line_spacing):
    size = font_size or max(16, height // 8)
    mixed = latin_path != cjk_path
    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    while True:
        latin_font = _load_font(latin_path, size)
        cjk_font = _load_font(cjk_path, size) if mixed else latin_font
        measured_lines = []
        max_width = 0
        for line in lines:
            runs = _split_runs(line, latin_font, cjk_font, mixed)
            measured, line_width, line_height = _measure_line(runs, scratch)
            measured_lines.append((measured, line_width, line_height))
            max_width = max(max_width, line_width)

        gap = max(2, int(size * line_spacing))
        total_height = sum(item[2] for item in measured_lines) + gap * (len(lines) - 1)
        if (max_width <= width - 2 * margin and total_height <= height - 2 * margin) or size <= 8:
            return measured_lines, gap
        size = max(8, size - max(1, size // 12))


def _fit_image(image: Image.Image, size: tuple, mode: str) -> Image.Image:
    if mode == "stretch":
        return image.resize(size, Image.LANCZOS)
    if mode == "cover":
        return ImageOps.fit(image, size, method=Image.LANCZOS)
    image = image.copy()
    image.thumbnail(size, Image.LANCZOS)
    return image


def gradient(size: tuple, top: str, bottom: str) -> Image.Image:
    """Vertical RGB gradient."""
    width, height = size
    top_rgb = ImageColor.getrgb(top)
    bottom_rgb = ImageColor.getrgb(bottom)
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(a + (b - a) * ratio) for a, b in zip(top_rgb, bottom_rgb))
        draw.line((0, y, width, y), fill=color)
    return image


def draw_text(
    image: Image.Image,
    xy: tuple,
    text: str,
    size: int,
    fill,
    *,
    font_path: Optional[str] = None,
    align: str = "left",
    shadow=None,
    shadow_offset: tuple = (2, 2),
):
    """Draw mixed CJK/Latin text; xy is the top-left/top-center/top-right point."""
    latin_path, cjk_path = _pick_font_paths(text, font_path)
    mixed = latin_path != cjk_path
    latin_font = _load_font(latin_path, size)
    cjk_font = _load_font(cjk_path, size) if mixed else latin_font
    runs = _split_runs(text, latin_font, cjk_font, mixed)
    draw = ImageDraw.Draw(image)

    measured = []
    total_width = 0
    height = 1
    for run_text, font in runs:
        box = draw.textbbox((0, 0), run_text, font=font)
        run_width = max(1, box[2] - box[0])
        height = max(height, max(1, box[3] - box[1]))
        measured.append((run_text, font, box, run_width))
        total_width += run_width

    x0, y0 = xy
    if align == "right":
        x0 -= total_width
    elif align == "center":
        x0 -= total_width // 2

    layers = []
    if shadow is not None:
        layers.append((shadow, shadow_offset))
    layers.append((fill, (0, 0)))
    for color, (dx, dy) in layers:
        x = x0 + dx
        for run_text, font, box, run_width in measured:
            draw.text((x - box[0], y0 + dy - box[1]), run_text, font=font, fill=color)
            x += run_width

    return total_width, height


def render(
    width: int,
    height: int,
    lines: Sequence[str] = (),
    *,
    bg: str = "#000000",
    fg: str = "#ffffff",
    font_path: Optional[str] = None,
    font_size: Optional[int] = None,
    align: str = "center",
    valign: str = "middle",
    line_spacing: float = 0.25,
    image_path: Optional[str] = None,
    fit: str = "contain",
    margin: int = 8,
) -> Image.Image:
    """Render text (and an optional background image) at the panel resolution."""
    lines = [str(line) for line in lines]
    canvas = Image.new("RGB", (width, height), ImageColor.getrgb(bg))

    if image_path:
        with Image.open(image_path) as source:
            picture = _fit_image(source.convert("RGB"), (width, height), fit)
        canvas.paste(picture, ((width - picture.width) // 2, (height - picture.height) // 2))

    if lines:
        latin_path, cjk_path = _pick_font_paths("".join(lines), font_path)
        measured_lines, gap = _layout(lines, width, height, latin_path, cjk_path, font_size, margin, line_spacing)
        draw = ImageDraw.Draw(canvas)
        color = ImageColor.getrgb(fg)

        total_height = sum(item[2] for item in measured_lines) + gap * (len(lines) - 1)
        if valign == "top":
            y = margin
        elif valign == "bottom":
            y = height - margin - total_height
        else:
            y = (height - total_height) // 2

        for runs, line_width, line_height in measured_lines:
            if align == "left":
                x = margin
            elif align == "right":
                x = width - margin - line_width
            else:
                x = (width - line_width) // 2
            for text, font, box, run_width in runs:
                draw.text((x - box[0], y - box[1]), text, font=font, fill=color)
                x += run_width
            y += line_height + gap

    return canvas


def render_test_pattern(width: int, height: int) -> Image.Image:
    """Color bars plus a resolution label, useful to verify panel output."""
    colors = ("#ffffff", "#ffff00", "#00ffff", "#00ff00", "#ff00ff", "#ff0000", "#0000ff", "#000000")
    canvas = Image.new("RGB", (width, height), "#000000")
    draw = ImageDraw.Draw(canvas)
    bar_width = width // len(colors)
    split = height * 2 // 3

    for index, color in enumerate(colors):
        x0 = index * bar_width
        x1 = width if index == len(colors) - 1 else (index + 1) * bar_width
        draw.rectangle((x0, 0, x1 - 1, split - 1), fill=color)

    label = f"MHS35  {width}x{height}"
    latin_path, _ = _pick_font_paths(label, None)
    font = _load_font(latin_path, max(16, height // 12))
    box = draw.textbbox((0, 0), label, font=font)
    x = (width - (box[2] - box[0])) // 2 - box[0]
    y = split + ((height - split) - (box[3] - box[1])) // 2 - box[1]
    draw.text((x, y), label, font=font, fill="#ffffff")
    return canvas
