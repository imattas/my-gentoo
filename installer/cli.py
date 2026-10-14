"""Command-line entry point for the Gentoo workstation installer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from installer.authorization.plan import create_authorization_record
from installer.discovery.host import inspect_host
from installer.planning.storage import render_storage_plan, validate_storage_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "workstation.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    # JSON is a strict subset of YAML and keeps read-only preflight usable on
    # the minimal live image without installing a third-party parser first.
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gentoo-installer")
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
    args = parser.parse_args(argv)

    if args.command == "inspect":
        try:
            report = inspect_host(load_config())
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
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
    if args.command in {"plan", "validate", "authorize"}:
        try:
            config = load_config()
            if args.command == "plan":
                report = inspect_host(config)
                plan = render_storage_plan(report, config, args.by_id)
                print(json.dumps(plan, indent=2, sort_keys=True))
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
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"{args.command} blocked: {exc}", file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
