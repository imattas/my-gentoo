"""Build and validate an exact-device storage plan without executing it."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical_hash(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "sha256"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _disk_state(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": device.get("path"),
        "model": device.get("model", "").strip(),
        "serial": device.get("serial", "").strip(),
        "size_bytes": device.get("size"),
        "partition_table": device.get("pttype"),
        "filesystem": device.get("fstype"),
        "mountpoints": device.get("mountpoints") or [],
        "children": device.get("children") or [],
    }


def render_storage_plan(
    report: dict[str, Any], config: dict[str, Any], selected_by_id: str
) -> dict[str, Any]:
    """Render a storage plan only when inspection uniquely identified its disk."""
    if report.get("read_only") is not True:
        raise ValueError("inspection report must be marked read-only")
    if report.get("firmware", {}).get("boot_mode") != "UEFI":
        raise ValueError("boot the live environment in UEFI mode before planning")
    if report.get("target", {}).get("status") != "identified" or report["target"].get("match_count") != 1:
        raise ValueError("system disk identity is not unique")
    if not selected_by_id.startswith("/dev/disk/by-id/") or "-part" in selected_by_id:
        raise ValueError("select a whole-disk /dev/disk/by-id path")

    expected = config["storage"]["system_target"]
    candidates = [
        device
        for device in report.get("block_devices", [])
        if device.get("type") == "disk"
        and device.get("model", "").strip() == expected["model"]
        and device.get("serial", "").strip() == expected["serial"]
    ]
    if len(candidates) != 1:
        raise ValueError("configured model and serial must match exactly one discovered disk")
    device = candidates[0]
    if selected_by_id not in device.get("by_id", []):
        raise ValueError("selected by-id path does not resolve to the configured system disk")
    if device.get("size", 0) < 2 * 1024**3:
        raise ValueError("system disk is too small for the configured EFI partition")

    state = _disk_state(device)
    root_part = "/dev/disk/by-partlabel/GENTOO-CRYPTROOT"
    esp_part = "/dev/disk/by-partlabel/GENTOO-ESP"
    commands = [
        ["sgdisk", "--zap-all", selected_by_id],
        [
            "sgdisk",
            "--new=1:0:+2G",
            "--typecode=1:EF00",
            "--change-name=1:GENTOO-ESP",
            "--new=2:0:0",
            "--typecode=2:8309",
            "--change-name=2:GENTOO-CRYPTROOT",
            selected_by_id,
        ],
        ["partprobe", selected_by_id],
        ["udevadm", "settle"],
        ["cryptsetup", "luksFormat", "--type", "luks2", root_part],
        ["cryptsetup", "open", root_part, "gentoo-root"],
        ["mkfs.btrfs", "--label", "gentoo-root", "/dev/mapper/gentoo-root"],
        ["mkfs.fat", "-F", "32", "-n", "GENTOO-ESP", esp_part],
    ]
    plan = {
        "schema_version": 1,
        "plan_type": "gentoo-system-storage",
        "read_only_plan": True,
        "requires_explicit_authorization": True,
        "target": {
            "model": expected["model"],
            "serial": expected["serial"],
            "by_id": selected_by_id,
            "observed_device_path": device["path"],
        },
        "observed_state": state,
        "layout": {
            "partition_table": "GPT",
            "efi_size_bytes": 2 * 1024**3,
            "efi_mount": "/efi",
            "root_partition": "remaining disk capacity",
            "root_encryption": "LUKS2",
            "root_filesystem": "Btrfs",
            "btrfs_subvolumes": expected["btrfs_subvolumes"],
            "mount_options": config["storage"]["mount_options"],
        },
        "effects": [
            "existing partition data will be destroyed",
            "all data on the named system disk will be irrecoverable without backups",
            "the separate data disk is outside this plan",
        ],
        "commands_for_review_only": commands,
    }
    plan["sha256"] = _canonical_hash(plan)
    return plan


def validate_storage_plan(
    plan: dict[str, Any],
    report: dict[str, Any],
    backup_verified: bool,
    recovery_media_verified: bool,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Compare a saved plan with fresh discovery and backup/recovery attestations."""
    issues: list[str] = []
    if plan.get("plan_type") != "gentoo-system-storage":
        issues.append("unsupported plan type")
    if plan.get("sha256") != _canonical_hash(plan):
        issues.append("plan hash does not match its contents")
    try:
        expected_plan = render_storage_plan(report, config, plan.get("target", {}).get("by_id", ""))
        if expected_plan["sha256"] != plan.get("sha256"):
            issues.append("plan content differs from the deterministic configured plan")
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(f"fresh state cannot reproduce the configured plan: {exc}")
    if not backup_verified:
        issues.append("operator has not confirmed a verified independent backup")
    if not recovery_media_verified:
        issues.append("operator has not confirmed verified recovery media")
    if report.get("read_only") is not True:
        issues.append("fresh discovery report is not marked read-only")
    if report.get("target", {}).get("status") != "identified":
        issues.append("system disk is not uniquely identified in fresh discovery")

    expected = plan.get("target", {})
    matches = [
        device
        for device in report.get("block_devices", [])
        if device.get("type") == "disk"
        and device.get("model", "").strip() == expected.get("model")
        and device.get("serial", "").strip() == expected.get("serial")
        and expected.get("by_id") in device.get("by_id", [])
    ]
    if len(matches) != 1:
        issues.append("fresh device identity does not match exactly one planned disk")
    elif _disk_state(matches[0]) != plan.get("observed_state"):
        issues.append("system disk partition or mount state changed after planning")
    if report.get("firmware", {}).get("boot_mode") != "UEFI":
        issues.append("live environment is not booted in UEFI mode")

    return {"valid": not issues, "plan_sha256": plan.get("sha256"), "issues": issues}
