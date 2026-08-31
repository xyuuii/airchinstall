from __future__ import annotations

import json
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

from .domain import Fact

Probe = Callable[[], list[Fact]]


class ProbeUnavailable(RuntimeError):
    def __init__(self, probe_name: str):
        super().__init__(f"probe unavailable: {probe_name}")
        self.probe_name = probe_name


class ProbeRegistry:
    """Runs only explicitly registered, read-only fact probes."""

    def __init__(self, probes: dict[str, Probe]):
        self._probes = probes

    def collect(self, probe_name: str) -> list[Fact]:
        try:
            probe = self._probes[probe_name]
        except KeyError as error:
            raise ValueError(f"unknown probe: {probe_name}") from error
        try:
            return probe()
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, TypeError):
            raise ProbeUnavailable(probe_name) from None

    def require_registered(self, probe_names) -> None:
        missing = sorted(set(probe_names) - self._probes.keys())
        if missing:
            raise ValueError(f"unregistered probes: {', '.join(missing)}")


def parse_lsblk(payload: str) -> list[dict[str, object]]:
    devices = json.loads(payload).get("blockdevices", [])
    return [
        {
            "path": device["path"],
            "size": device.get("size", ""),
            "model": (device.get("model") or "").strip(),
            "removable": bool(device.get("rm", False)),
        }
        for device in devices
        if device.get("type") == "disk"
    ]


def _uefi_probe() -> list[Fact]:
    return [
        Fact(
            key="boot.uefi",
            value=Path("/sys/firmware/efi/efivars").is_dir(),
            source="uefi",
        )
    ]


def _network_probe() -> list[Fact]:
    online = False
    try:
        with socket.create_connection(("archlinux.org", 443), timeout=3):
            online = True
    except OSError:
        pass
    return [Fact(key="network.online", value=online, source="network")]


def _disk_probe() -> list[Fact]:
    completed = subprocess.run(
        ["lsblk", "-J", "-o", "NAME,PATH,SIZE,TYPE,MODEL,RM"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Fact(key="disks.inventory", value=parse_lsblk(completed.stdout), source="disks")]


def system_probe_registry() -> ProbeRegistry:
    return ProbeRegistry({"uefi": _uefi_probe, "network": _network_probe, "disks": _disk_probe})
