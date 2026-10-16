# Continued SPIR-V tools build snapshot

Captured at approximately 2026-10-16 00:04 UTC from the active disposable
QEMU VM. The VM was left running.

## Copy validation

QEMU HMP created the read-only inspection copy:

```text
drive_backup target /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261016T0004Z.qcow2 qcow2
```

The block job completed and `qemu-img check` reported no errors. The copy is
kept on the WSL builder outside Git.

## Build state

The copied emerge log still records package 173/363 complete and package 174
(`dev-util/spirv-tools-1.4.357.0`) in `Compiling/Merging`. The build log is
`spirv-tools-build-log-snapshot-20261016T0004Z.log` (616,943 bytes, SHA-256
`FDC96D30391BD5721CD1192C8B0DC63E424A10A2E03DE7A70AD197EE612C39C8`). It
shows the x86_64 ABI at Ninja step `[225/380]`, with build log mtime
2026-10-16 00:03:36 UTC. The previous target snapshot showed this ABI at
`[164/380]`; an earlier x86_32 build log reached `[319/380]`. The targeted
scan for `fatal error`, `error:`, `failed`, `killed`, and `terminated` found
no matches. The copied emerge log is 104,480 bytes with SHA-256
`2F9DFC623887807F2FE161CD0734E769B338280F28BB4F66EE4DBB447F86D96B`.

The latest package checkpoint copy (23:40 UTC) remains incomplete. This
target-only copy does not prove package 174 or the base stage completed.
QEMU PID 120557 was still running at 00:04:58 UTC (elapsed 1:30:54, about
110% CPU); the live target showed `wr_bytes=5878166528`.

## Reproduction

Use HMP `drive_backup target <new-image.qcow2> qcow2`, wait for
`info block-jobs` to report no active job, and run `qemu-img check`. Attach
the copy read-only with `qemu-nbd`, unlock LUKS2 with a read-only mapping,
and mount Btrfs subvolumes `@` and `@log` read-only. Copy the emerge and
SPIR-V build logs, record the last Ninja line, and scan the error markers
listed above. Disconnect NBD and close the mapping/mounts afterwards.
