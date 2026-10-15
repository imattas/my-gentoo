# SPIR-V tools ABI transition snapshot

Captured from the running disposable QEMU installation at approximately
2026-10-15 23:55 UTC. The VM and original target remained running.

## Snapshot integrity

QEMU HMP copied the target with:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261015T2355Z.qcow2 qcow2
```

`qemu-img check` reported no errors. The image remains on the WSL builder,
outside Git.

## Portage/build log state

The emerge log still records package 173 (`sys-libs/binutils-libs`) complete
and package 174 (`dev-util/spirv-tools-1.4.357.0`) compiling/merging. The
23:52 UTC build-log copy ended at Ninja `[319/380]` with `build-abi_x86_32`
and `-m32`. In this 23:55 UTC copy, the build log's last line is Ninja
`[87/380]` with `build-abi_x86_64`. This indicates a transition between ABI
build directories; it is not a separate Portage completion event for the
32-bit build or for package 174.

The 23:55 build log is 476,372 bytes with SHA-256
`BD5983509FAB6C62346A50A25FE39E5071833DE1CE400E5E5FA17544176A0B5F`. A scan
for `fatal error`, `error:`, `failed`, `killed`, and `terminated` found no
matches. The copied emerge log is 104,480 bytes with SHA-256
`2F9DFC623887807F2FE161CD0734E769B338280F28BB4F66EE4DBB447F86D96B`.

The latest package checkpoint snapshot (23:40 UTC) remains incomplete; this
target-only snapshot does not refresh it. At 23:57 UTC QEMU PID 120557 was
still running (elapsed 1:22:40, about 110% CPU). No installed-system boot is
claimed.

## Reproduction

Create a point-in-time target copy with the HMP command above and verify it
with `qemu-img check`. Attach it read-only with `qemu-nbd`, open its LUKS2
partition read-only, and mount Btrfs subvolumes `@` and `@log` read-only. Read
`/var/log/emerge.log` and
`/var/tmp/portage/dev-util/spirv-tools-1.4.357.0/temp/build.log`; inspect the
last Ninja path/step and scan the error markers above. Disconnect NBD and
close the mounts and mapper after inspection.
