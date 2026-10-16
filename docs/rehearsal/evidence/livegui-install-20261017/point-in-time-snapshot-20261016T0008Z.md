# Portage package completion and checkpoint snapshot

Captured 2026-10-16 00:08 UTC from the live disposable QEMU target, with a
separate state-device copy captured around 00:11 UTC. The VM remained running;
no physical disk was attached.

## Target snapshot and filesystem recovery mode

QEMU HMP created the target copy:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261016T0008Z.qcow2 qcow2
```

The QEMU block job completed and `qemu-img check` found no image errors. The
filesystem copy was opened through read-only NBD and LUKS mappings. A normal
read-only Btrfs mount reported that tree-log replay was required; the copy was
then mounted with `ro,rescue=nologreplay` to avoid replaying anything. This
view therefore excludes pending tree-log replay and may omit the newest
uncommitted filesystem changes.

The resulting `/var/log/emerge.log` copy is
`base-emerge-log-snapshot-20261016T0008Z-rescue.log`. It records:

```text
::: completed emerge (174 of 363) dev-util/spirv-tools-1.4.357.0 to /
::: completed emerge (175 of 363) media-libs/opus-1.5.2 to /
>>> emerge (176 of 363) net-libs/libpsl-0.21.5 to /
=== (176 of 363) Merging (...)
```

This is positive package-level progress evidence. The base emerge command
itself did not complete in this snapshot.

## State checkpoint

QEMU HMP copied the state device to
`/root/gentoo-qemu-rehearsal/livegui-install/state-observe-20261016T0008Z.qcow2`.
The state copy passed `qemu-img check` with no errors. Its ext4 filesystem was
attached read-only and mounted with `ro,noload`. The copied checkpoint
`gentoo-packages-base-snapshot-20261016T0008Z.json` remains:

```json
{
  "complete": false,
  "completed": [],
  "package_set": "base",
  "started": 0
}
```

The event journal contains only the start of `@world` command index 0. The
checkpoint therefore correctly remains incomplete despite package 174 and
175 completion events in Portage's log.

The read-only NBD devices were disconnected after copying the files. No
snapshot was attached writable.

## Reproduction

Create point-in-time `target` and `state` copies using QEMU HMP
`drive_backup`, wait for `info block-jobs` to report no active jobs, and run
`qemu-img check` on each. Attach target read-only with `qemu-nbd`, unlock
LUKS2 read-only, and mount Btrfs `@` and `@log` with
`ro,rescue=nologreplay` if normal `ro` reports pending log replay. Attach the
state image read-only and mount ext4 with `ro,noload`. Never replay filesystem
logs or write to these observation copies.
