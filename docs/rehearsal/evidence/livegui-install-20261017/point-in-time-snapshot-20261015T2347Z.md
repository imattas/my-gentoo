# SPIR-V tools build snapshot

Captured from the running disposable QEMU VM at approximately 2026-10-15
23:47 UTC. The VM was not stopped or reset; only a QEMU point-in-time target
copy was created.

## Snapshot integrity

The copy was created with HMP:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261015T2347Z.qcow2 qcow2
```

QEMU reported `No active jobs`, and `qemu-img check` reported no errors. The
snapshot resides on the WSL builder outside this repository.

## Portage evidence

The copied Gentoo emerge log records:

```text
::: completed emerge (173 of 363) sys-libs/binutils-libs-2.47 to /
>>> emerge (174 of 363) dev-util/spirv-tools-1.4.357.0 to /
=== (174 of 363) Compiling/Merging (...)
```

The corresponding copied Portage build log is
`spirv-tools-build-log-snapshot-20261015T2347Z.log` (195,857 bytes). Its last
recorded Ninja step is `[194/380]`, compiling a SPIR-V optimizer source file
with `-m32`. A targeted scan for `fatal error`, `error:`, `failed`, `killed`,
and `terminated` markers returned no matches. This is a build-in-progress
snapshot, not proof that package 174 or the base merge completed.

At 23:47 UTC QEMU PID 120557 was still running (elapsed 1:12:26, about 108%
CPU), and the target's block statistics showed 5,822,305,280 bytes written.
The checkpoint from the prior 23:40 UTC state snapshot remains incomplete;
this target-only snapshot does not update that checkpoint evidence.

## Reproduction

Create a new point-in-time target copy with the HMP command above, wait for
`info block-jobs` to report no active jobs, and run `qemu-img check`. Attach
the copy using `qemu-nbd --read-only`, open the LUKS2 partition read-only,
and mount Btrfs `@` and `@log` subvolumes read-only. Copy
`/var/log/emerge.log` and
`/var/tmp/portage/dev-util/spirv-tools-1.4.357.0/temp/build.log`. Inspect the
log tail and search for the error markers listed above. Disconnect NBD and
close all mounts and mappings afterwards.
