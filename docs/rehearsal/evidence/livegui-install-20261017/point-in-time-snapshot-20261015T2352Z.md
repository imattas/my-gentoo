# Continuing multilib build snapshot

Captured from the running disposable QEMU installation at approximately
2026-10-15 23:52 UTC. No VM reset or physical disk access occurred.

## Snapshot integrity

QEMU HMP created the target copy:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261015T2352Z.qcow2 qcow2
```

QEMU reported no active block jobs afterwards. `qemu-img check` reported no
errors. The snapshot remains on the WSL builder, outside Git.

## Gentoo build progress

The copied emerge log ends with package 173 complete and package 174
`dev-util/spirv-tools-1.4.357.0` compiling/merging. Its copied Portage build
log is `spirv-tools-build-log-snapshot-20261015T2352Z.log` (332,764 bytes,
SHA-256
`D9A6BBFD356AC4817B4DD18258DEBDEA96AA252FAB889D260EE5D3D20525CB71`). The
last Ninja line is `[319/380]`, with a 32-bit `-m32` C++ compile. A scan for
`fatal error`, `error:`, `failed`, `killed`, and `terminated` found no matches.
The copied emerge log SHA-256 is
`2F9DFC623887807F2FE161CD0734E769B338280F28BB4F66EE4DBB447F86D96B`.

This is still an in-progress package snapshot, not a successful package-stage
result. The latest state-device snapshot (23:40 UTC) shows the package-stage
checkpoint incomplete. It was not recopied at 23:52 UTC.

At 23:50:49 UTC the original QEMU process was still running (PID 120557,
elapsed 1:16:15, approximately 109% CPU); the target had
`wr_bytes=5839959040`. The live SSH endpoint still identifies Ubuntu 22.04
with a `microsoft-standard-WSL2` kernel, so it does not provide the current
Gentoo guest status.

## Reproduction

Create a target copy with the HMP command above, wait for `info block-jobs`
to report no active jobs, and run `qemu-img check`. Attach it read-only with
`qemu-nbd`, open the LUKS2 partition read-only, and mount Btrfs subvolumes `@`
and `@log` read-only. Copy `/var/log/emerge.log` and
`/var/tmp/portage/dev-util/spirv-tools-1.4.357.0/temp/build.log`. Record the
last Ninja step and search for the error markers above. Disconnect NBD and
close the mounts and mapper after inspection.
