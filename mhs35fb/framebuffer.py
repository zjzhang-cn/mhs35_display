"""Linux framebuffer output for the MHS35 (ILI9486 / fbtft) 3.5" LCD."""

from __future__ import annotations

import ctypes
import fcntl
import glob
import mmap
import os
import time
from dataclasses import dataclass
from typing import Optional

FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602

MHS35_SIZES = {(480, 320), (320, 480)}
DRM_MARKERS = ("vc4drmfb", "simpledrm", "drmfb", "fbcon")


class _Bitfield(ctypes.Structure):
    _fields_ = [
        ("offset", ctypes.c_uint32),
        ("length", ctypes.c_uint32),
        ("msb_right", ctypes.c_uint32),
    ]


class _VarScreeninfo(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_uint32),
        ("yres", ctypes.c_uint32),
        ("xres_virtual", ctypes.c_uint32),
        ("yres_virtual", ctypes.c_uint32),
        ("xoffset", ctypes.c_uint32),
        ("yoffset", ctypes.c_uint32),
        ("bits_per_pixel", ctypes.c_uint32),
        ("grayscale", ctypes.c_uint32),
        ("red", _Bitfield),
        ("green", _Bitfield),
        ("blue", _Bitfield),
        ("transp", _Bitfield),
        ("nonstd", ctypes.c_uint32),
        ("activate", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("accel_flags", ctypes.c_uint32),
        ("pixclock", ctypes.c_uint32),
        ("left_margin", ctypes.c_uint32),
        ("right_margin", ctypes.c_uint32),
        ("upper_margin", ctypes.c_uint32),
        ("lower_margin", ctypes.c_uint32),
        ("hsync_len", ctypes.c_uint32),
        ("vsync_len", ctypes.c_uint32),
        ("sync", ctypes.c_uint32),
        ("vmode", ctypes.c_uint32),
        ("rotate", ctypes.c_uint32),
        ("colorspace", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 4),
    ]


class _FixScreeninfo(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char * 16),
        ("smem_start", ctypes.c_ulong),
        ("smem_len", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("type_aux", ctypes.c_uint32),
        ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16),
        ("ypanstep", ctypes.c_uint16),
        ("ywrapstep", ctypes.c_uint16),
        ("line_length", ctypes.c_uint32),
        ("mmio_start", ctypes.c_ulong),
        ("mmio_len", ctypes.c_uint32),
        ("accel", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16 * 2),
    ]


@dataclass(frozen=True)
class FramebufferDevice:
    path: str
    name: str
    width: int
    height: int
    bpp: int

    @property
    def size(self):
        return (self.width, self.height)

    def __str__(self):
        return f"{self.path}  {self.name}  {self.width}x{self.height}  {self.bpp}bpp"


def _read(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return default


def list_devices():
    devices = []
    for name_path in sorted(glob.glob("/sys/class/graphics/fb*/name")):
        fb_dir = os.path.dirname(name_path)
        path = "/dev/" + os.path.basename(fb_dir)
        if not os.path.exists(path):
            continue
        name = _read(name_path, "?")
        try:
            width, height = (int(part) for part in _read(os.path.join(fb_dir, "virtual_size")).split(","))
        except ValueError:
            width = height = 0
        try:
            bpp = int(_read(os.path.join(fb_dir, "bits_per_pixel"), "0"))
        except ValueError:
            bpp = 0
        devices.append(FramebufferDevice(path, name, width, height, bpp))
    return devices


def is_mhs35(device: FramebufferDevice) -> bool:
    if device.width <= 0 or device.height <= 0:
        return False
    name = device.name.lower()
    if any(marker in name for marker in DRM_MARKERS):
        return False
    if "ili9486" in name or "fbtft" in name:
        return True
    return device.size in MHS35_SIZES


def find_framebuffer(path: Optional[str] = None) -> str:
    if path:
        if not os.path.exists(path):
            raise RuntimeError(f"framebuffer {path} does not exist")
        return path

    devices = list_devices()
    matches = [device for device in devices if is_mhs35(device)]
    if matches:
        matches.sort(key=lambda d: (0 if "ili9486" in d.name.lower() else 1, d.path))
        return matches[0].path

    available = ", ".join(str(device) for device in devices) or "no framebuffer devices"
    raise RuntimeError(
        "MHS35 framebuffer not found (%s).\n"
        "Enable the panel once on the Pi with `sudo ./MHS35-show 90`, then reboot.\n"
        "To preview output without the panel: mhs35disp.py --demo --preview demo.png"
        % available
    )


def image_to_rgb565(image, byteorder: str = "little") -> bytes:
    """Convert a Pillow RGB image to packed RGB565 bytes."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    try:
        import numpy as np
    except ImportError:
        return _image_to_rgb565_py(image, byteorder)

    pixels = np.asarray(image, dtype=np.uint16)
    red = (pixels[..., 0] & 0xF8) << 8
    green = (pixels[..., 1] & 0xFC) << 3
    blue = pixels[..., 2] >> 3
    packed = red | green | blue
    dtype = "<u2" if byteorder == "little" else ">u2"
    return packed.astype(dtype, copy=False).tobytes()


def _image_to_rgb565_py(image, byteorder: str) -> bytes:
    source = image.tobytes()
    out = bytearray((len(source) // 3) * 2)
    index = 0
    for offset in range(0, len(source), 3):
        value = ((source[offset] & 0xF8) << 8) | ((source[offset + 1] & 0xFC) << 3) | (source[offset + 2] >> 3)
        if byteorder == "little":
            out[index] = value & 0xFF
            out[index + 1] = value >> 8
        else:
            out[index] = value >> 8
            out[index + 1] = value & 0xFF
        index += 2
    return bytes(out)


class Framebuffer:
    """mmap'ed Linux framebuffer with RGB565/32bpp blitting."""

    def __init__(self, path: Optional[str] = None, byteorder: str = "little"):
        self.path = find_framebuffer(path)
        self.byteorder = byteorder
        self._fd = os.open(self.path, os.O_RDWR | os.O_CLOEXEC)
        try:
            var = _VarScreeninfo()
            fcntl.ioctl(self._fd, FBIOGET_VSCREENINFO, var)
            fix = _FixScreeninfo()
            fcntl.ioctl(self._fd, FBIOGET_FSCREENINFO, fix)

            self.width = var.xres
            self.height = var.yres
            self.bpp = var.bits_per_pixel
            self.line_length = fix.line_length
            self.hardware_rotate = var.rotate
            if self.bpp not in (16, 32):
                raise RuntimeError(f"unsupported framebuffer depth: {self.bpp}bpp")
            self._mm = mmap.mmap(
                self._fd,
                fix.smem_len,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
            )
        except Exception:
            os.close(self._fd)
            raise

    @property
    def size(self):
        return (self.width, self.height)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        mm = getattr(self, "_mm", None)
        if mm is not None:
            mm.close()
            self._mm = None
        if getattr(self, "_fd", None) is not None:
            os.close(self._fd)
            self._fd = None

    def write(self, data: bytes, flush_delay: float = 0.0):
        bytes_per_pixel = self.bpp // 8
        row_bytes = self.width * bytes_per_pixel
        expected = row_bytes * self.height
        if len(data) < expected:
            raise ValueError(f"expected at least {expected} bytes, got {len(data)}")

        if self.line_length == row_bytes:
            self._mm[:expected] = data[:expected]
        else:
            for row in range(self.height):
                source = row * row_bytes
                target = row * self.line_length
                self._mm[target : target + row_bytes] = data[source : source + row_bytes]
        if flush_delay:
            self.flush(flush_delay)

    def blit(self, image, flush_delay: float = 0.08):
        if image.size != self.size:
            image = image.resize(self.size)
        if self.bpp == 32:
            raw = image.tobytes("raw", "BGRX" if self.byteorder == "little" else "XRGB")
        else:
            raw = image_to_rgb565(image, self.byteorder)
        self.write(raw)
        self.flush(flush_delay)

    def flush(self, delay: float = 0.08):
        try:
            self._mm.flush()
        except (BufferError, ValueError):
            pass
        if delay > 0:
            # fbtft uses deferred IO; give its worker time to push the frame.
            time.sleep(delay)
