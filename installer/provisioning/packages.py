"""Render reviewable Gentoo package operations as argv arrays."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable

from installer.planning.storage import plan_hash_matches
from installer.stages.stage3 import verify_root_mapping
from installer.stages.storage import _append_event, _atomic_json, ensure_state_location_off_target


PACKAGE_SETS = ("base", "desktop", "gaming", "development", "virtualization", "security_backup")

def render_emerge_commands(
    config: dict[str, Any],
    package_set: str,
    target_root: str = "/mnt/gentoo",
    *,
    non_interactive: bool = False,
) -> list[list[str]]:
    if target_root != "/mnt/gentoo":
        raise ValueError("package operations are bound to the configured Gentoo root")
    sets = config.get("sets", {})
    if package_set not in sets:
        raise ValueError(f"unknown package set: {package_set}")
    prefix = ["chroot", target_root, "emerge"]
    confirmation = ["--ask=n"] if non_interactive else ["--ask"]
    commands: list[list[str]] = []
    if package_set == "base":
        commands.append(
            prefix + confirmation + ["--verbose", "--update", "--deep", "--newuse", "--with-bdeps=y", "@world"]
        )
        support_packages = [
            atom for atom in sets[package_set] if atom != "sys-kernel/gentoo-kernel-bin"
        ]
        commands.append(prefix + confirmation + ["--verbose", *support_packages])
        commands.append(
            prefix + confirmation + ["--verbose", "sys-kernel/gentoo-kernel-bin"]
        )
    else:
        commands.append(prefix + confirmation + ["--verbose", *sets[package_set]])
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
                "install", "-d",
                f"{target_root}/etc/systemd/system/multi-user.target.wants",
                f"{target_root}/etc/systemd/system",
            ]
        )
        commands.append([
            "ln", "-sfn", "/usr/lib/systemd/system/NetworkManager.service",
            f"{target_root}/etc/systemd/system/multi-user.target.wants/NetworkManager.service",
        ])
        commands.append([
            "ln", "-sfn", "/usr/lib/systemd/system/sddm.service",
            f"{target_root}/etc/systemd/system/display-manager.service",
        ])
        commands.append(["systemctl", f"--root={target_root}", "set-default", "graphical.target"])
    elif package_set == "gaming":
        commands = [
            prefix + confirmation + ["--verbose", "app-eselect/eselect-repository", "dev-vcs/git"],
            ["chroot", target_root, "eselect", "repository", "enable", "steam-overlay"],
            ["chroot", target_root, "emaint", "sync", "-r", "steam-overlay"],
            prefix + confirmation + ["--verbose", *sets[package_set]],
        ]
    return commands


def validate_boot_assets(root: Path) -> list[str]:
    efi = root / "efi"
    bootloader = efi / "EFI" / "systemd" / "systemd-bootx64.efi"
    production = efi / "EFI" / "Linux" / "gentoo-production.efi"
    linux_dir = production.parent
    expected_cmdline_path = root / "etc" / "kernel" / "cmdline"
    try:
        expected_cmdline = expected_cmdline_path.read_text(encoding="utf-8").split()
    except OSError as exc:
        raise RuntimeError("configured kernel command line is missing") from exc
    if bootloader.is_symlink() or not _is_efi_application(bootloader):
        raise RuntimeError("systemd-boot EFI application is missing or invalid")
    generated = [
        image
        for image in linux_dir.glob("*.efi")
        if image not in (production, linux_dir / "gentoo-fallback.efi")
        and not image.name.startswith("gentoo-experimental")
        and _is_unified_kernel_image(image)
        and _uki_has_command_line(image, expected_cmdline)
    ]
    if generated:
        source = max(generated, key=lambda image: image.stat().st_mtime_ns)
        import shutil

        if (
            not production.is_symlink()
            and _is_unified_kernel_image(production)
            and _uki_has_command_line(production, expected_cmdline)
            and production.read_bytes() != source.read_bytes()
        ):
            _atomic_copy(production, linux_dir / "gentoo-fallback.efi")
        _atomic_copy(source, production)
    if (
        production.is_symlink()
        or not _is_unified_kernel_image(production)
        or not _uki_has_command_line(production, expected_cmdline)
    ):
        raise RuntimeError("systemd-boot and a valid EFI application production UKI are required")
    fallback = linux_dir / "gentoo-fallback.efi"
    if fallback.exists() and (
        fallback.is_symlink()
        or not _is_unified_kernel_image(fallback)
        or not _uki_has_command_line(fallback, expected_cmdline)
    ):
        raise RuntimeError("previous production fallback UKI is invalid")
    _write_systemd_boot_entries(efi, fallback.is_file())
    installed = [production.name]
    if fallback.is_file():
        installed.append(fallback.name)
    return installed


def rollback_production_uki(root: Path) -> str:
    """Restore the previous production UKI after validating its EFI contents."""
    efi = root / "efi"
    linux_dir = efi / "EFI" / "Linux"
    bootloader = efi / "EFI" / "systemd" / "systemd-bootx64.efi"
    fallback = linux_dir / "gentoo-fallback.efi"
    production = linux_dir / "gentoo-production.efi"
    expected_cmdline_path = root / "etc" / "kernel" / "cmdline"
    try:
        expected_cmdline = expected_cmdline_path.read_text(encoding="utf-8").split()
    except OSError as exc:
        raise RuntimeError("configured kernel command line is missing") from exc
    if bootloader.is_symlink() or not _is_efi_application(bootloader):
        raise RuntimeError("systemd-boot EFI application is missing or invalid")
    if (
        fallback.is_symlink()
        or not _is_unified_kernel_image(fallback)
        or not _uki_has_command_line(fallback, expected_cmdline)
    ):
        raise RuntimeError("known-good fallback UKI is missing, invalid, or has a stale command line")
    _atomic_copy(fallback, production)
    return production.name


def stage_experimental_uki(
    root: Path, candidate: Path, entry_name: str = "gentoo-experimental"
) -> str:
    """Install a validated experimental UKI under its own non-default boot entry."""
    if not isinstance(entry_name, str) or not re.fullmatch(
        r"gentoo-experimental(?:-[a-z0-9][a-z0-9_-]{0,47})?", entry_name
    ):
        raise ValueError("experimental boot entry name must use the gentoo-experimental prefix")
    efi = root / "efi"
    linux_dir = efi / "EFI" / "Linux"
    bootloader = efi / "EFI" / "systemd" / "systemd-bootx64.efi"
    production = linux_dir / "gentoo-production.efi"
    loader_dir = efi / "loader"
    entries_dir = loader_dir / "entries"
    loader_conf = loader_dir / "loader.conf"
    production_entry = entries_dir / "gentoo-production.conf"
    if candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError("experimental UKI candidate must be a regular non-symlink file")
    candidate = candidate.resolve(strict=True)
    try:
        expected_cmdline = (root / "etc" / "kernel" / "cmdline").read_text(
            encoding="utf-8"
        ).split()
    except OSError as exc:
        raise RuntimeError("configured kernel command line is missing") from exc
    if bootloader.is_symlink() or not _is_efi_application(bootloader):
        raise RuntimeError("systemd-boot EFI application is missing or invalid")
    if (
        production.is_symlink()
        or not _is_unified_kernel_image(production)
        or not _uki_has_command_line(production, expected_cmdline)
    ):
        raise RuntimeError("valid production UKI is required before staging an experimental kernel")
    if (
        not _is_unified_kernel_image(candidate)
        or not _uki_has_command_line(candidate, expected_cmdline)
    ):
        raise RuntimeError("experimental UKI candidate is invalid or has a stale root command line")
    for path in (loader_dir, entries_dir):
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"refusing unsafe systemd-boot directory: {path}")
    for path in (loader_conf, production_entry):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"required production boot configuration is missing or unsafe: {path}")
    if "default gentoo-production" not in loader_conf.read_text(encoding="utf-8").splitlines():
        raise RuntimeError("experimental staging requires the production entry to remain the default")
    if production_entry.read_text(encoding="utf-8").splitlines()[-1:] != [
        "efi /EFI/Linux/gentoo-production.efi"
    ]:
        raise RuntimeError("production boot entry does not point to the production UKI")

    experimental = linux_dir / f"{entry_name}.efi"
    entry = entries_dir / f"{entry_name}.conf"
    for path in (experimental, entry):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError(f"refusing unsafe experimental boot asset: {path}")
    _atomic_copy(candidate, experimental)
    _atomic_write_text(
        entry,
        "title Gentoo Workstation (experimental kernel)\n"
        f"efi /EFI/Linux/{entry_name}.efi\n",
    )
    return experimental.name


def _atomic_copy(source: Path, destination: Path) -> None:
    import shutil

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".new", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _write_systemd_boot_entries(efi: Path, has_fallback: bool) -> None:
    loader_dir = efi / "loader"
    entries_dir = loader_dir / "entries"
    for directory in (loader_dir, entries_dir):
        if directory.is_symlink():
            raise RuntimeError(f"refusing symlinked systemd-boot directory: {directory}")
        directory.mkdir(exist_ok=True)

    managed = {
        loader_dir / "loader.conf": "default gentoo-production\ntimeout 5\n",
        entries_dir / "gentoo-production.conf": (
            "title Gentoo Workstation (production)\n"
            "efi /EFI/Linux/gentoo-production.efi\n"
        ),
    }
    fallback_entry = entries_dir / "gentoo-fallback.conf"
    if has_fallback:
        managed[fallback_entry] = (
            "title Gentoo Workstation (previous production kernel)\n"
            "efi /EFI/Linux/gentoo-fallback.efi\n"
        )
    elif fallback_entry.exists() or fallback_entry.is_symlink():
        if fallback_entry.is_symlink() or not fallback_entry.is_file():
            raise RuntimeError(f"refusing unsafe systemd-boot entry: {fallback_entry}")
        fallback_entry.unlink()

    for destination, contents in managed.items():
        if destination.is_symlink():
            raise RuntimeError(f"refusing symlinked systemd-boot file: {destination}")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=destination.name + ".", suffix=".new", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def _atomic_write_text(destination: Path, contents: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".new", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def recover_failed_package_checkpoint(
    package_set: str,
    package_config: dict[str, Any],
    state_dir: Path,
    command_index: int,
    confirmed_log_sha256: str,
    storage_plan_sha256: str,
    *,
    non_interactive: bool = False,
    kernel_repair: Callable[[], str] | None = None,
    desktop_repair: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Reopen a package checkpoint after a hash-reviewed safe failure and repair."""
    if package_set not in PACKAGE_SETS:
        raise ValueError(f"unknown package set: {package_set}")
    state_dir = state_dir.resolve(strict=True)
    state_path = state_dir / f"gentoo-packages-{package_set}.json"
    event_path = state_dir / "gentoo-package-events.jsonl"
    journal = json.loads(state_path.read_text(encoding="utf-8"))
    storage_state = json.loads((state_dir / "gentoo-storage-state.json").read_text(encoding="utf-8"))
    base_state = json.loads((state_dir / "gentoo-base-config-state.json").read_text(encoding="utf-8"))
    if (
        journal.get("package_set") != package_set
        or journal.get("complete")
        or journal.get("started") != command_index
        or journal.get("completed") != list(range(command_index))
        or journal.get("storage_plan_sha256") != storage_plan_sha256
        or storage_state.get("plan_sha256") != storage_plan_sha256
        or base_state.get("storage_plan_sha256") != storage_plan_sha256
    ):
        raise RuntimeError("package, storage, and base configuration checkpoints do not identify this failed command")

    events = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching_failure = [
        event for event in events
        if event.get("event") == "package-command-failed"
        and event.get("package_set") == package_set
        and event.get("index") == command_index
    ]
    if not matching_failure:
        raise RuntimeError("failed package event or its command log is missing")
    failed_log = Path(matching_failure[-1].get("log", ""))
    log_dir = (state_dir / "logs").resolve(strict=True)
    if failed_log.is_symlink() or failed_log.resolve(strict=True).parent != log_dir:
        raise RuntimeError("failed package log is outside the protected installer log directory")
    log_path = failed_log.resolve(strict=True)
    if not log_path.is_file():
        raise RuntimeError("failed package event or its command log is missing")

    log_bytes = log_path.read_bytes()
    log_sha256 = hashlib.sha256(log_bytes).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", confirmed_log_sha256) or log_sha256 != confirmed_log_sha256:
        raise RuntimeError("failed command log hash does not match the operator-reviewed hash")
    log_text = log_bytes.decode("utf-8", errors="replace")
    unavailable_atom = 'emerge: there are no ebuilds to satisfy "' in log_text
    masked_atom = (
        '!!! All ebuilds that could satisfy "' in log_text
        and "masked packages is required to complete your request" in log_text
    )
    blocked_conflict = "Conflict:" in log_text and "blocks (" in log_text
    use_conflict = "The following USE changes are necessary to proceed:" in log_text
    premerge_resolution = unavailable_atom or masked_atom or blocked_conflict or use_conflict
    kernel_postinst = (
        "ERROR: sys-kernel/gentoo-kernel-bin-" in log_text
        and "failed (postinst phase)" in log_text
        and "Module 'btrfs' cannot be installed" in log_text
        and "emerge --config '=sys-kernel/gentoo-kernel-bin-" in log_text
    )
    desktop_sysv_hook = (
        package_set == "desktop"
        and command_index == 1
        and "systemd-sysv-install --root=/mnt/gentoo enable NetworkManager" in log_text
        and "failed to run command '/usr/sbin/update-rc.d': No such file or directory" in log_text
    )
    if (
        kernel_postinst
        and kernel_repair is None
    ):
        raise RuntimeError("known kernel post-install failure requires the explicit repair path")
    if desktop_sysv_hook and desktop_repair is None:
        raise RuntimeError("known desktop service failure requires the explicit repair path")
    if not (kernel_postinst or desktop_sysv_hook) and (
        not premerge_resolution
        or ">>> emerge (" in log_text
        or "Compiling/Merging (" in log_text
        or "Merging Binary (" in log_text
    ):
        raise RuntimeError("failed log does not prove a safe package resolution or kernel post-install failure")
    commands = render_emerge_commands(
        package_config, package_set, non_interactive=non_interactive
    )
    for completed_index in range(command_index):
        starts = [
            event for event in events
            if event.get("event") == "package-command-started"
            and event.get("package_set") == package_set
            and event.get("index") == completed_index
        ]
        if not starts or starts[-1].get("argv") != commands[completed_index]:
            raise RuntimeError("a completed package command changed; checkpoint recovery is unsafe")

    if kernel_postinst:
        repair_log = kernel_repair()
        repair_path = state_dir / "logs" / f"package-recovery-kernel-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
        repair_path.write_text(repair_log, encoding="utf-8")
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "package-kernel-postinst-repaired",
                "package_set": package_set,
                "index": command_index,
                "failed_log_sha256": log_sha256,
                "repair_log": str(repair_path),
                "repair_log_sha256": hashlib.sha256(repair_log.encode()).hexdigest(),
            },
        )
    if desktop_sysv_hook:
        repair_log = desktop_repair()
        repair_path = state_dir / "logs" / f"package-recovery-desktop-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
        repair_path.write_text(repair_log, encoding="utf-8")
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "package-desktop-services-repaired",
                "package_set": package_set,
                "index": command_index,
                "failed_log_sha256": log_sha256,
                "repair_log": str(repair_path),
                "repair_log_sha256": hashlib.sha256(repair_log.encode()).hexdigest(),
            },
        )

    previous_digest = journal.get("command_sha256")
    new_digest = hashlib.sha256(
        json.dumps(commands, separators=(",", ":")).encode()
    ).hexdigest()
    journal["command_sha256"] = new_digest
    journal["started"] = None
    recovery = {
        "failed_index": command_index,
        "log_sha256": log_sha256,
        "previous_command_sha256": previous_digest,
        "new_command_sha256": new_digest,
        "recovered_at": datetime.now(timezone.utc).isoformat(),
    }
    journal.setdefault("recoveries", []).append(recovery)
    _atomic_json(state_path, journal)
    _append_event(
        event_path,
        {
            "time": recovery["recovered_at"],
            "event": "package-checkpoint-recovered",
            "package_set": package_set,
            **recovery,
        },
    )
    return {"status": "ready-to-resume", "package_set": package_set, **recovery}


def _is_efi_application(path: Path) -> bool:
    """Check the bounded PE/COFF headers and EFI application subsystem."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if len(data) < 0x40 or data[:2] != b"MZ":
        return False
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset > len(data) - 24 or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        return False
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    optional_offset = pe_offset + 24
    if optional_size < 70 or optional_offset + optional_size > len(data):
        return False
    if struct.unpack_from("<H", data, optional_offset)[0] not in {0x10B, 0x20B}:
        return False
    return struct.unpack_from("<H", data, optional_offset + 68)[0] == 10


def _is_unified_kernel_image(path: Path) -> bool:
    """Require a PE EFI app carrying non-empty kernel, initrd, and cmdline sections."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if not _is_efi_application(path):
        return False
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    section_table = pe_offset + 24 + optional_size
    if section_count == 0 or section_table + section_count * 40 > len(data):
        return False
    sections: dict[str, bytes] = {}
    for index in range(section_count):
        offset = section_table + index * 40
        name = data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii", errors="ignore")
        raw_size = struct.unpack_from("<I", data, offset + 16)[0]
        raw_offset = struct.unpack_from("<I", data, offset + 20)[0]
        if raw_size and raw_offset <= len(data) and raw_size <= len(data) - raw_offset:
            sections[name] = data[raw_offset : raw_offset + raw_size]
    return all(sections.get(name) for name in (".linux", ".initrd", ".cmdline"))


def _uki_has_command_line(path: Path, expected_tokens: list[str]) -> bool:
    data = path.read_bytes()
    if not _is_efi_application(path):
        return False
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    section_table = pe_offset + 24 + optional_size
    if section_table + section_count * 40 > len(data):
        return False
    for index in range(section_count):
        offset = section_table + index * 40
        name = data[offset : offset + 8].split(b"\0", 1)[0]
        if name != b".cmdline":
            continue
        size = struct.unpack_from("<I", data, offset + 16)[0]
        raw_offset = struct.unpack_from("<I", data, offset + 20)[0]
        if not size or raw_offset > len(data) or size > len(data) - raw_offset:
            return False
        actual_tokens = set(
            data[raw_offset : raw_offset + size]
            .decode("utf-8", errors="ignore")
            .strip("\0")
            .split()
        )
        return set(expected_tokens).issubset(actual_tokens)
    return False


def run_package_stage(
    package_set: str,
    package_config: dict[str, Any],
    storage_plan: dict[str, Any],
    state_dir: Path,
    workstation: dict[str, Any],
    *,
    root: Path = Path("/mnt/gentoo"),
    non_interactive: bool = False,
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
    command_list = render_emerge_commands(
        package_config, package_set, str(root), non_interactive=non_interactive
    )
    if package_set == "base":
        efi_stat = os.statvfs(root / "efi")
        free_bytes = efi_stat.f_bavail * efi_stat.f_frsize
        if free_bytes < 512 * 1024**2:
            raise RuntimeError("less than 512 MiB remains free on the EFI partition")

    state_path = state_dir / f"gentoo-packages-{package_set}.json"
    event_path = state_dir / "gentoo-package-events.jsonl"
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
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
        prior_attempts = 0
        if event_path.is_file():
            prior_attempts = sum(
                1
                for line in event_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
                and (event := json.loads(line)).get("event") == "package-command-started"
                and event.get("package_set") == package_set
                and event.get("index") == index
            )
        log_path = log_dir / f"packages-{package_set}-command-{index}-attempt-{prior_attempts + 1:02d}.log"
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
        try:
            command_result = runner(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            log_path.write_text(output, encoding="utf-8")
            _append_event(
                event_path,
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "event": "package-command-failed",
                    "package_set": package_set,
                    "index": index,
                    "returncode": exc.returncode,
                    "log": str(log_path),
                },
            )
            raise RuntimeError(
                f"package command {index} failed; inspect {log_path} before recovery"
            ) from exc
        output = (command_result.stdout or "") + (command_result.stderr or "")
        log_path.write_text(output, encoding="utf-8")
        if output:
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
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
                "log": str(log_path),
            },
        )

    journal["complete"] = True
    _atomic_json(state_path, journal)
    return {"status": "complete", "package_set": package_set, "state_file": str(state_path)}
