"""Command-line entry point for the Gentoo workstation installer."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from installer.authorization.plan import create_authorization_record
from installer.discovery.host import inspect_host
from installer.planning.storage import plan_hash_matches, render_storage_plan, validate_storage_plan
from installer.stages.storage import apply_storage_plan, ensure_state_location_off_target
from installer.stages.stage3 import extract_verified_stage3, verify_root_mapping, verify_stage3
from installer.stages.base import configure_base_system
from installer.provisioning.packages import (
    PACKAGE_SETS,
    recover_failed_package_checkpoint,
    run_package_stage,
)
from installer.stages.user import setup_user
from installer.stages.chroot import mounted_chroot


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "workstation.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    # JSON is a strict subset of YAML and keeps read-only preflight usable on
    # the minimal live image without installing a third-party parser first.
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_mounted_kernel_target(root: Path, config: dict) -> None:
    if not os.path.ismount(root / "efi"):
        raise RuntimeError("target EFI filesystem must be mounted at <root>/efi")
    root_mount = subprocess.run(
        [
            "findmnt", "--evaluate", "--mountpoint", str(root), "--noheadings",
            "--output", "SOURCE,FSTYPE",
        ],
        check=True, capture_output=True, text=True,
    ).stdout.strip().split()
    if root_mount != ["/dev/mapper/gentoo-root[/@]", "btrfs"]:
        raise RuntimeError("target root must be Btrfs subvolume @ on gentoo-root")
    mounted = subprocess.run(
        [
            "findmnt", "--evaluate", "--mountpoint", str(root / "efi"), "--noheadings",
            "--output", "SOURCE,FSTYPE",
        ],
        check=True, capture_output=True, text=True,
    ).stdout.strip().split()
    if len(mounted) != 2 or mounted[1] != "vfat":
        raise RuntimeError("target ESP mount must be a single VFAT filesystem")
    expected_esp = subprocess.run(
        ["readlink", "-f", "/dev/disk/by-partlabel/GENTOO-ESP"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    mounted_esp = subprocess.run(
        ["readlink", "-f", mounted[0]], check=True, capture_output=True, text=True
    ).stdout.strip()
    if not expected_esp or mounted_esp != expected_esp:
        raise RuntimeError("mounted EFI filesystem is not the GENTOO-ESP partition")
    configured_serial = config["storage"]["system_target"].get("serial")
    if not isinstance(configured_serial, str) or not configured_serial.strip():
        raise RuntimeError("configured exact system-disk serial is missing")
    expected_serial = configured_serial.strip().casefold()
    parent = subprocess.run(
        ["lsblk", "--noheadings", "--output", "PKNAME", mounted[0]],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if not parent:
        raise RuntimeError("cannot identify the physical disk containing GENTOO-ESP")
    actual_serial = subprocess.run(
        ["lsblk", "--nodeps", "--noheadings", "--output", "SERIAL", f"/dev/{parent}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().casefold()
    if not expected_serial or actual_serial != expected_serial:
        raise RuntimeError("GENTOO-ESP is not on the configured exact system disk")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gentoo-installer")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="workstation hardware and storage config (default: config/workstation.yaml)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="read-only live hardware and storage inventory")
    plan_parser = commands.add_parser("plan", help="render a read-only exact-disk storage plan")
    plan_parser.add_argument("--by-id", required=True, help="verified whole-disk by-id path")
    validate_parser = commands.add_parser("validate", help="revalidate a saved storage plan")
    validate_parser.add_argument("--plan", required=True, type=Path)
    validate_parser.add_argument("--backup-verified", action="store_true")
    validate_parser.add_argument("--recovery-media-verified", action="store_true")
    authorize_parser = commands.add_parser(
        "authorize", help="record explicit authorization for one reviewed plan"
    )
    authorize_parser.add_argument("--plan", required=True, type=Path)
    authorize_parser.add_argument("--confirm-plan-hash", required=True)
    authorize_parser.add_argument("--confirm-serial", required=True)
    authorize_parser.add_argument("--backup-verified", action="store_true")
    authorize_parser.add_argument("--recovery-media-verified", action="store_true")
    for command_name in ("install", "resume"):
        stage_parser = commands.add_parser(command_name)
        stages = stage_parser.add_subparsers(dest="stage", required=True)
        storage_parser = stages.add_parser("storage")
        storage_parser.add_argument("--plan", required=True, type=Path)
        storage_parser.add_argument("--authorization", required=True, type=Path)
        storage_parser.add_argument("--confirm-plan-hash", required=True)
        storage_parser.add_argument("--confirm-serial", required=True)
        storage_parser.add_argument("--confirm-erasure", required=True)
        storage_parser.add_argument("--state-dir", required=True, type=Path)
        storage_parser.add_argument("--backup-verified", action="store_true")
        storage_parser.add_argument("--recovery-media-verified", action="store_true")
        stage3_parser = stages.add_parser("stage3")
        stage3_parser.add_argument("--storage-plan", required=True, type=Path)
        stage3_parser.add_argument("--state-dir", required=True, type=Path)
        stage3_parser.add_argument("--archive", type=Path)
        stage3_parser.add_argument("--digests", type=Path)
        stage3_parser.add_argument("--signature", type=Path)
        stage3_parser.add_argument(
            "--keyring", type=Path, default=Path("/usr/share/openpgp-keys/gentoo-release.asc")
        )
        packages_parser = stages.add_parser("packages")
        packages_parser.add_argument("--set", dest="package_set", required=True, choices=PACKAGE_SETS)
        packages_parser.add_argument("--storage-plan", required=True, type=Path)
        packages_parser.add_argument("--state-dir", required=True, type=Path)
        packages_parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="approve Portage package operations for scripted disposable rehearsals",
        )
        user_parser = stages.add_parser("user")
        user_parser.add_argument("--username", required=True)
        user_parser.add_argument("--storage-plan", required=True, type=Path)
        user_parser.add_argument("--state-dir", required=True, type=Path)
    stage3_parser = commands.add_parser(
        "verify-stage3", help="verify the pinned Stage 3 signatures and SHA512"
    )
    stage3_parser.add_argument("--archive", type=Path)
    stage3_parser.add_argument("--digests", type=Path)
    stage3_parser.add_argument("--signature", type=Path)
    stage3_parser.add_argument(
        "--keyring", type=Path, default=Path("/usr/share/openpgp-keys/gentoo-release.asc")
    )
    configure_parser = commands.add_parser(
        "configure", help="configure Portage, encrypted-root boot, locale, and hostname"
    )
    configure_parser.add_argument("--storage-plan", required=True, type=Path)
    configure_parser.add_argument("--state-dir", required=True, type=Path)
    configure_parser.add_argument("--timezone", default="America/New_York")
    configure_parser.add_argument("--locale", default="en_US.UTF-8")
    configure_parser.add_argument("--hostname", default="gentoo-workstation")
    recover_parser = commands.add_parser(
        "recover-package",
        help="reopen a reviewed package checkpoint after an unavailable-atom resolution failure",
    )
    recover_parser.add_argument("--set", dest="package_set", required=True, choices=PACKAGE_SETS)
    recover_parser.add_argument("--storage-plan", required=True, type=Path)
    recover_parser.add_argument("--state-dir", required=True, type=Path)
    recover_parser.add_argument("--command-index", required=True, type=int)
    recover_parser.add_argument("--confirm-log-sha256", required=True)
    recover_parser.add_argument("--non-interactive", action="store_true")
    recover_parser.add_argument(
        "--repair-known-kernel-postinst",
        action="store_true",
        help="repair only the recognized dracut Btrfs post-install failure before reopening its package checkpoint",
    )
    recover_parser.add_argument(
        "--repair-known-desktop-sysv-hook",
        action="store_true",
        help="repair the recognized missing update-rc.d systemd enable hook before reopening the desktop checkpoint",
    )
    rollback_parser = commands.add_parser(
        "kernel-rollback",
        help="restore a validated previous production UKI from a mounted target ESP",
    )
    rollback_parser.add_argument(
        "--root", required=True, type=Path,
        help="mounted Gentoo root (use / for the running installation or its rescue mount)",
    )
    experimental_parser = commands.add_parser(
        "kernel-stage-experimental",
        help="stage a validated experimental UKI without changing the production default",
    )
    experimental_parser.add_argument("--root", required=True, type=Path)
    experimental_parser.add_argument(
        "--image", required=True, type=Path,
        help="externally built UKI carrying the configured encrypted-root command line",
    )
    args = parser.parse_args(argv)

    if args.command in {"kernel-rollback", "kernel-stage-experimental"}:
        try:
            from installer.provisioning.packages import (
                rollback_production_uki,
                stage_experimental_uki,
            )

            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("kernel management requires root to update the mounted EFI partition")
            if platform.system() != "Linux":
                raise RuntimeError("kernel management can run only from Gentoo Linux or its recovery environment")
            root = args.root.resolve(strict=True)
            config = load_config(args.config)
            _validate_mounted_kernel_target(root, config)
            if args.command == "kernel-rollback":
                result = rollback_production_uki(root)
                status = "rolled-back"
                result_key = "production_uki"
            else:
                kernel_config = load_config(ROOT / "config" / "kernel.yaml")
                result = stage_experimental_uki(
                    root, args.image, kernel_config["experimental_entry"]
                )
                status = "staged"
                result_key = "experimental_uki"
        except (OSError, RuntimeError, subprocess.SubprocessError, KeyError, ValueError) as exc:
            print(f"{args.command} refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"status": status, result_key: result}))
        return 0

    if args.command == "inspect":
        try:
            report = inspect_host(load_config(args.config))
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            print(f"inspection blocked: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["target"]["status"] != "identified":
            print(
                f"target identification: {report['target']['status']} "
                f"({report['target']['match_count']} exact matches)",
                file=sys.stderr,
            )
            return 2
        return 0
    if args.command in {"plan", "validate", "authorize", "install", "resume", "verify-stage3", "configure", "recover-package"}:
        try:
            config = load_config(args.config)
            if args.command == "plan":
                report = inspect_host(config)
                plan = render_storage_plan(report, config, args.by_id)
                print(json.dumps(plan, indent=2, sort_keys=True))
                return 0

            if args.command == "verify-stage3":
                stage3 = config["stage3"]
                archive = args.archive or (ROOT / stage3["filename"])
                digests = args.digests or archive.with_name(archive.name + ".DIGESTS")
                signature = args.signature or archive.with_name(archive.name + ".asc")
                result = verify_stage3(archive, digests, signature, args.keyring)
                if result["sha512"] != stage3["sha512"]:
                    raise ValueError("verified archive differs from the pinned workstation Stage 3")
                print(json.dumps(result, indent=2))
                return 0

            if args.command == "configure":
                storage_plan = json.loads(args.storage_plan.read_text(encoding="utf-8"))
                package_config = json.loads(
                    (ROOT / "config" / "packages.yaml").read_text(encoding="utf-8")
                )
                kernel_config = json.loads(
                    (ROOT / "config" / "kernel.yaml").read_text(encoding="utf-8")
                )
                report = inspect_host(config)
                with mounted_chroot():
                    result = configure_base_system(
                        storage_plan,
                        args.state_dir,
                        config,
                        package_config,
                        kernel_config,
                        timezone=args.timezone,
                        locale=args.locale,
                        hostname=args.hostname,
                        report=report,
                    )
                print(json.dumps(result, indent=2))
                return 0

            if args.command == "recover-package":
                storage_plan = json.loads(args.storage_plan.read_text(encoding="utf-8"))
                package_config = json.loads(
                    (ROOT / "config" / "packages.yaml").read_text(encoding="utf-8")
                )
                expected = config["storage"]["system_target"]
                if (
                    not plan_hash_matches(storage_plan)
                    or storage_plan.get("target", {}).get("serial") != expected["serial"]
                ):
                    raise ValueError("storage plan does not identify the configured exact target")
                state_dir = args.state_dir.resolve(strict=True)
                ensure_state_location_off_target(
                    state_dir,
                    storage_plan["target"]["by_id"],
                    (expected["serial"], config["storage"]["data_disk"]["serial"]),
                )
                kernel_repair = None
                desktop_repair = None
                if args.repair_known_kernel_postinst:
                    if args.package_set != "base" or args.command_index != 1:
                        raise ValueError("kernel post-install recovery is limited to base package command 1")

                    def repair_kernel_postinst() -> str:
                        target_root = Path("/mnt/gentoo")
                        verify_root_mapping(storage_plan["target"]["by_id"])
                        installed = sorted(
                            path.name
                            for path in (target_root / "var/db/pkg/sys-kernel").glob(
                                "gentoo-kernel-bin-*"
                            )
                            if path.is_dir()
                        )
                        if len(installed) != 1 or not installed[0].startswith("gentoo-kernel-bin-"):
                            raise RuntimeError("expected exactly one installed binary kernel to repair")
                        kernel_atom = "=sys-kernel/gentoo-kernel-bin-" + installed[0].removeprefix(
                            "gentoo-kernel-bin-"
                        )
                        repair_commands = [
                            [
                                "chroot", str(target_root), "emerge", "--ask=n", "--verbose",
                                "sys-fs/btrfs-progs",
                            ],
                            [
                                "chroot", str(target_root), "emerge", "--config", kernel_atom,
                            ],
                        ]
                        outputs = []
                        repair_path = state_dir / "logs" / (
                            "package-recovery-kernel-"
                            + datetime.now().strftime("%Y%m%dT%H%M%S")
                            + ".log"
                        )
                        try:
                            with mounted_chroot():
                                for command in repair_commands:
                                    result = subprocess.run(
                                        command, check=False, capture_output=True, text=True
                                    )
                                    outputs.append(
                                        "$ " + " ".join(command) + "\n"
                                        + (result.stdout or "") + (result.stderr or "")
                                        + f"\n[exit {result.returncode}]\n"
                                    )
                                    if result.returncode:
                                        raise RuntimeError("kernel repair command failed")
                        except (OSError, RuntimeError) as exc:
                            repair_path.write_text("".join(outputs), encoding="utf-8")
                            raise RuntimeError(f"inspect kernel recovery log {repair_path}") from exc
                        return "".join(outputs)

                    kernel_repair = repair_kernel_postinst
                if args.repair_known_desktop_sysv_hook:
                    if args.package_set != "desktop" or args.command_index != 1:
                        raise ValueError("desktop SysV hook recovery is limited to desktop package command 1")

                    def repair_desktop_sysv_hook() -> str:
                        target_root = Path("/mnt/gentoo")
                        verify_root_mapping(storage_plan["target"]["by_id"])
                        systemd_dir = target_root / "etc/systemd/system"
                        wants_dir = systemd_dir / "multi-user.target.wants"
                        for directory in (systemd_dir, wants_dir):
                            if directory.is_symlink():
                                raise RuntimeError(f"refusing symlinked systemd configuration directory: {directory}")
                            directory.mkdir(parents=True, exist_ok=True)
                        links = [
                            (
                                target_root / "usr/lib/systemd/system/NetworkManager.service",
                                wants_dir / "NetworkManager.service",
                            ),
                            (
                                target_root / "usr/lib/systemd/system/sddm.service",
                                systemd_dir / "display-manager.service",
                            ),
                        ]
                        output = []
                        for unit, link in links:
                            if not unit.is_file() or unit.is_symlink():
                                raise RuntimeError(f"expected native systemd unit is missing or unsafe: {unit}")
                            link_target = "/usr/lib/systemd/system/" + unit.name
                            if link.is_symlink():
                                if os.readlink(link) != link_target:
                                    raise RuntimeError(f"refusing to replace conflicting systemd link: {link}")
                            elif link.exists():
                                raise RuntimeError(f"refusing to replace existing systemd path: {link}")
                            else:
                                link.symlink_to(link_target)
                            output.append(f"{link} -> {link_target}\n")
                        return "".join(output)

                    desktop_repair = repair_desktop_sysv_hook
                result = recover_failed_package_checkpoint(
                    args.package_set,
                    package_config,
                    state_dir,
                    args.command_index,
                    args.confirm_log_sha256,
                    storage_plan["sha256"],
                    non_interactive=args.non_interactive,
                    kernel_repair=kernel_repair,
                    desktop_repair=desktop_repair,
                )
                print(json.dumps(result, indent=2))
                return 0

            if args.command in {"install", "resume"}:
                if args.stage == "storage":
                    plan = json.loads(args.plan.read_text(encoding="utf-8"))
                    authorization = json.loads(args.authorization.read_text(encoding="utf-8"))
                    report = inspect_host(config)
                    result = apply_storage_plan(
                        plan,
                        authorization,
                        config,
                        report,
                        args.state_dir,
                        confirmed_sha256=args.confirm_plan_hash,
                        confirmed_serial=args.confirm_serial,
                        erasure_phrase=args.confirm_erasure,
                        backup_verified=args.backup_verified,
                        recovery_media_verified=args.recovery_media_verified,
                    )
                    print(json.dumps(result, indent=2))
                    return 0

                if args.stage == "packages":
                    storage_plan = json.loads(args.storage_plan.read_text(encoding="utf-8"))
                    package_config = json.loads(
                        (ROOT / "config" / "packages.yaml").read_text(encoding="utf-8")
                    )
                    with mounted_chroot():
                        result = run_package_stage(
                            args.package_set,
                            package_config,
                            storage_plan,
                            args.state_dir,
                            config,
                            non_interactive=args.non_interactive,
                        )
                    print(json.dumps(result, indent=2))
                    return 0

                if args.stage == "user":
                    storage_plan = json.loads(args.storage_plan.read_text(encoding="utf-8"))
                    with mounted_chroot():
                        result = setup_user(
                            args.username,
                            storage_plan,
                            args.state_dir,
                            config,
                        )
                    print(json.dumps(result, indent=2))
                    return 0

                plan = json.loads(args.storage_plan.read_text(encoding="utf-8"))
                if not plan_hash_matches(plan):
                    raise ValueError("storage plan content does not match its hash")
                configured_disk = config["storage"]["system_target"]
                if (
                    plan.get("target", {}).get("model") != configured_disk["model"]
                    or plan.get("target", {}).get("serial") != configured_disk["serial"]
                    or not plan.get("target", {}).get("by_id", "").startswith("/dev/disk/by-id/")
                ):
                    raise ValueError("storage plan does not name the configured Samsung system disk")
                state_dir = args.state_dir.resolve(strict=True)
                storage_state = json.loads(
                    (state_dir / "gentoo-storage-state.json").read_text(encoding="utf-8")
                )
                expected_commands = plan["commands_for_review_only"]
                if (
                    storage_state.get("plan_sha256") != plan.get("sha256")
                    or storage_state.get("command_count") != len(expected_commands)
                    or storage_state.get("completed") != list(range(len(expected_commands)))
                    or storage_state.get("started") is not None
                ):
                    raise RuntimeError("the authorized storage stage is not fully checkpointed")
                verify_root_mapping(plan["target"]["by_id"])
                stage3 = config["stage3"]
                archive = args.archive or (ROOT / stage3["filename"])
                digests = args.digests or archive.with_name(archive.name + ".DIGESTS")
                signature = args.signature or archive.with_name(archive.name + ".asc")
                result = extract_verified_stage3(
                    archive,
                    digests,
                    signature,
                    args.keyring,
                    Path("/mnt/gentoo"),
                    state_dir,
                    plan["target"]["by_id"],
                    protected_serials=(
                        configured_disk["serial"],
                        config["storage"]["data_disk"]["serial"],
                    ),
                    expected_sha512=stage3["sha512"],
                )
                print(json.dumps(result, indent=2))
                return 0

            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            report = inspect_host(config)
            validation = validate_storage_plan(
                plan,
                report,
                args.backup_verified,
                args.recovery_media_verified,
                config,
            )
            if not validation["valid"]:
                print(json.dumps(validation, indent=2), file=sys.stderr)
                return 2
            if args.command == "validate":
                print(json.dumps(validation, indent=2))
                return 0
            approval = create_authorization_record(
                plan, args.confirm_plan_hash, args.confirm_serial
            )
            print(json.dumps(approval, indent=2, sort_keys=True))
            return 0
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            print(f"{args.command} blocked: {exc}", file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
