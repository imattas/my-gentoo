"""Render reviewable Gentoo package operations as argv arrays."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from typing import Any

from installer.planning.storage import plan_hash_matches
from installer.stages.stage3 import verify_root_mapping
from installer.stages.storage import _append_event, _atomic_json, ensure_state_location_off_target


PACKAGE_SETS = ("base", "desktop", "gaming", "development", "virtualization", "security_backup")

def render_emerge_commands(
    config: dict[str, Any], package_set: str, target_root: str = "/mnt/gentoo"
) -> list[list[str]]:
    if target_root != "/mnt/gentoo":
        raise ValueError("package operations are bound to the configured Gentoo root")
    sets = config.get("sets", {})
    if package_set not in sets:
        raise ValueError(f"unknown package set: {package_set}")
    prefix = ["chroot", target_root, "emerge"]
    commands: list[list[str]] = []
    if package_set == "base":
        commands.append(prefix + ["--sync"])
        commands.append(
            prefix + ["--ask", "--verbose", "--update", "--deep", "--newuse", "--with-bdeps=y", "@world"]
        )
    commands.append(prefix + ["--ask", "--verbose", *sets[package_set]])
    if package_set == "base":
        commands.append(
            ["chroot", target_root, "visudo", "--check", "--file", "/etc/sudoers"]
        )
        commands.append(
            ["chroot", target_root, "bootctl", "--esp-path=/efi", "--no-variables", "install"]
        )
    elif package_set == "desktop":
        commands.append(
            [
                "systemctl",
                f"--root={target_root}",
                "enable",
                "NetworkManager.service",
                "sddm.service",
            ]
        )
        commands.append(["systemctl", f"--root={target_root}", "set-default", "graphical.target"])
    return commands


def validate_boot_assets(root: Path) -> list[str]:
    efi = root / "efi"
    bootloader = efi / "EFI" / "systemd" / "systemd-bootx64.efi"
    ukis = sorted(
        path.name
        for path in (efi / "EFI" / "Linux").glob("*.efi")
        if path.is_file() and path.stat().st_size > 0
    )
    if not bootloader.is_file() or not ukis:
        raise RuntimeError("systemd-boot or a production UKI is missing from the EFI partition")
    return ukis


def run_package_stage(
    package_set: str,
    package_config: dict[str, Any],
    storage_plan: dict[str, Any],
    state_dir: Path,
    workstation: dict[str, Any],
    *,
    root: Path = Path("/mnt/gentoo"),
    runner: Any = subprocess.run,
    state_location_check: Any = ensure_state_location_off_target,
) -> dict[str, Any]:
    if package_set not in PACKAGE_SETS:
        raise ValueError(f"unknown package set: {package_set}")
    if not plan_hash_matches(storage_plan):
        raise ValueError("storage plan content does not match its hash")
    expected = workstation["storage"]["system_target"]
    if storage_plan.get("target", {}).get("serial") != expected["serial"]:
        raise ValueError("storage plan does not identify the configured system disk")

    state_dir = state_dir.resolve(strict=True)
    state_location_check(
        state_dir,
        storage_plan["target"]["by_id"],
        (expected["serial"], workstation["storage"]["data_disk"]["serial"]),
    )
    storage_state = json.loads((state_dir / "gentoo-storage-state.json").read_text())
    stage3_state = json.loads((state_dir / "gentoo-stage3-state.json").read_text())
    base_state = json.loads((state_dir / "gentoo-base-config-state.json").read_text())
    if (
        storage_state.get("plan_sha256") != storage_plan["sha256"]
        or storage_state.get("completed") != list(range(len(storage_plan["commands_for_review_only"])))
        or storage_state.get("started") is not None
        or not stage3_state.get("complete")
        or stage3_state.get("sha512") != workstation["stage3"]["sha512"]
        or base_state.get("storage_plan_sha256") != storage_plan["sha256"]
    ):
        raise RuntimeError("storage, Stage 3, and base configuration must be complete first")

    dependencies = {
        "base": (),
        "desktop": ("base",),
        "gaming": ("desktop",),
        "development": ("desktop",),
        "virtualization": ("desktop",),
        "security_backup": ("desktop",),
    }
    for required_set in dependencies[package_set]:
        completed = json.loads(
            (state_dir / f"gentoo-packages-{required_set}.json").read_text(encoding="utf-8")
        )
        if not completed.get("complete") or completed.get("storage_plan_sha256") != storage_plan["sha256"]:
            raise RuntimeError(f"package set {required_set} must finish before {package_set}")

    verify_root_mapping(storage_plan["target"]["by_id"], runner=runner)
    root_mount = runner(
        ["findmnt", "--mountpoint", str(root), "--noheadings", "--output", "TARGET,SOURCE,FSTYPE"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split()
    efi_mount = runner(
        ["findmnt", "--mountpoint", str(root / "efi"), "--noheadings", "--output", "TARGET,SOURCE,FSTYPE"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split()
    if (
        len(root_mount) != 3
        or root_mount[0] != str(root)
        or root_mount[2] != "btrfs"
        or root_mount[1].split("[", 1)[0] != "/dev/mapper/gentoo-root"
        or len(efi_mount) != 3
        or efi_mount[0] != str(root / "efi")
        or efi_mount[2] != "vfat"
    ):
        raise RuntimeError("encrypted Btrfs root and EFI partition must be mounted at their expected paths")
    efi_source = runner(
        ["readlink", "-f", "/dev/disk/by-partlabel/GENTOO-ESP"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if runner(["readlink", "-f", efi_mount[1]], check=True, capture_output=True, text=True).stdout.strip() != efi_source:
        raise RuntimeError("mounted EFI filesystem is not the planned GENTOO-ESP partition")
    command_list = render_emerge_commands(package_config, package_set, str(root))
    if package_set == "base":
        efi_stat = os.statvfs(root / "efi")
        free_bytes = efi_stat.f_bavail * efi_stat.f_frsize
        if free_bytes < 512 * 1024**2:
            raise RuntimeError("less than 512 MiB remains free on the EFI partition")

    state_path = state_dir / f"gentoo-packages-{package_set}.json"
    event_path = state_dir / "gentoo-package-events.jsonl"
    command_digest = hashlib.sha256(
        json.dumps(command_list, separators=(",", ":")).encode()
    ).hexdigest()
    if state_path.exists():
        journal = json.loads(state_path.read_text(encoding="utf-8"))
        if journal.get("command_sha256") != command_digest:
            raise RuntimeError("package checkpoint does not match the current configuration")
        if journal.get("started") is not None:
            raise RuntimeError("package command was interrupted; inspect Portage state before retrying")
        if journal.get("complete"):
            return {"status": "complete", "package_set": package_set, "state_file": str(state_path)}
    else:
        journal = {
            "schema_version": 1,
            "package_set": package_set,
            "storage_plan_sha256": storage_plan["sha256"],
            "command_sha256": command_digest,
            "completed": [],
            "started": None,
            "complete": False,
        }
        _atomic_json(state_path, journal)

    while len(journal["completed"]) < len(command_list):
        index = len(journal["completed"])
        command = command_list[index]
        journal["started"] = index
        _atomic_json(state_path, journal)
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "package-command-started",
                "package_set": package_set,
                "index": index,
                "argv": command,
            },
        )
        print("Running: " + " ".join(command), flush=True)
        runner(command, check=True)
        if package_set == "base" and index == len(command_list) - 1:
            journal["uki_files"] = validate_boot_assets(root)
        journal["completed"].append(index)
        journal["started"] = None
        _atomic_json(state_path, journal)
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "package-command-completed",
                "package_set": package_set,
                "index": index,
                "returncode": 0,
            },
        )

    journal["complete"] = True
    _atomic_json(state_path, journal)
    return {"status": "complete", "package_set": package_set, "state_file": str(state_path)}
