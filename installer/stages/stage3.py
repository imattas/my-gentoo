"""Verify Gentoo Stage 3 artifacts before they can be extracted."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable

from installer.stages.storage import _append_event, _atomic_json, ensure_state_location_off_target

GENTOO_ROOT = Path("/mnt/gentoo")


def extract_sha512(signed_text: str, filename: str) -> str:
    """Read a SHA512 entry for exactly filename from signed Gentoo metadata."""
    signed_body = signed_text.split("-----BEGIN PGP SIGNATURE-----", 1)[0]
    entries = re.findall(r"(?m)^([0-9a-fA-F]{128})\s+([^\s]+)\s*$", signed_body)
    matches = [digest.lower() for digest, name in entries if name == filename]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one SHA512 entry for {filename}")
    return matches[0]


def verify_root_mapping(
    target_by_id: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
    realpath: Callable[[str], str] = os.path.realpath,
) -> None:
    """Confirm gentoo-root is open from the labeled partition on the target disk."""
    status = runner(
        ["cryptsetup", "status", "gentoo-root"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    source_lines = [
        line.split(":", 1)[1].strip()
        for line in status.splitlines()
        if line.strip().startswith("device:")
    ]
    if len(source_lines) != 1:
        raise RuntimeError("cannot identify the active LUKS mapping's source partition")

    labeled_partition = "/dev/disk/by-partlabel/GENTOO-CRYPTROOT"
    actual_partition = realpath(source_lines[0])
    expected_partition = realpath(labeled_partition)
    if actual_partition != expected_partition:
        raise RuntimeError("gentoo-root mapping does not use the GENTOO-CRYPTROOT partition")
    partlabel = runner(
        ["lsblk", "--list", "--noheadings", "--raw", "--output", "PARTLABEL", labeled_partition],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if partlabel != "GENTOO-CRYPTROOT":
        raise RuntimeError("encrypted-root partition label does not match the install plan")
    ancestry = runner(
        ["lsblk", "--list", "--paths", "--inverse", "--noheadings", "--raw", "--output", "PATH", actual_partition],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if realpath(target_by_id) not in {realpath(path.strip()) for path in ancestry if path.strip()}:
        raise RuntimeError("gentoo-root mapping does not trace to the authorized Samsung disk")


def verify_stage3(
    archive: Path,
    digest_file: Path,
    archive_signature: Path,
    trusted_key_file: Path = Path("/usr/share/openpgp-keys/gentoo-release.asc"),
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, str]:
    """Verify signed Gentoo metadata, detached signature, and archive SHA512."""
    for required in (archive, digest_file, archive_signature, trusted_key_file):
        if not required.is_file():
            raise FileNotFoundError(f"required verification file is missing: {required}")
    with tempfile.TemporaryDirectory(prefix="gentoo-gpg-") as gpg_home:
        runner(["gpg", "--batch", "--homedir", gpg_home, "--import", str(trusted_key_file)], check=True)
        runner(
            [
                "gpg",
                "--batch",
                "--homedir",
                gpg_home,
                "--output",
                "-",
                "--decrypt",
                str(digest_file),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        runner(
            ["gpg", "--batch", "--homedir", gpg_home, "--verify", str(archive_signature), str(archive)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    signed_text = digest_file.read_text(encoding="utf-8", errors="strict")
    expected = extract_sha512(signed_text, archive.name)
    actual_hash = hashlib.sha512()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            actual_hash.update(chunk)
    actual = actual_hash.hexdigest()
    if actual != expected:
        raise ValueError(f"SHA512 mismatch for {archive.name}")
    return {"filename": archive.name, "sha512": actual, "signature_status": "verified"}


def extract_verified_stage3(
    archive: Path,
    digest_file: Path,
    archive_signature: Path,
    trusted_key_file: Path,
    target: Path,
    state_dir: Path,
    target_by_id: str,
    *,
    protected_serials: tuple[str, ...],
    expected_sha512: str | None = None,
    verifier: Callable[..., dict[str, str]] = verify_stage3,
    mount_probe: Callable[[Path], dict[str, str]] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    state_location_check: Callable[[Path, str], None] = ensure_state_location_off_target,
) -> dict[str, str]:
    """Extract only verified Stage 3 data into the exact mounted Btrfs root."""
    if target != GENTOO_ROOT:
        raise ValueError("Stage 3 extraction target must be exactly /mnt/gentoo")
    verification = verifier(archive, digest_file, archive_signature, trusted_key_file)
    if verification.get("signature_status") != "verified" or not verification.get("sha512"):
        raise RuntimeError("Stage 3 verification did not complete")
    if expected_sha512 and verification["sha512"] != expected_sha512:
        raise ValueError("verified Stage 3 hash does not match the pinned workstation artifact")

    target = target.resolve(strict=True)
    state_dir = state_dir.resolve(strict=True)
    state_location_check(state_dir, target_by_id, protected_serials)
    if mount_probe is None:
        completed = subprocess.run(
            [
                "findmnt",
                "--noheadings",
                "--target",
                str(target),
                "--output",
                "TARGET,SOURCE,FSTYPE",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        fields = completed.stdout.strip().split()
        mount = dict(zip(("target", "source", "fstype"), fields, strict=True))
    else:
        mount = mount_probe(target)
    if mount.get("target") != str(target) or mount.get("fstype") != "btrfs":
        raise RuntimeError("/mnt/gentoo is not the exact Btrfs root mount")
    if mount.get("source", "").split("[", 1)[0] != "/dev/mapper/gentoo-root":
        raise RuntimeError("/mnt/gentoo is not mounted from the authorized encrypted root")

    state_path = state_dir / "gentoo-stage3-state.json"
    event_path = state_dir / "gentoo-stage3-events.jsonl"
    if state_path.exists():
        journal = json.loads(state_path.read_text(encoding="utf-8"))
        if journal.get("started"):
            raise RuntimeError("Stage 3 extraction was interrupted; inspect the target before retrying")
        if journal.get("complete"):
            if journal.get("sha512") == verification["sha512"] and journal.get("target") == str(target):
                return {"status": "complete", "sha512": verification["sha512"], "state_file": str(state_path)}
            raise RuntimeError("existing Stage 3 checkpoint does not match the verified archive")
    else:
        journal = {
            "schema_version": 1,
            "target": str(target),
            "sha512": verification["sha512"],
            "started": False,
            "complete": False,
        }

    argv = [
        "tar",
        "--extract",
        "--xz",
        "--file",
        str(archive),
        "--directory",
        str(target),
        "--numeric-owner",
        "--xattrs",
        "--xattrs-include=*",
    ]
    journal["started"] = True
    _atomic_json(state_path, journal)
    _append_event(
        event_path,
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": "stage3-extraction-started",
            "archive": archive.name,
            "sha512": verification["sha512"],
            "target": str(target),
        },
    )
    print("Running: " + " ".join(argv), flush=True)
    try:
        runner(argv, check=True)
    except subprocess.CalledProcessError as exc:
        _append_event(
            event_path,
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": "stage3-extraction-failed",
                "returncode": exc.returncode,
            },
        )
        raise
    if not (target / "etc" / "gentoo-release").is_file() or not (target / "bin" / "bash").exists():
        raise RuntimeError("Stage 3 extraction returned successfully but expected base files are missing")
    journal["started"] = False
    journal["complete"] = True
    _atomic_json(state_path, journal)
    _append_event(
        event_path,
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": "stage3-extraction-completed",
            "sha512": verification["sha512"],
            "target": str(target),
        },
    )
    return {"status": "complete", "sha512": verification["sha512"], "state_file": str(state_path)}
