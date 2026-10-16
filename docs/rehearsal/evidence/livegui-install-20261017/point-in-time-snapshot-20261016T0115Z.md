# Point-in-time snapshot: 2026-10-16 01:15 UTC

- The QEMU rehearsal remains running against disposable qcow2 target/state
  disks. No physical disk is attached.
- `target-observe-20261016T0115Z.qcow2` passed `qemu-img check` with no errors.
- The target `@log` subvolume showed the base `@world` merge at package 251
  (`media-libs/mesa-26.1.8`). Its multilib build log shows the `-m32` ABI
  advancing from Ninja step 181/1704 at 01:13 UTC to 436/1704 at 01:15 UTC.
  This is actual 32-bit Mesa compilation evidence, not a completed package.
- The LUKS mapping and Btrfs mount were read-only; `rescue=nologreplay` avoids
  replaying pending tree-log entries. Temporary key, mapping, mount, and NBD
  device were cleaned up after inspection.
- Kernel install, remaining package sets, installed-system reboot, encrypted
  unlock, systemd startup, and user login remain pending in this clean retry.
