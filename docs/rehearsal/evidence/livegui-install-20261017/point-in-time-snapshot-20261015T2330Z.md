# Point-in-time package progress snapshot

Captured 2026-10-15 23:30 UTC from the running disposable QEMU installation.
The VM was not paused or reset. No physical disk was attached.

## Snapshot method and integrity

QEMU HMP `drive_backup` made independent point-in-time copies of the attached
`target` and `state` devices:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261015.qcow2 qcow2
drive_backup state /root/gentoo-qemu-rehearsal/livegui-install/state-observe-20261015.qcow2 qcow2
```

QEMU reported no active block jobs after the copies completed. Both copies
passed `qemu-img check` with no errors. SHA-256:

```text
8d2efe5b3b8815fdd61105ef847835e00623f2c10cde31a142eb8dd20b8271ea  target-observe-20261015.qcow2
eed3d62b1b78d08d7b1c2d23b92ea69ca805ebe8c4fc3ce4906f0b43686e79cc  state-observe-20261015.qcow2
```

The copies are retained on the WSL builder under
`/root/gentoo-qemu-rehearsal/livegui-install/`; they are not part of the Git
repository.

## Read-only inspection

The target copy was attached to `/dev/nbd5` read-only. Its GPT showed a 2 GiB
VFAT `GENTOO-ESP` partition and a 98 GiB LUKS2 partition. LUKS2 was opened
read-only with the external test key. Btrfs root (`@`) and log (`@log`)
subvolumes were mounted read-only. The detached state copy was attached to
`/dev/nbd6` read-only and mounted ext4 with `ro,noload`. Both NBD devices were
disconnected after the files were copied into this evidence directory. The
temporary normalized key copy was removed.

`base-emerge-log-snapshot.log` ends at:

```text
=== (158 of 363) Compiling/Merging (dev-libs/popt-1.19-r1::...)
=== (158 of 363) Merging (dev-libs/popt-1.19-r1::...)
>>> unmerge success: dev-libs/popt-1.19-r1
```

There is no package 158 post-build completion line in the snapshot. The
state checkpoint has `complete: false`, `completed: []`, and `started: 0`;
the package event journal records command 0 (`@world`) started at
2026-10-15 22:43:35 UTC. This is progress evidence, not a successful base
merge. The current live package position was not read.

At 23:33 UTC the original QEMU process was still running (PID 120557, elapsed
58:23, 108% CPU), QEMU reported no active block jobs, and the original target
had `wr_bytes=5483832320`. The read-only snapshot does not include those later
writes.

## Reproduction outline

With the VM running and the same disposable qcow2 target attached, start HMP
point-in-time copies using the commands above, then wait until
`info block-jobs` reports no active jobs. Check each copy with `qemu-img
check`. Attach the target copy read-only with `qemu-nbd`, unlock its LUKS2
partition read-only, and mount the Btrfs `@` and `@log` subvolumes read-only.
Mount the state copy read-only with ext4 `ro,noload`. Never attach these
inspection copies writable.
