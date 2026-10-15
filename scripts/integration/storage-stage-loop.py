#!/usr/bin/env python3
"""Exercise the destructive storage stage against a new sparse file via loop."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid

from installer.authorization.plan import create_authorization_record
from installer.planning.storage import render_storage_plan
from installer.stages.storage import apply_storage_plan


ROOT = Path(__file__).resolve().parents[2]
MOUNTPOINTS = (
    Path("/mnt/gentoo-rescue"),
    Path("/mnt/gentoo/efi"),
    Path("/mnt/gentoo/var/log"),
    Path("/mnt/gentoo/.snapshots"),
    Path("/mnt/gentoo/home"),
    Path("/mnt/gentoo"),
    Path("/mnt/gentoo-top"),
)
ROOT_MAPPER = Path("/dev/mapper/gentoo-root")
PARTLABELS = {
    Path("/dev/disk/by-partlabel/GENTOO-ESP"): 1,
    Path("/dev/disk/by-partlabel/GENTOO-CRYPTROOT"): 2,
}


def run(argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=True,
        text=True,
        capture_output=capture,
    )


def mountpoints(value: list[str | None] | None) -> list[str]:
    return [point for point in (value or []) if point]


def ensure_unclaimed_paths(by_id: Path) -> None:
    if by_id.exists() or by_id.is_symlink():
        raise RuntimeError(f"refusing existing test by-id path: {by_id}")
    for path in PARTLABELS:
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"refusing existing partition label path: {path}")
    if ROOT_MAPPER.exists() or ROOT_MAPPER.is_symlink():
        raise RuntimeError(f"refusing existing mapper path: {ROOT_MAPPER}")
    for root in (Path("/mnt/gentoo"), Path("/mnt/gentoo-top")):
        if root.exists() or root.is_symlink():
            raise RuntimeError(f"refusing existing storage test mount directory: {root}")
    for path in MOUNTPOINTS:
        probe = subprocess.run(["mountpoint", "--quiet", str(path)], check=False)
        if probe.returncode == 0:
            raise RuntimeError(f"refusing to use already-mounted path: {path}")


def block_report(loopdev: str, by_id: str, config: dict) -> dict:
    raw = run(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--paths",
            "--tree",
            "--output",
            "PATH,TYPE,SIZE,PTTYPE,FSTYPE,MOUNTPOINTS,PARTLABEL",
            loopdev,
        ],
        capture=True,
    )
    observed = json.loads(raw.stdout)["blockdevices"][0]
    children = [
        {
            "path": child.get("path"),
            "partlabel": child.get("partlabel"),
            "size": child.get("size"),
            "fstype": child.get("fstype"),
            "mountpoints": mountpoints(child.get("mountpoints")),
        }
        for child in observed.get("children") or []
    ]
    disk = {
        # The planner accepts whole disks; this harness exposes its disposable
        # loop-backed virtual disk through the same block-device contract.
        "type": "disk",
        "path": observed["path"],
        "model": config["storage"]["system_target"]["model"],
        "serial": config["storage"]["system_target"]["serial"],
        "size": observed["size"],
        "by_id": [by_id],
        "pttype": observed.get("pttype"),
        "fstype": observed.get("fstype"),
        "mountpoints": mountpoints(observed.get("mountpoints")),
        "children": children,
    }
    return {
        "read_only": True,
        "firmware": {"boot_mode": "UEFI"},
        "target": {"status": "identified", "match_count": 1},
        "block_devices": [disk],
    }


def require_loop_partition(path: Path, loopdev: str, partition: int) -> None:
    expected = f"{loopdev}p{partition}"
    actual = os.path.realpath(path)
    if actual != expected:
        raise RuntimeError(f"{path} resolves to {actual}; expected disposable partition {expected}")


def require_loop_mapper(loopdev: str) -> None:
    status = run(["cryptsetup", "status", "gentoo-root"], capture=True).stdout
    device = next(
        (line.split(":", 1)[1].strip() for line in status.splitlines() if line.strip().startswith("device:")),
        None,
    )
    if device != f"{loopdev}p2":
        raise RuntimeError("gentoo-root mapper does not resolve to the disposable loop image")


def materialize_test_partition_links(loopdev: str) -> None:
    """Emulate udev's by-partlabel links when the WSL udev rules omit them."""
    links = (
        (1, "GENTOO-ESP"),
        (2, "GENTOO-CRYPTROOT"),
    )
    verified = []
    for number, expected_label in links:
        partition = f"{loopdev}p{number}"
        probe = subprocess.run(
            ["blkid", "--probe", "--output", "export", partition],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode:
            return
        properties = dict(
            line.split("=", 1) for line in probe.stdout.splitlines() if "=" in line
        )
        actual_label = properties.get("PART_ENTRY_NAME")
        if actual_label is None:
            return
        if actual_label != expected_label:
            raise RuntimeError(f"unexpected GPT partition label on {partition}: {actual_label}")
        verified.append((Path(f"/dev/disk/by-partlabel/{expected_label}"), partition))

    directory = Path("/dev/disk/by-partlabel")
    if directory.is_symlink():
        raise RuntimeError(f"refusing symlinked partition-label directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    for alias, partition in verified:
        if alias.exists() or alias.is_symlink():
            if os.path.realpath(alias) != partition:
                raise RuntimeError(f"refusing conflicting partition identity link: {alias}")
        else:
            alias.symlink_to(partition)


def run_target_command(
    argv: list[str], *, loopdev: str, by_id: Path, keyfile: Path
) -> subprocess.CompletedProcess[str]:
    for item in argv:
        if item == str(by_id):
            if os.path.realpath(item) != loopdev:
                raise RuntimeError("planned whole-disk path no longer resolves to the disposable loop")
        elif item in {str(path) for path in PARTLABELS}:
            require_loop_partition(Path(item), loopdev, PARTLABELS[Path(item)])
        elif item == str(ROOT_MAPPER):
            require_loop_mapper(loopdev)

    actual = argv
    if argv[:2] == ["cryptsetup", "luksFormat"]:
        actual = argv[:4] + ["--batch-mode", "--key-file", str(keyfile), argv[4]]
    elif argv[:2] == ["cryptsetup", "open"]:
        actual = argv[:2] + ["--key-file", str(keyfile)] + argv[2:]
    result = run(actual)
    if argv[:2] == ["udevadm", "settle"]:
        materialize_test_partition_links(loopdev)
    return result


def verify_completed_stage(loopdev: str, by_id: Path, config: dict) -> None:
    esp_partition = Path("/dev/disk/by-partlabel/GENTOO-ESP")
    root_partition = Path("/dev/disk/by-partlabel/GENTOO-CRYPTROOT")
    require_loop_partition(esp_partition, loopdev, 1)
    require_loop_partition(root_partition, loopdev, 2)
    require_loop_mapper(loopdev)
    expected_mounts = {
        "/mnt/gentoo": "@",
        "/mnt/gentoo/home": "@home",
        "/mnt/gentoo/.snapshots": "@snapshots",
        "/mnt/gentoo/var/log": "@log",
        "/mnt/gentoo/efi": "GENTOO-ESP",
    }
    for target, subvolume in expected_mounts.items():
        mounted = run(
            ["findmnt", "--noheadings", "--output", "SOURCE,FSTYPE,OPTIONS", "--target", target],
            capture=True,
        ).stdout.split()
        if len(mounted) != 3:
            raise RuntimeError(f"mount verification returned an unexpected result for {target}")
        source, fstype, options = mounted
        if target.endswith("/efi"):
            if os.path.realpath(source) != os.path.realpath(str(esp_partition)) or fstype != "vfat":
                raise RuntimeError("EFI mount does not use the disposable GENTOO-ESP partition")
        else:
            actual_subvolume = next(
                (item.split("=", 1)[1] for item in options.split(",") if item.startswith("subvol=")),
                "",
            ).strip("/")
            if fstype != "btrfs" or actual_subvolume != subvolume.strip("/"):
                raise RuntimeError(f"Btrfs subvolume {subvolume} is not mounted at {target}; got {options}")
    root_report = block_report(loopdev, str(by_id), config)
    if root_report["target"]["status"] != "identified":
        raise RuntimeError("disposable loop target lost its reported identity")
    print("PASS: storage stage partitioned, encrypted, formatted, and mounted the disposable loop image")
    for target, subvolume in expected_mounts.items():
        print(f"PASS: {target} mounted from {subvolume}")


def make_test_uki(command_line: str, kernel: bytes) -> bytes:
    sections = (".linux", ".initrd", ".cmdline")
    payloads = {
        ".linux": kernel,
        ".initrd": b"disposable initramfs fixture",
        ".cmdline": command_line.encode("utf-8") + b"\0",
    }
    image = bytearray(0x500)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)
    image[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", image, 0x46, len(sections))
    struct.pack_into("<H", image, 0x54, 0xE0)
    struct.pack_into("<H", image, 0x58, 0x20B)
    struct.pack_into("<H", image, 0x9C, 10)
    for index, name in enumerate(sections):
        section = 0x138 + index * 40
        image[section : section + 8] = name.encode().ljust(8, b"\0")
        payload = payloads[name]
        raw_offset = 0x200 + index * 0x100
        struct.pack_into("<I", image, section + 16, len(payload))
        struct.pack_into("<I", image, section + 20, raw_offset)
        image[raw_offset : raw_offset + len(payload)] = payload
    return bytes(image)


def rehearse_guarded_kernel_rollback(
    loopdev: str, temporary: Path, config: dict
) -> None:
    root = Path("/mnt/gentoo")
    esp_partition = Path("/dev/disk/by-partlabel/GENTOO-ESP")
    require_loop_mapper(loopdev)
    require_loop_partition(esp_partition, loopdev, 1)
    command_line = (
        "rd.luks.name=12345678-1234-1234-1234-123456789abc=gentoo-root "
        "root=/dev/mapper/gentoo-root rootflags=subvol=@ rw"
    )
    (root / "etc/kernel").mkdir(parents=True, exist_ok=True)
    (root / "etc/kernel/cmdline").write_text(command_line, encoding="utf-8")
    esp = root / "efi"
    systemd = esp / "EFI/systemd"
    linux = esp / "EFI/Linux"
    systemd.mkdir(parents=True, exist_ok=True)
    linux.mkdir(parents=True, exist_ok=True)
    entries = esp / "loader/entries"
    entries.mkdir(parents=True, exist_ok=True)
    (esp / "loader/loader.conf").write_text(
        "default gentoo-production\ntimeout 5\n", encoding="utf-8"
    )
    (entries / "gentoo-production.conf").write_text(
        "title Gentoo Workstation (production)\n"
        "efi /EFI/Linux/gentoo-production.efi\n",
        encoding="utf-8",
    )
    known_good = make_test_uki(command_line, b"known-good disposable kernel")
    (systemd / "systemd-bootx64.efi").write_bytes(known_good)
    (linux / "gentoo-fallback.efi").write_bytes(known_good)
    production = linux / "gentoo-production.efi"
    production.write_bytes(b"deliberately invalid updated UKI")

    rescue_config = temporary / "rollback-workstation.json"
    rescue_config.write_text(json.dumps(config), encoding="utf-8")
    shim_dir = temporary / "rescue-command-shims"
    shim_dir.mkdir(exist_ok=True)
    real_lsblk = shutil.which("lsblk")
    if not real_lsblk:
        raise RuntimeError("rollback rehearsal requires lsblk")
    lsblk = shim_dir / "lsblk"
    lsblk.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == --noheadings && \"$2\" == --output && \"$3\" == PKNAME ]]; then\n"
        "  device=$(readlink -f -- \"$4\")\n"
        "  name=${device##*/}\n"
        "  printf '%s\\n' \"${name%p1}\"\n"
        "elif [[ \"$1\" == --nodeps && \"$2\" == --noheadings && \"$3\" == --output && \"$4\" == SERIAL ]]; then\n"
        "  printf '%s\\n' \"$GENTOO_RESCUE_TEST_SERIAL\"\n"
        "else\n"
        f"  exec {real_lsblk!r} \"$@\"\n"
        "fi\n",
        encoding="utf-8",
    )
    lsblk.chmod(0o700)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{shim_dir}:{env['PATH']}",
            "GENTOO_RESCUE_TEST_SERIAL": config["storage"]["system_target"]["serial"],
            "PYTHONPATH": str(ROOT),
        }
    )
    command = [
        sys.executable,
        "-m",
        "installer.cli",
        "--config",
        str(rescue_config),
        "kernel-rollback",
        "--root",
        str(root),
    ]
    result = subprocess.run(command, cwd=ROOT, env=env, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"guarded kernel rollback CLI failed: {result.stderr.strip()}")
    if production.read_bytes() != known_good or '"status": "rolled-back"' not in result.stdout:
        raise RuntimeError("guarded kernel rollback CLI did not restore the valid fallback UKI")
    print("PASS: guarded kernel-rollback CLI replaced the invalid UKI on the disposable VFAT ESP")

    wrong_env = env.copy()
    wrong_env["GENTOO_RESCUE_TEST_SERIAL"] = "GQ-UNAUTHORIZED-DISK"
    refused = subprocess.run(command, cwd=ROOT, env=wrong_env, check=False, text=True, capture_output=True)
    if refused.returncode != 2 or "not on the configured exact system disk" not in refused.stderr:
        raise RuntimeError("guarded kernel rollback CLI did not reject a mismatched disk serial")
    if production.read_bytes() != known_good:
        raise RuntimeError("guarded kernel rollback CLI changed the UKI after identity refusal")
    print("PASS: guarded kernel-rollback CLI refused a mismatched disk serial without writing")

    candidate = temporary / "experimental-candidate.efi"
    candidate.write_bytes(make_test_uki(command_line, b"disposable experimental kernel"))
    staged = subprocess.run(
        [
            sys.executable,
            "-m",
            "installer.cli",
            "--config",
            str(rescue_config),
            "kernel-stage-experimental",
            "--root",
            str(root),
            "--image",
            str(candidate),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    experimental = linux / "gentoo-experimental.efi"
    experimental_entry = entries / "gentoo-experimental.conf"
    if (
        staged.returncode != 0
        or experimental.read_bytes() != candidate.read_bytes()
        or (esp / "loader/loader.conf").read_text(encoding="utf-8")
        != "default gentoo-production\ntimeout 5\n"
        or production.read_bytes() != known_good
        or "efi /EFI/Linux/gentoo-experimental.efi"
        not in experimental_entry.read_text(encoding="utf-8")
    ):
        raise RuntimeError(f"experimental UKI CLI staging failed or changed production: {staged.stderr.strip()}")
    print("PASS: experimental UKI staged on the disposable VFAT ESP without changing production default")
    repeated = subprocess.run(
        [
            sys.executable,
            "-m",
            "installer.cli",
            "--config",
            str(rescue_config),
            "kernel-stage-experimental",
            "--root",
            str(root),
            "--image",
            str(candidate),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    if repeated.returncode != 0 or production.read_bytes() != known_good:
        raise RuntimeError("repeating experimental staging failed or changed production")
    print("PASS: repeating experimental UKI staging is idempotent")


def rehearse_readonly_rescue(
    loopdev: str, temporary: Path, config: dict, keyfile: Path
) -> None:
    marker = Path("/mnt/gentoo/recovery-marker.txt")
    marker.write_text("disposable rescue fixture\n", encoding="utf-8")
    rescue_config = temporary / "rescue-workstation.json"
    rescue_config.write_text(json.dumps(config), encoding="utf-8")
    shim_dir = temporary / "rescue-command-shims"
    shim_dir.mkdir(exist_ok=True)

    real_lsblk = shutil.which("lsblk")
    real_cryptsetup = shutil.which("cryptsetup")
    if not real_lsblk or not real_cryptsetup:
        raise RuntimeError("rescue rehearsal requires lsblk and cryptsetup")
    (shim_dir / "lsblk").write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == -no && \"$2\" == PKNAME ]]; then\n"
        "  device=$(readlink -f -- \"$3\")\n"
        "  name=${device##*/}\n"
        "  printf '%s\\n' \"${name%p2}\"\n"
        "elif [[ \"$1\" == -dn && \"$2\" == -o && \"$3\" == MODEL ]]; then\n"
        "  printf '%s\\n' \"$GENTOO_RESCUE_TEST_MODEL\"\n"
        "elif [[ \"$1\" == -dn && \"$2\" == -o && \"$3\" == SERIAL ]]; then\n"
        "  printf '%s\\n' \"$GENTOO_RESCUE_TEST_SERIAL\"\n"
        "else\n"
        f"  exec {real_lsblk!r} \"$@\"\n"
        "fi\n",
        encoding="utf-8",
    )
    (shim_dir / "cryptsetup").write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == open ]]; then\n"
        "  shift\n"
        f"  exec {real_cryptsetup!r} open --key-file \"$GENTOO_RESCUE_TEST_KEY\" \"$@\"\n"
        "fi\n"
        f"exec {real_cryptsetup!r} \"$@\"\n",
        encoding="utf-8",
    )
    for shim in shim_dir.iterdir():
        shim.chmod(0o700)

    cleanup_mounts(loopdev)
    require_loop_mapper(loopdev)
    run(["cryptsetup", "close", "gentoo-root"])
    rescue_env = os.environ.copy()
    rescue_env.update(
        {
            "PATH": f"{shim_dir}:{rescue_env['PATH']}",
            "GENTOO_WORKSTATION_CONFIG": str(rescue_config),
            "GENTOO_RESCUE_TEST_KEY": str(keyfile),
            "GENTOO_RESCUE_TEST_MODEL": config["storage"]["system_target"]["model"],
            "GENTOO_RESCUE_TEST_SERIAL": config["storage"]["system_target"]["serial"],
        }
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "rescue.sh")],
        cwd=ROOT,
        env=rescue_env,
        check=True,
        text=True,
        capture_output=True,
    )
    if "mounted read-only" not in result.stdout:
        raise RuntimeError("rescue script did not report a read-only recovery mount")
    options = run(
        ["findmnt", "--noheadings", "--output", "OPTIONS", "--target", "/mnt/gentoo-rescue"],
        capture=True,
    ).stdout.strip().split(",")
    source = run(
        ["findmnt", "--noheadings", "--output", "SOURCE", "--target", "/mnt/gentoo-rescue"],
        capture=True,
    ).stdout.strip().split("[", 1)[0]
    if "ro" not in options or os.path.realpath(source) != os.path.realpath(ROOT_MAPPER):
        raise RuntimeError("rescue script did not mount the disposable encrypted root read-only")
    restored = Path("/mnt/gentoo-rescue/recovery-marker.txt").read_text(encoding="utf-8")
    if restored != "disposable rescue fixture\n":
        raise RuntimeError("rescue mount did not expose the expected recovery fixture")
    print("PASS: rescue script unlocked the disposable root read-only and retrieved its fixture")
    run(["umount", "/mnt/gentoo-rescue"])
    require_loop_mapper(loopdev)
    run(["cryptsetup", "close", "gentoo-root"])
    wrong_identity_env = rescue_env.copy()
    wrong_identity_env["GENTOO_RESCUE_TEST_SERIAL"] = "GQ-UNAUTHORIZED-DISK"
    refused = subprocess.run(
        ["bash", str(ROOT / "scripts" / "rescue.sh")],
        cwd=ROOT,
        env=wrong_identity_env,
        check=False,
        text=True,
        capture_output=True,
    )
    if refused.returncode == 0 or "identity mismatch; refusing" not in refused.stderr:
        raise RuntimeError("rescue script did not refuse a mismatched target disk identity")
    status = subprocess.run(
        [real_cryptsetup, "status", "gentoo-root"],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode == 0:
        raise RuntimeError("rescue script opened a mapping after refusing the target identity")
    print("PASS: rescue script refused a mismatched disk identity without opening a mapping")


def cleanup_mounts(loopdev: str) -> None:
    for path in MOUNTPOINTS:
        probe = subprocess.run(["mountpoint", "--quiet", str(path)], check=False)
        if probe.returncode == 0:
            source = run(
                ["findmnt", "--noheadings", "--output", "SOURCE", "--target", str(path)],
                capture=True,
            ).stdout.strip().split("[", 1)[0]
            expected = (
                PARTLABELS[Path("/dev/disk/by-partlabel/GENTOO-ESP")]
                if path == Path("/mnt/gentoo/efi")
                else None
            )
            if expected is not None:
                require_loop_partition(Path(source), loopdev, expected)
            else:
                require_loop_mapper(loopdev)
                if os.path.realpath(source) != os.path.realpath(ROOT_MAPPER):
                    raise RuntimeError(f"refusing to unmount unrelated source {source} at {path}")
            subprocess.run(["umount", str(path)], check=True)


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("run this test as root on Linux")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("run this test from Linux")
    test_id = uuid.uuid4().hex[:12]
    model = "Gentoo Disposable Loop Integration Disk"
    serial = f"GQ-STORAGE-{test_id}"
    by_id = Path(f"/dev/disk/by-id/gentoo-storage-test-{test_id}")
    config = json.loads((ROOT / "config" / "workstation.yaml").read_text(encoding="utf-8"))
    config["storage"]["system_target"]["model"] = model
    config["storage"]["system_target"]["serial"] = serial
    config["storage"]["data_disk"]["serial"] = f"GQ-DATA-{test_id}"

    with tempfile.TemporaryDirectory(prefix="gentoo-storage-loop-") as temporary:
        temporary_path = Path(temporary)
        image = temporary_path / "target.img"
        state_dir = temporary_path / "state"
        state_dir.mkdir()
        keyfile = temporary_path / "test-luks-key"
        keyfile.write_bytes(secrets.token_bytes(32))
        keyfile.chmod(0o600)
        loopdev: str | None = None
        by_id_created = False
        try:
            ensure_unclaimed_paths(by_id)
            run(["truncate", "--size", str(8 * 1024**3), str(image)])
            loopdev = run(
                ["losetup", "--find", "--show", "--partscan", str(image)], capture=True
            ).stdout.strip()
            if not loopdev.startswith("/dev/loop"):
                raise RuntimeError(f"losetup returned an unexpected target: {loopdev}")
            backing_file = run(
                ["losetup", "--noheadings", "--output", "BACK-FILE", loopdev], capture=True
            ).stdout.strip()
            if os.path.realpath(backing_file) != os.path.realpath(image):
                raise RuntimeError("loop device does not map to the newly created temporary image")
            by_id.symlink_to(loopdev)
            by_id_created = True

            initial = block_report(loopdev, str(by_id), config)
            plan = render_storage_plan(initial, config, str(by_id))
            authorization = create_authorization_record(
                plan, plan["sha256"], plan["target"]["serial"]
            )

            def current_report(_: dict) -> dict:
                report = block_report(loopdev, str(by_id), config)
                if os.environ.get("GENTOO_STORAGE_LOOP_DEBUG") == "1":
                    disk = report["block_devices"][0]
                    print(
                        "Observed loop state:",
                        json.dumps(
                            {
                                "pttype": disk["pttype"],
                                "children": disk["children"],
                                "mountpoints": disk["mountpoints"],
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    for partition in (1, 2):
                        device = f"{loopdev}p{partition}"
                        result = subprocess.run(
                            ["blkid", "--probe", "--output", "export", device],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        if result.stdout:
                            print(f"blkid {device}: {result.stdout.strip()}", flush=True)
                return report

            result = apply_storage_plan(
                plan,
                authorization,
                config,
                initial,
                state_dir,
                confirmed_sha256=plan["sha256"],
                confirmed_serial=serial,
                erasure_phrase="ERASE-SYSTEM-DISK",
                backup_verified=True,
                recovery_media_verified=True,
                runner=lambda argv, **kwargs: run_target_command(
                    argv, loopdev=loopdev, by_id=by_id, keyfile=keyfile
                ),
                report_provider=current_report,
            )
            if result["status"] != "complete":
                raise RuntimeError(f"storage stage returned {result['status']}")
            verify_completed_stage(loopdev, by_id, config)
            print(f"PASS: checkpoint state and event log persisted in {state_dir}")
            rehearse_guarded_kernel_rollback(loopdev, temporary_path, config)
            rehearse_readonly_rescue(loopdev, temporary_path, config, keyfile)
            return 0
        finally:
            if loopdev is not None:
                cleanup_mounts(loopdev)
                status = subprocess.run(
                    ["cryptsetup", "status", "gentoo-root"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if status.returncode == 0:
                    require_loop_mapper(loopdev)
                    run(["cryptsetup", "close", "gentoo-root"])
                if by_id_created and by_id.is_symlink() and os.path.realpath(by_id) == loopdev:
                    by_id.unlink()
                for alias, partition in (
                    (Path("/dev/disk/by-partlabel/GENTOO-ESP"), f"{loopdev}p1"),
                    (Path("/dev/disk/by-partlabel/GENTOO-CRYPTROOT"), f"{loopdev}p2"),
                ):
                    if alias.is_symlink() and os.path.realpath(alias) == partition:
                        alias.unlink()
                backing = subprocess.run(
                    ["losetup", "--noheadings", "--output", "BACK-FILE", loopdev],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if backing.returncode == 0 and os.path.realpath(backing.stdout.strip()) == os.path.realpath(image):
                    run(["losetup", "--detach", loopdev])
                for root in (Path("/mnt/gentoo-top"), Path("/mnt/gentoo")):
                    if root.is_dir() and not root.is_symlink():
                        root.rmdir()
            if keyfile.exists():
                keyfile.write_bytes(b"\0" * keyfile.stat().st_size)
                keyfile.unlink()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print(f"storage stage loop rehearsal failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
