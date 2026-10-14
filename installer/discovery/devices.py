"""Helpers for identifying the configured target among lsblk records."""

from __future__ import annotations

from typing import Any


def identify_system_target(devices: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Return a unique target status; never choose a device by its kernel name."""
    expected = config["storage"]["system_target"]
    matches = [
        device
        for device in devices
        if device.get("type") == "disk"
        and str(device.get("model") or "").strip() == expected["model"]
        and str(device.get("serial") or "").strip() == expected["serial"]
    ]
    if len(matches) == 1:
        return {"status": "identified", "match_count": 1, "device": matches[0]}
    return {
        "status": "blocked" if not matches else "ambiguous",
        "match_count": len(matches),
        "device": None,
    }
