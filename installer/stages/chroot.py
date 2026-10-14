"""Temporary live-system mounts needed to operate safely inside Stage 3."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
from typing import Any, Iterator
import uuid


@contextmanager
def mounted_chroot(
    root: Path = Path("/mnt/gentoo"),
    *,
    runner: Any = subprocess.run,
    require_fixed_root: bool = True,
    resolver_source: Path = Path("/etc/resolv.conf"),
) -> Iterator[None]:
    """Bind live kernel interfaces and DNS into the target for one operation.

    All mountpoints are checked first. Only mounts made here are removed, in
    reverse order, and a Stage 3 resolver symlink is restored after use.
    """
    root = root.resolve(strict=True)
    if require_fixed_root and root != Path("/mnt/gentoo"):
        raise ValueError("chroot operations are bound to exactly /mnt/gentoo")

    mountpoints = [root / name for name in ("dev", "proc", "sys", "run")]
    resolver = root / "etc" / "resolv.conf"
    if not resolver.parent.is_dir():
        raise RuntimeError("Stage 3 /etc directory is missing")
    for mountpoint in [*mountpoints, resolver]:
        result = runner(["mountpoint", "-q", str(mountpoint)], check=False)
        if result.returncode == 0:
            raise RuntimeError(f"target chroot mountpoint is already mounted: {mountpoint}")

    if not resolver_source.is_file():
        raise RuntimeError("live resolver configuration is unavailable")

    backup: Path | None = None
    created_resolver = False
    if resolver.is_symlink():
        backup = resolver.with_name(f".resolv.conf.installer-{uuid.uuid4().hex}")
        os.replace(resolver, backup)
        resolver.touch()
    elif not resolver.exists():
        resolver.touch()
        created_resolver = True

    mounted: list[Path] = []
    resolver_mounted = False
    try:
        for mountpoint in mountpoints:
            mountpoint.mkdir(parents=True, exist_ok=True)
            runner(["mount", "--rbind", f"/{mountpoint.name}", str(mountpoint)], check=True)
            mounted.append(mountpoint)
            runner(["mount", "--make-rslave", str(mountpoint)], check=True)
        runner(["mount", "--bind", str(resolver_source), str(resolver)], check=True)
        resolver_mounted = True
        yield
    finally:
        cleanup_error: BaseException | None = None
        if resolver_mounted:
            try:
                runner(["umount", str(resolver)], check=True)
            except BaseException as exc:  # preserve cleanup failure after attempting every unmount
                cleanup_error = exc
        for mountpoint in reversed(mounted):
            try:
                runner(["umount", "--recursive", str(mountpoint)], check=True)
            except BaseException as exc:
                cleanup_error = cleanup_error or exc
        if backup is not None:
            resolver.unlink(missing_ok=True)
            os.replace(backup, resolver)
        elif created_resolver:
            resolver.unlink(missing_ok=True)
        if cleanup_error is not None:
            raise cleanup_error
