# Second point-in-time package progress snapshot

Captured 2026-10-15 23:40 UTC from the running disposable QEMU installation.
The VM remained running during and after snapshot creation; no physical disk
was attached.

## Copy and validation

QEMU HMP `drive_backup` copied the target and state devices to independent
qcow2 files. `info block-jobs` reported no active jobs after each copy. Both
passed `qemu-img check` with no errors. SHA-256:

```text
2b800c12fd2d52ea939e94d2fc6f0ef5022f0e27eea0f13ebbdfb186b812dbdf  target-observe-20261015T2340Z.qcow2
23069793714e804bb8cb15770e69860d27f0fd9ac98d8e9e518fd9abffc1169e  state-observe-20261015T2340Z.qcow2
```

Copies are on the WSL builder under
`/root/gentoo-qemu-rehearsal/livegui-install/`; they are not committed.

## Read-only extraction

The target copy was attached to `/dev/nbd5` read-only. The LUKS2 partition was
opened read-only; Btrfs subvolumes `@` and `@log` were mounted read-only. The
state copy is a whole-device ext4 image, attached to `/dev/nbd6` and mounted
read-only with `noload`. The emerge log and package state were copied into
this directory. Both NBD devices, mounts, and the temporary normalized key
copy were removed afterwards.

The emerge log tail at its latest entry reads:

```text
=== (172 of 363) Post-Build Cleaning (app-crypt/rhash-1.4.6-r1::...)
::: completed emerge (172 of 363) app-crypt/rhash-1.4.6-r1 to /
>>> emerge (173 of 363) sys-libs/binutils-libs-2.47 to /
=== (173 of 363) Cleaning (...)
=== (173 of 363) Compiling/Merging (...)
```

The latest package is still compiling/merging in this snapshot. The state
checkpoint remains `complete: false`, `completed: []`, and `started: 0`. Its
event journal contains only the `@world` command start event. The latest
snapshot proves package progress, not completion of the base package stage.

At 23:41 UTC the original QEMU process was still running (PID 120557, elapsed
1:06:18, 109% CPU), and QEMU reported target `wr_bytes=5782897664`, above the
snapshot-time counter. The live forwarded SSH query still does not expose the
expected Gentoo guest environment.

## Reproduction

Use QEMU HMP `drive_backup target <new-target.qcow2> qcow2` and
`drive_backup state <new-state.qcow2> qcow2`, wait for `info block-jobs` to
report no active jobs, and run `qemu-img check` on both. Attach the target
copy with `qemu-nbd --read-only`, unlock LUKS2 with a read-only mapping, and
mount `@` and `@log` read-only to retrieve `/var/log/emerge.log`. Attach the
state copy read-only and mount its ext4 filesystem with `ro,noload` to read
the package checkpoint. Never mount the inspection copies writable.
