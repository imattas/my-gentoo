#!/usr/bin/env python3
"""Exercise the destructive storage stage against a new sparse file via loop."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import uuid

from installer.authorization.plan import create_authorization_record
from installer.planning.storage import render_storage_plan
from installer.stages.storage import apply_storage_plan


ROOT = Path(__file__).resolve().parents[2]
MOUNTPOINTS = (
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
