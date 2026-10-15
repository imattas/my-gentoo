"""Interactive local-account creation without passing or recording passwords."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from typing import Any

from installer.planning.storage import plan_hash_matches
from installer.stages.stage3 import verify_root_mapping
from installer.stages.storage import _append_event, _atomic_json, ensure_state_location_off_target


def validate_target_mounts(root: Path, runner: Any = subprocess.run) -> None:
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
        ["readlink", "-f", "/dev/disk/by-partlabel/GENTOO-ESP"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    mounted_efi_source = runner(
        ["readlink", "-f", efi_mount[1]], check=True, capture_output=True, text=True
    ).stdout.strip()
    if mounted_efi_source != efi_source:
        raise RuntimeError("mounted EFI filesystem is not the planned GENTOO-ESP partition")


def user_creation_commands(username: str, root: str = "/mnt/gentoo") -> list[list[str]]:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}\$?", username) or username.startswith("-"):
        raise ValueError("username must be a simple lowercase Linux login name")
    if root != "/mnt/gentoo":
        raise ValueError("user setup is bound to the configured Gentoo root")
    return [
        ["chroot", root, "useradd", "--create-home", "--groups", "wheel", "--shell", "/bin/bash", username],
        ["chroot", root, "passwd", username],
    ]


def setup_user(
    username: str,
    storage_plan: dict[str, Any],
    state_dir: Path,
    workstation: dict[str, Any],
    *,
    runner: Any = subprocess.run,
    root: Path = Path("/mnt/gentoo"),
    state_location_check: Any = ensure_state_location_off_target,
) -> dict[str, str]:
    commands = user_creation_commands(username, str(root))
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
    storage = json.loads((state_dir / "gentoo-storage-state.json").read_text(encoding="utf-8"))
    desktop = json.loads((state_dir / "gentoo-packages-desktop.json").read_text(encoding="utf-8"))
    if (
        storage.get("plan_sha256") != storage_plan["sha256"]
        or not desktop.get("complete")
        or desktop.get("storage_plan_sha256") != storage_plan["sha256"]
    ):
        raise RuntimeError("desktop and storage setup must finish before adding a login user")
    verify_root_mapping(storage_plan["target"]["by_id"], runner=runner)
    validate_target_mounts(root, runner)

    state_path = state_dir / "gentoo-user-state.json"
    event_path = state_dir / "gentoo-user-events.jsonl"
    command_digest = hashlib.sha256(json.dumps(commands, separators=(",", ":")).encode()).hexdigest()
    resume_password = False
    if state_path.exists():
        journal = json.loads(state_path.read_text(encoding="utf-8"))
        if (
            journal.get("command_sha256") != command_digest
            or journal.get("storage_plan_sha256") != storage_plan["sha256"]
            or journal.get("username") != username
        ):
            raise RuntimeError("user setup checkpoint does not match this login")
        if journal.get("started") is not None:
            resume_password = journal.get("started") == 1 and journal.get("completed") == [0]
            if not resume_password:
                raise RuntimeError("user setup was interrupted before account creation completed")
        if journal.get("complete"):
            return {"status": "complete", "username": username, "state_file": str(state_path)}
    else:
        journal = {
            "schema_version": 1,
            "username": username,
            "storage_plan_sha256": storage_plan["sha256"],
            "command_sha256": command_digest,
            "completed": [],
            "started": None,
            "complete": False,
        }
        _atomic_json(state_path, journal)

    existing = runner(
        ["chroot", str(root), "getent", "passwd", username],
        check=False,
        capture_output=True,
        text=True,
    )
    if existing.returncode == 0 and not resume_password:
        raise RuntimeError("that login already exists; inspect it and set its password manually")
    if resume_password and existing.returncode != 0:
        raise RuntimeError("password recovery requires the previously created login to exist")
    if not resume_password and existing.returncode != 2:
        raise RuntimeError("could not safely determine whether that login already exists")

    while len(journal["completed"]) < len(commands):
        index = len(journal["completed"])
        argv = commands[index]
        journal["started"] = index
        _atomic_json(state_path, journal)
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "user-command-started",
                "username": username,
                "command": argv[2],
            },
        )
        print("Running: " + " ".join(argv), flush=True)
        runner(argv, check=True)
        journal["completed"].append(index)
        journal["started"] = None
        _atomic_json(state_path, journal)
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "user-command-completed",
                "username": username,
                "command": argv[2],
                "returncode": 0,
            },
        )

    journal["complete"] = True
    _atomic_json(state_path, journal)
    return {"status": "complete", "username": username, "state_file": str(state_path)}
