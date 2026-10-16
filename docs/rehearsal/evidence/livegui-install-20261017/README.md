# Clean-target LiveGUI rehearsal

This retry uses a fresh, blank 100 GiB qcow2 with observed serial
`GQ-LIVEGUI-INSTALL-2` and a separate 16 GiB state qcow2. The previous
interrupted target was preserved as a separate image and was not attached to
this VM. Only virtual disks are attached; the Gentoo LiveGUI ISO is read-only.

## Completed

- Read-only discovery identified `/dev/vda` as the unique configured target.
- Storage plan hash
  `b98af0618558c362a74eac5a304cb1697966e57a69e34c56845117d44dfea4f4`
  validated with no issues and was authorized for the exact observed serial.
- The installer completed GPT, a 2 GiB ESP mounted with `umask=0077`, LUKS2,
  Btrfs, and the `@`, `@home`, `@snapshots`, and `@log` subvolumes.
- Stage 3 SHA512 and Gentoo release signatures verified; extraction completed.
- The Gentoo repository snapshot signature verified. Configuration completed
  with profile `default/linux/amd64/23.0/desktop/plasma/systemd`.
- The base `@world` set resolved 363 packages. The 00:57 UTC read-only target
  log shows package 245 (`net-libs/nghttp2`) complete and package 246
  (`net-misc/curl`) compiling; GnuTLS and libmicrohttpd also completed. The
  00:11 UTC installer state checkpoint remains incomplete. Vulkan loader and
  SPIR-V Tools metadata enable both x86 ABIs. Btrfs required
  `rescue=nologreplay`; pending tree-log replay may be absent.
- Point-in-time target and state copies passed `qemu-img check`. Their
  filesystems were unlocked/mounted read-only to copy emerge logs and
  installer state; all inspection mounts and NBD connections were removed.
  QEMU was still running afterwards. Its SSH forward identifies Ubuntu 22.04
  with a `microsoft-standard-WSL2` kernel and no `/dev/vda` target, so live
  package position remains unknown. No installed-system boot is claimed.

## Evidence files

- `preflight.json`, `storage-plan.json`, `plan-validation.json`, and
  `storage-authorization.json` â€” exact target discovery and write scope.
- `gentoo-storage-state.json` and `gentoo-storage-events.jsonl` â€” destructive
  storage-stage checkpoints and command results.
- `gentoo-stage3-state.json` and `gentoo-stage3-events.jsonl` â€” verified
  extraction checkpoint.
- `gentoo-base-config-state.json` â€” generated system configuration result.
- `gentoo-packages-base.json` and `gentoo-package-events.jsonl` â€” base package
  checkpoint and command event log.
- `base-emerge-log-snapshot.log`, `gentoo-packages-base-snapshot.json`, and
  `gentoo-package-events-snapshot.jsonl` â€” copied from a read-only target and
  state snapshot; the emerge log reaches package 158/363 and the installer
  checkpoint remains incomplete.
- `base-emerge-log-snapshot-20261015T2336Z.log`,
  `gentoo-packages-base-snapshot-20261015T2336Z.json`, and
  `gentoo-package-events-snapshot-20261015T2336Z.jsonl` â€” later read-only
  snapshot; the emerge log reaches package 173/363.
- `base-emerge-log-snapshot-20261015T2347Z.log` and
  `spirv-tools-build-log-snapshot-20261015T2347Z.log` â€” read-only target
  snapshot showing package 173 complete and the multilib SPIR-V tools build
  underway at Ninja step 194/380.
- `base-emerge-log-snapshot-20261015T2352Z.log` and
  `spirv-tools-build-log-snapshot-20261015T2352Z.log` â€” later read-only target
  snapshot showing the same build advanced to Ninja step 319/380.
- `base-emerge-log-snapshot-20261015T2355Z.log` and
  `spirv-tools-build-log-snapshot-20261015T2355Z.log` â€” the build log now shows
  the x86_64 ABI at Ninja step 87/380.
- `base-emerge-log-snapshot-20261016T0004Z.log` and
  `spirv-tools-build-log-snapshot-20261016T0004Z.log` â€” the x86_64 build
  advanced to Ninja step 225/380.
- `base-emerge-log-snapshot-20261016T0008Z-rescue.log`,
  `gentoo-packages-base-snapshot-20261016T0008Z.json`, and
  `gentoo-package-events-snapshot-20261016T0008Z.jsonl` â€” latest target and
  state snapshots: packages 174 and 175 completed, 176 merging, checkpoint
  incomplete.
- `base-emerge-log-snapshot-20261016T0014Z.log` â€” newer read-only target log;
- `base-progress-current.log` â€” QEMU block counters, active Portage process,
  and Gentoo emerge log tail captured at 23:15 UTC.
- `live-host-observation-20261015T2326Z.md` â€” QEMU state and SSH identity
  mismatch before point-in-time snapshot inspection.
- `point-in-time-snapshot-20261015T2330Z.md` â€” snapshot creation, read-only
  LUKS2/Btrfs inspection, backup checksums, checkpoint state, and commands.
- `point-in-time-snapshot-20261015T2340Z.md` â€” later snapshot integrity and
  package progress evidence.
- `point-in-time-snapshot-20261015T2347Z.md` â€” package 174 compiler progress,
  32-bit build evidence, and filtered error scan.
- `point-in-time-snapshot-20261015T2352Z.md` â€” subsequent build progress
  evidence from the target copy.
- `point-in-time-snapshot-20261015T2355Z.md` â€” ABI-pass transition and
  updated compiler progress.
- `point-in-time-snapshot-20261016T0004Z.md` â€” subsequent x86_64 compiler
  progress.
- `point-in-time-snapshot-20261016T0008Z.md` â€” package completion events,
  checkpoint state, and the read-only tree-log replay limitation.
- `point-in-time-snapshot-20261016T0014Z.md` â€” package progress capture.
- `point-in-time-snapshot-20261016T0019Z.md` â€” Vulkan loader merge completion,
  package 201 progress, and VM liveness observation.
- `point-in-time-snapshot-20261016T0021Z.md` â€” package 209 progress and
  observed 32-bit/64-bit Vulkan loader and SPIR-V Tools ABI metadata.
- `point-in-time-snapshot-20261016T0025Z.md` â€” packages 209–210 completion,
- `point-in-time-snapshot-20261016T0045Z.md` â€” package 239 completion,
- `point-in-time-snapshot-20261016T0057Z.md` â€” package 245 completion,
  package 246 build progress, clean image check, and VM liveness.
  package 240 progress, image integrity, and QEMU liveness.
  package 211 build progress, clean image check, and error scan.
- `qemu-launch-command.txt` â€” the running headless QEMU invocation.

The pre-install target copy was checked with `qemu-img check` and contained no
errors (SHA-256
`3cb0de024967f22d2d27eb875686ba876014d26caf00a696d07696753e9242bd`). The
test-only LUKS key is held in a root-only file outside the
repository; neither it nor the temporary LiveGUI account password is captured
here. No installed-system boot has occurred in this retry yet. Desktop,
gaming, development, virtualization, user setup, encrypted reboot, and first
login remain unverified for this run.
