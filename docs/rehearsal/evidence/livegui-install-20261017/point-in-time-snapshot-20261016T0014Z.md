# Continued base package merge snapshot

Captured 2026-10-16 around 00:14 UTC from the running disposable QEMU
installation. The VM was not reset and no physical drive was attached.

## Target snapshot

The target copy was created with QEMU HMP:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261016T0014Z.qcow2 qcow2
```

The backup job completed, and `qemu-img check` reported no errors. The image
remains on the WSL builder outside Git. It was attached to NBD read-only and
unlocked through a read-only LUKS2 mapping. Btrfs required
`ro,rescue=nologreplay` because a normal read-only mount reported that tree-log
replay was pending. This recovery view omits pending tree-log replay and may
not include uncommitted filesystem changes.

The copied emerge log is
`base-emerge-log-snapshot-20261016T0014Z.log`. It records packages 174
(`dev-util/spirv-tools`) and 175 (`media-libs/opus`) completed; package 188
(`x11-libs/libXrandr`) was merging at the end of the copy. This is package
progress, not base `@world` completion.

## Checkpoint and live VM status

The separate state-device snapshot from around 00:11 UTC passed `qemu-img
check`. Its ext4 filesystem was mounted read-only with `ro,noload`. The copied
package checkpoint remains `complete: false`, `completed: []`, `started: 0`,
and the event journal contains only the `@world` command start event. The
checkpoint therefore does not claim a completed base stage.

At 00:15:35 UTC QEMU PID 120557 remained running (elapsed 1:41:54, 112% CPU).
The original target had `wr_bytes=6038443008`.

## Reproduction

Create a target copy with HMP `drive_backup target <new-image.qcow2> qcow2`,
wait for `info block-jobs` to show no active jobs, and run `qemu-img check`.
Attach the copy with `qemu-nbd --read-only`, open its LUKS2 partition
read-only, then mount Btrfs `@` and `@log` with
`ro,rescue=nologreplay` only when normal `ro` requires pending log replay.
Copy `/var/log/emerge.log`. For the state copy, use read-only NBD and ext4
`ro,noload` to copy the installer checkpoint and event journal. Disconnect
NBD and close the mapper/mounts after inspection; do not write to the copies.
