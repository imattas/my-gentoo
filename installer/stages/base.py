"""Build the Gentoo base-system configuration from observed device UUIDs."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from installer.discovery.host import inspect_host
from installer.planning.storage import plan_hash_matches
from installer.provisioning.configuration import (
    build_target_files,
    select_kde_systemd_profile,
    write_target_files,
)
from installer.stages.stage3 import verify_root_mapping
from installer.stages.storage import _atomic_json, ensure_state_location_off_target

GENTOO_ROOT = Path("/mnt/gentoo")


def _output(runner: Callable[..., Any], argv: list[str], *, input: str | None = None) -> str:
    result = runner(argv, check=True, capture_output=True, text=True, input=input)
    return result.stdout.strip()


def configure_base_system(
    storage_plan: dict[str, Any],
    state_dir: Path,
    workstation: dict[str, Any],
    package_config: dict[str, Any],
    kernel_config: dict[str, Any],
    *,
    timezone: str,
    hostname: str,
    locale: str = "en_US.UTF-8",
    runner: Callable[..., Any] = subprocess.run,
    root: Path = GENTOO_ROOT,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Configure profile, Portage, encrypted boot parameters, locale, and fstab."""
    if not plan_hash_matches(storage_plan):
        raise ValueError("storage plan content does not match its hash")
    expected_disk = workstation["storage"]["system_target"]
    if (
        storage_plan.get("target", {}).get("model") != expected_disk["model"]
        or storage_plan.get("target", {}).get("serial") != expected_disk["serial"]
        or not storage_plan.get("target", {}).get("by_id", "").startswith("/dev/disk/by-id/")
    ):
        raise ValueError("storage plan does not identify the configured system disk")

    state_dir = state_dir.resolve(strict=True)
    ensure_state_location_off_target(
        state_dir,
        storage_plan["target"]["by_id"],
        (
            expected_disk["serial"],
            workstation["storage"]["data_disk"]["serial"],
        ),
    )
    storage_state = json.loads(
        (state_dir / "gentoo-storage-state.json").read_text(encoding="utf-8")
    )
    stage3_state = json.loads(
        (state_dir / "gentoo-stage3-state.json").read_text(encoding="utf-8")
    )
    command_count = len(storage_plan["commands_for_review_only"])
    if (
        storage_state.get("plan_sha256") != storage_plan["sha256"]
        or storage_state.get("completed") != list(range(command_count))
        or storage_state.get("started") is not None
        or not stage3_state.get("complete")
        or stage3_state.get("sha512") != workstation["stage3"]["sha512"]
        or stage3_state.get("target") != str(root.resolve(strict=True))
    ):
        raise RuntimeError("storage and verified Stage 3 stages must be complete first")

    verify_root_mapping(storage_plan["target"]["by_id"], runner=runner)
    root_mount = _output(
        runner,
        ["findmnt", "--mountpoint", str(root), "--noheadings", "--output", "TARGET,SOURCE,FSTYPE"],
    ).split()
    if len(root_mount) != 3 or root_mount[0] != str(root) or root_mount[2] != "btrfs":
        raise RuntimeError("installed root is not mounted as Btrfs at the expected mount point")
    if root_mount[1].split("[", 1)[0] != "/dev/mapper/gentoo-root":
        raise RuntimeError("installed root is not mounted from the authorized encrypted mapping")
    efi_mount = _output(
        runner,
        ["findmnt", "--mountpoint", str(root / "efi"), "--noheadings", "--output", "TARGET,SOURCE,FSTYPE"],
    ).split()
    if len(efi_mount) != 3 or efi_mount[0] != str(root / "efi") or efi_mount[2] != "vfat":
        raise RuntimeError("EFI system partition is not mounted at /mnt/gentoo/efi")
    efi_source = _output(runner, ["readlink", "-f", "/dev/disk/by-partlabel/GENTOO-ESP"])
    if _output(runner, ["readlink", "-f", efi_mount[1]]) != efi_source:
        raise RuntimeError("mounted EFI filesystem is not the planned GENTOO-ESP partition")

    efi_device = "/dev/disk/by-partlabel/GENTOO-ESP"
    root_device = "/dev/mapper/gentoo-root"
    crypt_device = "/dev/disk/by-partlabel/GENTOO-CRYPTROOT"
    efi_uuid = _output(runner, ["blkid", "-s", "UUID", "-o", "value", efi_device])
    btrfs_uuid = _output(runner, ["blkid", "-s", "UUID", "-o", "value", root_device])
    luks_uuid = _output(runner, ["cryptsetup", "luksUUID", crypt_device])
    efi_type = _output(runner, ["blkid", "-s", "TYPE", "-o", "value", efi_device])
    root_type = _output(runner, ["blkid", "-s", "TYPE", "-o", "value", root_device])
    if efi_type != "vfat" or root_type != "btrfs":
        raise RuntimeError("filesystem type does not match the planned EFI and encrypted Btrfs layout")

    zoneinfo = root / "usr/share/zoneinfo" / timezone
    if not zoneinfo.is_file():
        raise ValueError(f"timezone is not present in the installed Stage 3: {timezone}")
    runner(
        ["chroot", str(root), "gcc", "-march=znver4", "-x", "c", "-fsyntax-only", "-"],
        check=True,
        input="int main(void) { return 0; }\n",
        text=True,
    )

    profile_list = _output(runner, ["chroot", str(root), "eselect", "profile", "list"])
    profile_id = select_kde_systemd_profile(profile_list, package_config["profile_release"])

    if report is None:
        report = inspect_host(workstation)
    cpu_threads = report.get("host", {}).get("cpu_threads")
    memory_gib = report.get("host", {}).get("memory_gib")
    if not isinstance(cpu_threads, int) or not isinstance(memory_gib, (int, float)):
        raise RuntimeError("live CPU and memory discovery is required before setting build parallelism")
    files = build_target_files(
        workstation,
        package_config,
        kernel_config,
        efi_uuid=efi_uuid,
        btrfs_uuid=btrfs_uuid,
        luks_uuid=luks_uuid,
        cpu_threads=cpu_threads,
        memory_gib=int(memory_gib),
        timezone=timezone,
        hostname=hostname,
        locale=locale,
    )
    runner(["chroot", str(root), "eselect", "profile", "set", profile_id], check=True)
    write_target_files(root, files)
    runner(
        ["chroot", str(root), "ln", "-snf", f"/usr/share/zoneinfo/{timezone}", "/etc/localtime"],
        check=True,
    )
    runner(["chroot", str(root), "locale-gen"], check=True)
    result = {
        "status": "configured",
        "profile": package_config["desktop_profile"],
        "efi_uuid": efi_uuid,
        "btrfs_uuid": btrfs_uuid,
        "luks_uuid": luks_uuid,
        "files_written": sorted(files),
        "next": "review emerge --pretend output before package installation",
    }
    _atomic_json(
        state_dir / "gentoo-base-config-state.json",
        {
            "schema_version": 1,
            "storage_plan_sha256": storage_plan["sha256"],
            "profile": package_config["desktop_profile"],
            "efi_uuid": efi_uuid,
            "btrfs_uuid": btrfs_uuid,
            "luks_uuid": luks_uuid,
            "files_written": sorted(files),
            "timezone": timezone,
            "locale": locale,
            "hostname": hostname,
        },
    )
    return result
