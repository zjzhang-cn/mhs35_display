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

- Never write to `/dev/fb0` (HDMI) or edit `/boot/config.txt` directly. `mhs35fb/framebuffer.py` auto-selects the fbtft/ILI9486 device and skips DRM devices.
- Do not run `install.sh` for real without confirmation: it edits the boot config and needs a reboot. `sudo ./install.sh --dry-run` is safe.
- Only one process may write `/dev/fb1`. Stop the dashboard before running another writer, and leave `mhs35-weather` disabled.
- Do not claim panel or touch verification unless it was actually done on hardware.

## Architecture

- `mhs35fb/framebuffer.py` — framebuffer discovery, fb ioctl structs, mmap, RGB565/32bpp blit, fbtft deferred-IO flush delay.
- `mhs35fb/render.py` — Pillow drawing, gradients, mixed-font text. CJK uses DroidSansFallbackFull and Latin uses DejaVu; the CJK font lacks Latin glyphs, so preserve the per-run font split.
- `mhs35fb/weather.py` — itboy weather API (reachable from the Pi) with Open-Meteo fallback, cache at `~/.cache/mhs35_weather.json`, cartoon scenes, IP helpers.
- `mhs35fb/cards.py` — clock/calendar card, host metrics card, page composition and dots.
- `mhs35fb/touch.py` — ADS7846 evdev reader. Any tap cycles cards; raw coordinates are not calibrated and are not used for navigation.
- `mhs35dash.py` — dashboard loop plus background weather worker; starts on the weather card; taps cycle weather → clock → host.
- `install.sh` + `overlays/mhs35.dtbo` + `udev/99-mhs35-touch-ignore.rules` — standalone overlay installer with rotation argument, `--dry-run`, `--uninstall`, `--install-deps`; the udev rule keeps ADS7846 out of the desktop input stack.

## Verification

- Render without hardware: `python3 mhs35dash.py --preview /tmp/card.png --card weather` (also `clock`, `host`).
- Weather only: `python3 mhs35weather.py --once` or `--preview`.
- Generic content: `python3 mhs35disp.py "line"`.
- Touch debugging: `python3 mhs35dash.py --start clock --touch-debug` prints raw events and the device path.
- Service logs: `journalctl -u mhs35-dashboard -f`.

## Conventions

- Keep the framebuffer layer dependency-light; Pillow is the only required third-party package, numpy is optional.
- Render code receives width/height from the detected framebuffer; do not hardcode 480x320 in shared drawing code.
- Commit only when asked; use short lowercase messages such as `add MHS35 dashboard and standalone installer`.
- This is an independent repo (branch `main`, no remote); the Pi deployment is a copy, not a clone.
