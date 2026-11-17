#!/bin/bash
# Standalone MHS35 3.5" LCD installer: overlay, SPI and rotation.
# This is the display/kernel part of LCD-show's MHS35-show, without X11/fbcp.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROTATION=90
REBOOT=0
DRY_RUN=0
UNINSTALL=0
INSTALL_DEPS=0

usage() {
cat <<'EOF'
Install the MHS35 3.5" LCD overlay on a Raspberry Pi.

Usage:
  sudo ./install.sh [ROTATION] [options]

Arguments:
  ROTATION          0, 90, 180 or 270 (default: 90)

Options:
  --reboot          Reboot after installing/uninstalling
  --dry-run         Show actions without changing anything
  --uninstall       Remove the mhs35 overlay line and dtbo
  --install-deps    Install python3-pil and python3-numpy with apt
  -h, --help        Show this help

The script enables spi, copies overlays/mhs35.dtbo and adds
dtoverlay=mhs35:rotate=ROTATION to the boot config. A reboot is required.
It does not install X11 calibration, fbturbo or fbcp.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    0|90|180|270) ROTATION="$1"; shift ;;
    --reboot) REBOOT=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "error: run as root: sudo $0 $*" >&2
  exit 1
fi

if [[ ! -e /proc/device-tree/model ]]; then
  echo "error: this does not look like a Raspberry Pi" >&2
  exit 1
fi

if [[ -f /boot/firmware/config.txt ]]; then
  CONFIG=/boot/firmware/config.txt
  OVERLAY_DIR=/boot/firmware/overlays
elif [[ -f /boot/config.txt ]]; then
  CONFIG=/boot/config.txt
  OVERLAY_DIR=/boot/overlays
else
  echo "error: boot config.txt not found" >&2
  exit 1
fi

if [[ ! -d "$OVERLAY_DIR" ]]; then
  echo "error: overlays directory not found: $OVERLAY_DIR" >&2
  exit 1
fi

OVERLAY_SRC="$SCRIPT_DIR/overlays/mhs35.dtbo"
if [[ ! -f "$OVERLAY_SRC" ]]; then
  echo "error: missing overlay: $OVERLAY_SRC" >&2
  exit 1
fi

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

backup_config() {
  local backup="${CONFIG}.bak-mhs35-$(date +%Y%m%d-%H%M%S)"
  run cp -a "$CONFIG" "$backup"
  echo "config backup: $backup"
}

append_all_line() {
  local line="$1"
  local last_section=""
  last_section=$(grep -E '^[[:space:]]*\[[^]]+\]' "$CONFIG" | tail -n 1 || true)

  if [[ "$last_section" == "[all]" ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] append line: $line"
    else
      printf '%s\n' "$line" >> "$CONFIG"
    fi
  else
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] append section: [all] / $line"
    else
      printf '\n[all]\n%s\n' "$line" >> "$CONFIG"
    fi
  fi
}

if [[ "$UNINSTALL" -eq 1 ]]; then
  echo "Removing MHS35 overlay from $CONFIG"
  backup_config

  if grep -qE '^[[:space:]]*dtoverlay=mhs35' "$CONFIG"; then
    run sed -i -E 's|^[[:space:]]*dtoverlay=mhs35.*|# dtoverlay=mhs35 (removed)|' "$CONFIG"
    echo "mhs35 overlay line commented out"
  else
    echo "no mhs35 overlay line found"
  fi

  if [[ -e "$OVERLAY_DIR/mhs35.dtbo" ]]; then
    run rm -f "$OVERLAY_DIR/mhs35.dtbo"
    echo "removed $OVERLAY_DIR/mhs35.dtbo"
  else
    echo "no mhs35.dtbo found"
  fi

  echo "MHS35 overlay removed. Reboot to use HDMI output again."
  if [[ "$REBOOT" -eq 1 ]]; then
    run reboot
  fi
  exit 0
fi

echo "MHS35 display install"
echo "  config:  $CONFIG"
echo "  overlay: $OVERLAY_DIR"
echo "  rotate:  $ROTATION"

backup_config
run install -m 644 "$OVERLAY_SRC" "$OVERLAY_DIR/mhs35.dtbo"

if grep -qE '^[[:space:]]*dtparam=spi=on' "$CONFIG"; then
  echo "SPI already enabled"
elif grep -qE '^[[:space:]]*#[[:space:]]*dtparam=spi=on' "$CONFIG"; then
  run sed -i -E 's|^[[:space:]]*#[[:space:]]*dtparam=spi=on|dtparam=spi=on|' "$CONFIG"
  echo "SPI enabled (uncommented)"
else
  append_all_line "dtparam=spi=on"
  echo "SPI enabled (appended)"
fi

if grep -qE '^[[:space:]]*dtoverlay=mhs35' "$CONFIG"; then
  run sed -i -E "s|^[[:space:]]*dtoverlay=mhs35.*|dtoverlay=mhs35:rotate=${ROTATION}|" "$CONFIG"
  echo "MHS35 overlay updated (rotate=$ROTATION)"
else
  append_all_line "dtoverlay=mhs35:rotate=${ROTATION}"
  echo "MHS35 overlay added (rotate=$ROTATION)"
fi

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
  run apt-get update
  run apt-get install -y python3-pil python3-numpy
else
  if ! python3 -c 'import PIL' >/dev/null 2>&1; then
    echo "warning: Pillow is missing; install with: sudo apt install python3-pil"
  fi
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run complete; no files were changed."
  exit 0
fi

echo
echo "MHS35 overlay installed. Reboot is required."
if [[ "$REBOOT" -eq 1 ]]; then
  echo "Rebooting..."
  reboot
else
  echo "Run: sudo reboot"
fi
