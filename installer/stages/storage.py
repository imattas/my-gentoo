"""Exact-device encrypted storage stage with fail-closed checkpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable

from installer.discovery.host import inspect_host
from installer.planning.storage import _disk_state, plan_hash_matches, validate_storage_plan


ERASURE_PHRASE = "ERASE-SYSTEM-DISK"


def validate_stage_authorization(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    confirmed_sha256: str,
    confirmed_serial: str,
    erasure_phrase: str,
) -> dict[str, Any]:
    issues = []
    target = plan.get("target", {})
    if not plan_hash_matches(plan):
        issues.append("storage plan contents do not match its hash")
    if authorization.get("authorized_operation") != "partition-and-format-system-disk":
        issues.append("authorization does not grant the storage operation")
    if authorization.get("single_disk_scope") is not True:
        issues.append("authorization is not scoped to one disk")
    if authorization.get("plan_sha256") != plan.get("sha256"):
        issues.append("authorization record is for a different plan")
    if authorization.get("target") != target:
        issues.append("authorization record is for a different disk")
    if confirmed_sha256 != plan.get("sha256"):
        issues.append("typed plan hash does not match")
    if confirmed_serial != target.get("serial"):
        issues.append("typed serial does not match")
    if erasure_phrase != ERASURE_PHRASE:
        issues.append("required erasure phrase was not entered exactly")
    return {"valid": not issues, "issues": issues}


def next_unstarted_command(commands: list[list[str]], journal: dict[str, Any]) -> int | None:
    completed = journal.get("completed", [])
    started = journal.get("started")
    if started is not None:
        raise RuntimeError(
            f"command {started} was interrupted after it began; inspect the disk manually before continuing"
        )
    if completed != list(range(len(completed))) or len(completed) > len(commands):
        raise RuntimeError("storage checkpoint is inconsistent; refusing to continue")
    if len(completed) == len(commands):
        return None
    return len(completed)


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def assert_state_device_is_unprotected(
    ancestors: list[dict[str, Any]],
    target_real_path: str,
    protected_serials: tuple[str, ...],
    *,
    realpath: Callable[[str], str] = os.path.realpath,
) -> None:
    paths = {realpath(row.get("path", "")) for row in ancestors if row.get("path")}
    if target_real_path in paths:
        raise RuntimeError("state directory resides on the target disk")
    serials = {str(row.get("serial") or "").strip() for row in ancestors}
    if serials.intersection(protected_serials):
        raise RuntimeError("state directory resides on a separately protected workstation disk")
    disks = [row for row in ancestors if row.get("type") == "disk"]
    if not disks or any(not str(row.get("serial") or "").strip() for row in disks):
        raise RuntimeError("cannot prove state storage is outside the protected workstation disks")


def _append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _exact_device_state(report: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    target = plan["target"]
    matches = [
        device
        for device in report.get("block_devices", [])
        if device.get("type") == "disk"
        and str(device.get("model") or "").strip() == target["model"]
        and str(device.get("serial") or "").strip() == target["serial"]
        and target["by_id"] in device.get("by_id", [])
    ]
    if len(matches) != 1:
        raise RuntimeError("authorized disk no longer has a unique exact identity")
    if matches[0].get("path") != target.get("observed_device_path"):
        raise RuntimeError("authorized by-id path resolves to a different kernel device")
    return _disk_state(matches[0])


def _assert_target_identity(state: dict[str, Any], plan: dict[str, Any]) -> None:
    target = plan["target"]
    observed = plan["observed_state"]
    if any(
        state.get(field) != expected
        for field, expected in (
            ("path", target["observed_device_path"]),
            ("model", target["model"]),
            ("serial", target["serial"]),
            ("size_bytes", observed["size_bytes"]),
        )
    ):
        raise RuntimeError("target identity changed during partition-table discovery")


def _assert_empty_partition_table(state: dict[str, Any], plan: dict[str, Any]) -> None:
    _assert_target_identity(state, plan)
    if state.get("partition_table") or state.get("children") or state.get("mountpoints"):
        raise RuntimeError("target is not in the expected blank state after the authorized wipe")


def _partition_label(child: dict[str, Any]) -> str | None:
    label = child.get("partlabel")
    if label:
        return str(label)
    path = child.get("path")
    if not path:
        return None
    probe = subprocess.run(
        ["blkid", "--probe", "--output", "export", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode:
        return None
    properties = dict(
        line.split("=", 1) for line in probe.stdout.splitlines() if "=" in line
    )
    return properties.get("PART_ENTRY_NAME")


def _assert_expected_partition_table(
    state: dict[str, Any],
    plan: dict[str, Any],
    *,
    require_unformatted: bool = True,
    require_labels: bool = True,
) -> None:
    """Validate the deliberate GPT transition while kernel partition data settles."""
    _assert_target_identity(state, plan)
    children = state.get("children", [])
    if (
        state.get("partition_table") != "gpt"
        or len(children) != 2
        or (require_unformatted and any(child.get("fstype") for child in children))
        or any(child.get("mountpoints") for child in children)
        or state.get("mountpoints")
    ):
        raise RuntimeError("observed partition table differs from the authorized GPT layout")

    disk_path = str(plan["target"]["observed_device_path"])
    disk_name = os.path.basename(disk_path)
    partition_separator = "p" if disk_name[-1:].isdigit() else ""
    expected_paths = {
        1: disk_path + partition_separator + "1",
        2: disk_path + partition_separator + "2",
    }
    by_path = {child.get("path"): child for child in children}
    if any(path not in by_path for path in expected_paths.values()):
        raise RuntimeError("observed GPT partitions do not match the planned partition numbers")
    esp = by_path[expected_paths[1]]
    root = by_path[expected_paths[2]]
    if esp.get("size") != 2 * 1024**3 or not isinstance(root.get("size"), int) or root["size"] <= 0:
        raise RuntimeError("observed EFI partition size differs from the authorized plan")
    if require_labels:
        if _partition_label(esp) != "GENTOO-ESP" or _partition_label(root) != "GENTOO-CRYPTROOT":
            raise RuntimeError("partition label does not match the authorized layout")
    elif any(
        child.get("partlabel") not in (None, expected_label)
        for child, expected_label in ((esp, "GENTOO-ESP"), (root, "GENTOO-CRYPTROOT"))
    ):
        raise RuntimeError("partition label does not match the authorized layout")


def _assert_partition_aliases_match_target(
    state: dict[str, Any],
    plan: dict[str, Any],
    *,
    realpath: Callable[[str], str] = os.path.realpath,
) -> None:
    _assert_expected_partition_table(state, plan)
    disk_path = str(plan["target"]["observed_device_path"])
    disk_name = os.path.basename(disk_path)
    partition_separator = "p" if disk_name[-1:].isdigit() else ""
    expected = {
        "/dev/disk/by-partlabel/GENTOO-ESP": disk_path + partition_separator + "1",
        "/dev/disk/by-partlabel/GENTOO-CRYPTROOT": disk_path + partition_separator + "2",
    }
    for alias, partition in expected.items():
        if realpath(alias) != realpath(partition):
            raise RuntimeError(f"partition identity link does not resolve to the authorized target: {alias}")


def _is_expected_partition_settling(
    state: dict[str, Any],
    completed: list[int],
    next_index: int,
    plan: dict[str, Any],
    commands: list[list[str]],
) -> bool:
    awaiting_wipe_probe = completed == [0] and next_index == 1
    awaiting_wipe_settle = completed == [0, 1] and next_index == 2
    awaiting_repartition = completed == [0, 1, 2] and next_index == 3
    if awaiting_wipe_probe or awaiting_wipe_settle or awaiting_repartition:
        _assert_empty_partition_table(state, plan)
        return True
    awaiting_partition_probe = completed == [0, 1, 2, 3] and next_index == 4
    awaiting_partition_settle = completed == [0, 1, 2, 3, 4] and next_index == 5
    if awaiting_partition_probe or awaiting_partition_settle:
        _assert_expected_partition_table(state, plan, require_labels=False)
        return True
    if (
        completed
        and next_index < len(commands)
        and commands[next_index][:2] == ["udevadm", "settle"]
        and commands[completed[-1]][0] in {"cryptsetup", "mkfs.btrfs", "mkfs.fat"}
    ):
        _assert_expected_partition_table(state, plan, require_unformatted=False)
        return True
    return False


def ensure_state_location_off_target(
    state_dir: Path, target_by_id: str, protected_serials: tuple[str, ...]
) -> None:
    if not state_dir.is_dir():
        raise RuntimeError("state directory must already exist on a non-target filesystem")
    completed = subprocess.run(
        ["findmnt", "--evaluate", "--noheadings", "--output", "SOURCE,FSTYPE", "--target", str(state_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    fields = completed.stdout.strip().split()
    if len(fields) != 2:
        raise RuntimeError("could not determine the state directory's backing filesystem")
    source, filesystem = fields
    if filesystem == "tmpfs":
        raise RuntimeError("state must persist on external block storage; tmpfs is not sufficient")
    if not source.startswith("/dev/"):
        raise RuntimeError("state must be on an identifiable external block device")
    target_real = os.path.realpath(target_by_id)
    source_device = source.split("[", 1)[0]
    ancestry_json = subprocess.run(
        [
            "lsblk",
            "--json",
            "--list",
            "--paths",
            "--inverse",
            "--output",
            "PATH,MODEL,SERIAL,TYPE",
            source_device,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    devices = json.loads(ancestry_json).get("blockdevices", [])
    ancestors: list[dict[str, Any]] = []

    def collect(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            ancestors.append(row)
            collect(row.get("children", []))

    collect(devices)
    assert_state_device_is_unprotected(ancestors, target_real, protected_serials)


def apply_storage_plan(
    plan: dict[str, Any],
    authorization: dict[str, Any],
    config: dict[str, Any],
    initial_report: dict[str, Any],
    state_dir: Path,
    *,
    confirmed_sha256: str,
    confirmed_serial: str,
    erasure_phrase: str,
    backup_verified: bool,
    recovery_media_verified: bool,
    runner: Callable[..., Any] = subprocess.run,
    report_provider: Callable[[dict[str, Any]], dict[str, Any]] = inspect_host,
    state_location_check: Callable[..., None] = ensure_state_location_off_target,
    effective_uid: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """Execute only the plan's listed argv after multiple exact confirmations."""
    if platform.system() != "Linux":
        raise RuntimeError("storage installation can run only from the Gentoo Linux live system")
    uid = effective_uid or getattr(os, "geteuid", lambda: -1)
    if uid() != 0:
        raise RuntimeError("storage installation requires the live environment's root account")
    auth_check = validate_stage_authorization(
        plan, authorization, confirmed_sha256, confirmed_serial, erasure_phrase
    )
    if not auth_check["valid"]:
        raise RuntimeError("authorization refused: " + "; ".join(auth_check["issues"]))
    plan_check = validate_storage_plan(
        plan, initial_report, backup_verified, recovery_media_verified, config
    )
    state_dir = state_dir.resolve(strict=True)
    protected_serials = (
        config["storage"]["system_target"]["serial"],
        config["storage"]["data_disk"]["serial"],
    )
    state_location_check(state_dir, plan["target"]["by_id"], protected_serials)
    state_path = state_dir / "gentoo-storage-state.json"
    event_path = state_dir / "gentoo-storage-events.jsonl"
    commands = plan["commands_for_review_only"]
    if state_path.exists():
        try:
            journal = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("storage checkpoint is unreadable or corrupt; refusing to continue") from exc
        if not isinstance(journal, dict):
            raise RuntimeError("storage checkpoint is unreadable or corrupt; refusing to continue")
        if journal.get("plan_sha256") != plan["sha256"]:
            raise RuntimeError("existing checkpoint belongs to a different plan")
        if journal.get("command_count") != len(commands):
            raise RuntimeError("existing checkpoint command list does not match the plan")
        if journal.get("started") is not None:
            raise RuntimeError(
                f"command {journal['started']} was interrupted after it began; inspect the disk manually"
            )
        latest = _exact_device_state(report_provider(config), plan)
        if journal.get("completed"):
            next_index = next_unstarted_command(commands, journal)
            if (
                latest != journal.get("last_verified_device_state")
                and not _is_expected_partition_settling(
                    latest, journal["completed"], next_index, plan, commands
                )
            ):
                raise RuntimeError("disk state changed since the last checkpoint; inspect manually")
        elif not plan_check["valid"]:
            raise RuntimeError("plan validation refused: " + "; ".join(plan_check["issues"]))
    else:
        if not plan_check["valid"]:
            raise RuntimeError("plan validation refused: " + "; ".join(plan_check["issues"]))
        journal = {
            "schema_version": 1,
            "plan_sha256": plan["sha256"],
            "target": plan["target"],
            "command_count": len(commands),
            "completed": [],
            "started": None,
            "last_verified_device_state": None,
        }
        _atomic_json(state_path, journal)

    while (index := next_unstarted_command(commands, journal)) is not None:
        current_report = report_provider(config)
        state_now = _exact_device_state(current_report, plan)
        if journal["completed"] == [0, 1, 2, 3, 4, 5] and index == 6:
            _assert_partition_aliases_match_target(state_now, plan)
        if not journal["completed"] and state_now != plan["observed_state"]:
            raise RuntimeError("target partition or mount state changed after planning")
        if journal["completed"] and state_now != journal.get("last_verified_device_state"):
            if not _is_expected_partition_settling(
                state_now, journal["completed"], index, plan, commands
            ):
                raise RuntimeError("disk state changed since the previous storage command")
        if not journal["completed"]:
            mounts = state_now.get("mountpoints", [])
            child_mounts = [
                point
                for child in state_now.get("children", [])
                for point in (child.get("mountpoints") or [])
                if point
            ]
            if any(mounts) or child_mounts:
                raise RuntimeError("target disk has mounted filesystems; unmount them before install")
        journal["started"] = index
        _atomic_json(state_path, journal)
        argv = commands[index]
        print("Running: " + " ".join(argv), flush=True)
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "command-started",
                "index": index,
                "argv": argv,
            },
        )
        try:
            runner(argv, check=True)
        except subprocess.CalledProcessError as exc:
            _append_event(
                event_path,
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "event": "command-failed",
                    "index": index,
                    "returncode": exc.returncode,
                },
            )
            raise
        latest = _exact_device_state(report_provider(config), plan)
        journal["completed"].append(index)
        journal["started"] = None
        journal["last_verified_device_state"] = latest
        _atomic_json(state_path, journal)
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "command-completed",
                "index": index,
                "returncode": 0,
                "device_state": latest,
            },
        )

    return {
        "status": "complete",
        "plan_sha256": plan["sha256"],
        "state_file": str(state_path),
        "event_log": str(event_path),
    }
