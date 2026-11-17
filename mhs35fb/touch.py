"""ADS7846 resistive touch input for the MHS35 panel."""

from __future__ import annotations

import glob
import os
import queue
import select
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux-only
    fcntl = None

_EVENT = struct.Struct("@llHHi")
EV_SYN = 0
EV_KEY = 1
EV_ABS = 3
ABS_X = 0
ABS_Y = 1
ABS_PRESSURE = 24
BTN_TOUCH = 0x14A
EVIOCGABS = 0x80184540


@dataclass
class Tap:
    x: int
    y: int
    duration: float


def find_touch_device() -> Optional[str]:
    for path in sorted(glob.glob("/dev/input/event*")):
        name_path = f"/sys/class/input/{os.path.basename(path)}/device/name"
        try:
            with open(name_path, encoding="utf-8") as handle:
                name = handle.read().strip()
        except OSError:
            continue
        if "ADS7846" in name or "Touchscreen" in name:
            return path
    return None


def _axis_range(fd: int, axis: int):
    if fcntl is None:
        return None
    try:
        buffer = bytearray(24)
        fcntl.ioctl(fd, EVIOCGABS + axis, buffer, True)
        value, minimum, maximum, fuzz, flat, resolution = struct.unpack("@6i", buffer)
        return minimum, maximum
    except OSError:
        return None


class TouchReader(threading.Thread):
    """Reads ADS7846 events and enqueues taps (press + quick release)."""

    def __init__(
        self,
        device: Optional[str] = None,
        tap_queue: Optional[queue.Queue] = None,
        tap_timeout: float = 1.5,
        debug: bool = False,
    ):
        super().__init__(daemon=True)
        self.device = device or find_touch_device()
        self.taps = tap_queue if tap_queue is not None else queue.Queue()
        self.tap_timeout = tap_timeout
        self.debug = debug
        self._stop_event = threading.Event()
        self._pressed = False
        self._press_started = 0.0
        self._x = 0
        self._y = 0
        self._last_tap = 0.0
        self._fd = None

    @property
    def available(self) -> bool:
        return self.device is not None

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        if not self.device:
            return
        try:
            self._fd = os.open(self.device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        except OSError as exc:
            if self.debug:
                print(f"touch: cannot open {self.device}: {exc}", flush=True)
            self.device = None
            return

        if self.debug:
            x_range = _axis_range(self._fd, ABS_X)
            y_range = _axis_range(self._fd, ABS_Y)
            print(f"touch: reading {self.device} x={x_range} y={y_range}", flush=True)

        buffer = b""
        try:
            while not self._stop_event.is_set():
                try:
                    ready, _, _ = select.select([self._fd], [], [], 0.2)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                try:
                    data = os.read(self._fd, _EVENT.size * 64)
                except BlockingIOError:
                    continue
                buffer += data
                while len(buffer) >= _EVENT.size:
                    event = _EVENT.unpack_from(buffer)
                    buffer = buffer[_EVENT.size:]
                    self._handle(*event)
        finally:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None

    def _handle(self, seconds, microseconds, type_, code, value) -> None:
        if self.debug and type_ != EV_SYN:
            print(f"touch: type={type_} code={code} value={value}", flush=True)
        if type_ == EV_KEY and code == BTN_TOUCH:
            if value:
                self._down()
            else:
                self._up()
        elif type_ == EV_ABS:
            if code == ABS_X:
                self._x = value
            elif code == ABS_Y:
                self._y = value
            elif code == ABS_PRESSURE:
                if value > 0:
                    self._down()
                else:
                    self._up()

    def _down(self) -> None:
        if self._pressed:
            return
        self._pressed = True
        self._press_started = time.monotonic()

    def _up(self) -> None:
        if not self._pressed:
            return
        self._pressed = False
        now = time.monotonic()
        if now - self._press_started > self.tap_timeout:
            return
        if now - self._last_tap < 0.3:
            return
        self._last_tap = now
        self.taps.put(Tap(self._x, self._y, now - self._press_started))
