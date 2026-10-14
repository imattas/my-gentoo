"""Pure renderers for Portage, fstab, kernel cmdline, and profile selection."""

from __future__ import annotations

import re
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any


def render_make_conf(config: dict[str, Any], cpu_threads: int, memory_gib: int) -> str:
    if cpu_threads < 1 or memory_gib < 1:
        raise ValueError("CPU thread count and available memory must be positive")
    make_jobs = max(1, min(cpu_threads, memory_gib // 8))
    emerge_jobs = max(1, min(cpu_threads, memory_gib // 16, 4))
    return "\n".join(
        [
            f'CFLAGS="{config["compiler_flags_candidate"]}"',
            'CXXFLAGS="${CFLAGS}"',
            f'MAKEOPTS="-j{make_jobs}"',
            f'EMERGE_DEFAULT_OPTS="--jobs={emerge_jobs} --load-average={cpu_threads}"',
            f'USE="{" ".join(config["global_use"])}"',
            'ABI_X86="64 32"',
            f'VIDEO_CARDS="{" ".join(config["video_cards"])}"',
            'INPUT_DEVICES="libinput"',
            "",
        ]
    )


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("filesystem and encryption UUIDs must come from live-device inspection") from exc


def render_fstab(efi_uuid: str, btrfs_uuid: str) -> str:
    efi = _uuid(efi_uuid)
    btrfs = _uuid(btrfs_uuid)
    rows = [f"UUID={efi} /efi vfat umask=0077,noatime 0 2"]
    for path, subvol in (("/", "@"), ("/home", "@home"), ("/.snapshots", "@snapshots"), ("/var/log", "@log")):
        rows.append(
            f"UUID={btrfs} {path} btrfs compress=zstd:3,noatime,subvol={subvol} 0 0"
        )
    return "\n".join(rows) + "\n"


def render_kernel_cmdline(luks_uuid: str) -> str:
    root_luks = _uuid(luks_uuid)
    return (
        f"rd.luks.name={root_luks}=gentoo-root "
        "root=/dev/mapper/gentoo-root rootflags=subvol=@ rw"
    )


def select_kde_systemd_profile(profile_list: str, profile_release: str) -> str:
    expected = f"default/linux/amd64/{profile_release}/desktop/kde/systemd"
    matches = re.findall(r"^\s*\[(\d+)\]\s+(\S+)", profile_list, flags=re.MULTILINE)
    ids = [profile_id for profile_id, path in matches if path == expected]
    if len(ids) != 1:
        raise ValueError(f"expected exactly one available Gentoo profile {expected}")
    return ids[0]


def render_package_use(entries: list[list[str]]) -> str:
    return "".join(" ".join(entry) + "\n" for entry in entries)


def render_dracut_config() -> str:
    return 'hostonly="no"\nadd_dracutmodules+=" crypt btrfs "\n'


def build_target_files(
    workstation: dict[str, Any],
    packages: dict[str, Any],
    kernel: dict[str, Any],
    *,
    efi_uuid: str,
    btrfs_uuid: str,
    luks_uuid: str,
    cpu_threads: int,
    memory_gib: int,
    timezone: str,
    hostname: str,
    locale: str = "en_US.UTF-8",
) -> dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", hostname):
        raise ValueError("hostname must be a simple DNS hostname")
    if not re.fullmatch(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*", timezone):
        raise ValueError("timezone must be a relative zoneinfo name")
    if not re.fullmatch(r"[A-Za-z0-9_.@+-]+", locale):
        raise ValueError("locale must be a simple locale identifier")
    make_config = {
        "compiler_flags_candidate": workstation["system"]["compiler_flags_candidate"],
        "global_use": packages["global_use"],
        "video_cards": packages["video_cards"],
    }
    kernel_cmdline = render_kernel_cmdline(luks_uuid)
    if kernel.get("root_mapper") != "/dev/mapper/gentoo-root" or kernel.get("efi_mount") != "/efi":
        raise ValueError("kernel config does not match the approved encrypted-root layout")
    return {
        "etc/fstab": render_fstab(efi_uuid, btrfs_uuid),
        "etc/hostname": hostname + "\n",
        "etc/locale.gen": locale + " UTF-8\n",
        "etc/locale.conf": f"LANG={locale}\n",
        "etc/timezone": timezone + "\n",
        "etc/kernel/cmdline": kernel_cmdline + "\n",
        "etc/dracut.conf.d/gentoo-workstation.conf": render_dracut_config(),
        "etc/portage/make.conf": render_make_conf(make_config, cpu_threads, memory_gib),
        "etc/portage/package.use/gentoo-workstation": render_package_use(packages["package_use"]),
        "etc/sudoers.d/10-gentoo-workstation-wheel": "%wheel ALL=(ALL:ALL) ALL\n",
    }


def write_target_files(target_root: Path, files: dict[str, str]) -> None:
    root = target_root.resolve(strict=True)
    for relative, content in files.items():
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or not relative_path.parts:
            raise ValueError(f"unsafe target path: {relative}")
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.parent.resolve().is_relative_to(root):
            raise ValueError(f"target path escapes the installed root: {relative}")
        fd, temporary_name = tempfile.mkstemp(prefix=".gentoo-install-", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_name, 0o440 if relative.startswith("etc/sudoers.d/") else 0o644)
            os.replace(temporary_name, destination)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
