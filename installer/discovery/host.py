"""Linux live-environment inspection; all operations are read-only."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from installer.discovery.devices import identify_system_target


def _run_json(argv: list[str]) -> Any:
    completed = subprocess.run(argv, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _memory_gib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 1)
    except (OSError, ValueError):
        return None
    return None


def parse_cpu_model(cpuinfo: str) -> str:
    for line in cpuinfo.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"model name", "Hardware"} and value.strip():
            return value.strip()
    return "unknown"


def _network_state() -> dict[str, Any]:
    if not shutil.which("ip"):
        return {"status": "unavailable", "interfaces": [], "default_routes": []}
    interfaces = _run_json(["ip", "-json", "address", "show"])
    routes = _run_json(["ip", "-json", "route", "show", "default"])
    return {"status": "observed", "interfaces": interfaces, "default_routes": routes}


def _pci_devices() -> dict[str, Any]:
    if not shutil.which("lspci"):
        return {"status": "unavailable", "devices": []}
    completed = subprocess.run(["lspci", "-nn"], check=True, capture_output=True, text=True)
    return {"status": "observed", "devices": completed.stdout.splitlines()}


def _by_id_links() -> dict[str, list[str]]:
    links: dict[str, list[str]] = {}
    root = Path("/dev/disk/by-id")
    if not root.exists():
        return links
    for link in root.iterdir():
        try:
            resolved = str(link.resolve(strict=True))
        except OSError:
            continue
        links.setdefault(resolved, []).append(str(link))
    return links


def inspect_host(config: dict[str, Any]) -> dict[str, Any]:
    """Collect hardware, firmware, network, and block-device state without writes."""
    if platform.system() != "Linux":
        raise RuntimeError("inspect must run from the Gentoo Linux live environment")
    if not shutil.which("lsblk"):
        raise RuntimeError("lsblk is required for block-device discovery")

    block = _run_json(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--output",
            "NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,PTTYPE,PARTLABEL,PARTUUID,FSTYPE,MOUNTPOINTS,PKNAME",
        ]
    )
    devices = block.get("blockdevices", [])
    target = identify_system_target(devices, config)
    target_path = target.get("device", {}).get("path") if target["device"] else None
    for device in devices:
        device["by_id"] = _by_id_links().get(device.get("path", ""), [])

    firmware = {
        "boot_mode": "UEFI" if Path("/sys/firmware/efi").exists() else "legacy-or-unknown",
        "efivars_mounted": Path("/sys/firmware/efi/efivars").exists(),
    }
    try:
        cpu_model = parse_cpu_model(Path("/proc/cpuinfo").read_text())
    except OSError:
        cpu_model = platform.processor() or "unknown"
    return {
        "schema_version": 1,
        "read_only": True,
        "host": {
            "hostname": platform.node(),
            "architecture": platform.machine(),
            "cpu_model": cpu_model,
            "cpu_threads": os.cpu_count(),
            "memory_gib": _memory_gib(),
        },
        "firmware": firmware,
        "network": _network_state(),
        "pci": _pci_devices(),
        "block_devices": devices,
        "target": {
            "status": target["status"],
            "match_count": target["match_count"],
            "path": target_path,
            "by_id": next(
                (device["by_id"] for device in devices if device.get("path") == target_path), []
            ),
        },
        "mounts": [
            {"path": device.get("path"), "mountpoints": device.get("mountpoints") or []}
            for device in devices
            if device.get("mountpoints")
        ],
    }
