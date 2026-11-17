# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## What this repo is

Standalone Python display stack for the MHS35 3.5" LCD (ILI9486/fbtft, 480x320, rotate=90) on Raspberry Pi. It writes the Linux framebuffer directly (`/dev/fb1`) and reads the ADS7846 touchscreen via evdev; no X11 or fbcp dependency.

Entry points: `mhs35dash.py` (multi-card dashboard, runs as a systemd service), `mhs35weather.py` (weather only), `mhs35disp.py` (text/image only). `install.sh` handles the overlay/SPI/rotation part of LCD-show.

## Platform and dependencies

- Raspberry Pi OS; Python 3.11 on the reference Pi; Pillow required, numpy optional (faster RGB565 conversion).
- No test suite, CI, lint, or package manifest. Verification is manual on the panel, or `--preview` for rendering only.
- Reference device: a Raspberry Pi on the local network, app at `~/mhs35_display`, active service `mhs35-dashboard`. The weather-only service `mhs35-weather` is disabled on purpose.

## Safety

- Never write to the HDMI framebuffer or edit `/boot/config.txt` directly. `mhs35fb/framebuffer.py` selects only the SPI0 CS0 480x320/320x480 framebuffer; DRM devices are never selected.
- Do not run `install.sh` for real without confirmation: it edits the boot config and needs a reboot. `sudo ./install.sh --dry-run` is safe.
- Only one process may write the panel framebuffer (`/dev/fbN`). Stop the dashboard before running another writer, and leave `mhs35-weather` disabled.
- Do not claim panel or touch verification unless it was actually done on hardware.

## Architecture

- `mhs35fb/framebuffer.py` — framebuffer discovery, fb ioctl structs, mmap, RGB565/32bpp blit, panel deferred-IO flush delay.
- `mhs35fb/render.py` — Pillow drawing, gradients, mixed-font text. CJK uses DroidSansFallbackFull and Latin uses DejaVu; the CJK font lacks Latin glyphs, so preserve the per-run font split.
- `mhs35fb/weather.py` — weather façade and weather-only run loop.
- `mhs35fb/weather_model.py` — `Weather` dataclass and location constants.
- `mhs35fb/weather_providers.py` — CMA/itboy/Open-Meteo/AQ providers and multi-source merge; must stay Pillow-free.
- `mhs35fb/weather_display.py` — cartoon scenes and weather panel rendering.
- `mhs35fb/weather_cache.py` — weather cache read/write.
- `mhs35fb/net.py` — local IP helpers for the host info card.
- `mhs35fb/cards.py` — clock/calendar card, host metrics card, page composition and dots.
- `mhs35fb/touch.py` — SPI0 CS1 touch evdev reader (bus address + ABS/button capability detection, no name matching). Any tap cycles cards; raw coordinates are not calibrated and are not used for navigation.
- `mhs35dash.py` — dashboard loop plus background weather worker; starts on the weather card; taps cycle weather → clock → host.
- `install.sh` + `overlays/mhs35.dtbo` + `udev/99-mhs35-touch-ignore.rules` — standalone overlay installer with rotation argument, `--dry-run`, `--uninstall`, `--install-deps`; the udev rule keeps the SPI0 CS1 touchscreen out of the desktop input stack.

## Verification

- Render without hardware: `python3 mhs35dash.py --preview /tmp/card.png --card weather` (also `clock`, `host`).
- Weather only: `python3 mhs35weather.py --once` or `--preview`.
- Generic content: `python3 mhs35disp.py "line"`.
- Touch debugging: `python3 mhs35dash.py --start clock --touch-debug` prints raw events and the device path.
- Service logs: `journalctl -u mhs35-dashboard -f`.

## Conventions

- Keep the framebuffer layer dependency-light; Pillow is the only required third-party package, numpy is optional.
- Keep `weather_providers.py` Pillow-free; weather drawing belongs in `weather_display.py`.
- Weather modules must not import `net`; IP belongs to the host info card only.
- Render code receives width/height from the detected framebuffer; do not hardcode 480x320 in shared drawing code.
- Commit only when asked; use short lowercase messages such as `add MHS35 dashboard and standalone installer`.
- This is an independent repo (branch `main`, no remote); the Pi deployment is a copy, not a clone.
