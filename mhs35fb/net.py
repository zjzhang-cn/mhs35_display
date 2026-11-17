"""Local network address helpers."""

from __future__ import annotations

import socket
import struct

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux-only helper
    fcntl = None


def _interface_addresses():
    if fcntl is None:
        return []
    addresses = []
    for _, name in socket.if_nameindex():
        if name == "lo" or name.startswith(("docker", "veth", "br-")):
            continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            request = struct.pack("256s", name[:15].encode("utf-8"))
            result = fcntl.ioctl(sock.fileno(), 0x8915, request)
            address = socket.inet_ntoa(result[20:24])
        except OSError:
            continue
        finally:
            sock.close()
        if address and not address.startswith("127."):
            addresses.append((name, address))
    return addresses


def _default_route_ip():
    for target in (("8.8.8.8", 80), ("223.5.5.5", 80)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(target)
            return sock.getsockname()[0]
        except OSError:
            pass
        finally:
            sock.close()
    return None


def local_ip():
    addresses = _interface_addresses()
    default = _default_route_ip()
    if default and not default.startswith("127."):
        for name, address in addresses:
            if address == default:
                return address, name
        return default, ""
    if addresses:
        addresses.sort(key=lambda item: (0 if item[0] in ("eth0", "wlan0") else 1, item[0]))
        name, address = addresses[0]
        return address, name
    return None, None
