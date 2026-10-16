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
- The base `@world` set resolved 363 packages. The 00:08 UTC target log shows
  package 174 (`dev-util/spirv-tools`) and 175 (`media-libs/opus`) completed;
  package 176 (`net-libs/libpsl`) was merging. The same-time state snapshot
  still has `complete: false` and no completed commands. The target's Btrfs
  log subvolume required a read-only `rescue=nologreplay` mount, which omits
  pending tree-log replay; that limitation is recorded with the snapshot.
- Two point-in-time target and state copy pairs passed `qemu-img check`. Their
  filesystems were unlocked/mounted read-only to copy emerge logs and
  installer state; all inspection mounts and NBD connections were removed.
  QEMU was still running afterwards. Its SSH forward identifies Ubuntu 22.04
  with a `microsoft-standard-WSL2` kernel and no `/dev/vda` target, so live
  package position remains unknown. No installed-system boot is claimed.

## Evidence files

- `preflight.json`, `storage-plan.json`, `plan-validation.json`, and
  `storage-authorization.json` — exact target discovery and write scope.
- `gentoo-storage-state.json` and `gentoo-storage-events.jsonl` — destructive
  storage-stage checkpoints and command results.
- `gentoo-stage3-state.json` and `gentoo-stage3-events.jsonl` — verified
  extraction checkpoint.
- `gentoo-base-config-state.json` — generated system configuration result.
- `gentoo-packages-base.json` and `gentoo-package-events.jsonl` — base package
  checkpoint and command event log.
- `base-emerge-log-snapshot.log`, `gentoo-packages-base-snapshot.json`, and
  `gentoo-package-events-snapshot.jsonl` — copied from a read-only target and
  state snapshot; the emerge log reaches package 158/363 and the installer
  checkpoint remains incomplete.
- `base-emerge-log-snapshot-20261015T2336Z.log`,
  `gentoo-packages-base-snapshot-20261015T2336Z.json`, and
  `gentoo-package-events-snapshot-20261015T2336Z.jsonl` — later read-only
  snapshot; the emerge log reaches package 173/363.
- `base-emerge-log-snapshot-20261015T2347Z.log` and
  `spirv-tools-build-log-snapshot-20261015T2347Z.log` — read-only target
  snapshot showing package 173 complete and the multilib SPIR-V tools build
  underway at Ninja step 194/380.
- `base-emerge-log-snapshot-20261015T2352Z.log` and
  `spirv-tools-build-log-snapshot-20261015T2352Z.log` — later read-only target
  snapshot showing the same build advanced to Ninja step 319/380.
- `base-emerge-log-snapshot-20261015T2355Z.log` and
  `spirv-tools-build-log-snapshot-20261015T2355Z.log` — the build log now shows
  the x86_64 ABI at Ninja step 87/380.
- `base-emerge-log-snapshot-20261016T0004Z.log` and
  `spirv-tools-build-log-snapshot-20261016T0004Z.log` — the x86_64 build
  advanced to Ninja step 225/380.
- `base-emerge-log-snapshot-20261016T0008Z-rescue.log`,
  `gentoo-packages-base-snapshot-20261016T0008Z.json`, and
  `gentoo-package-events-snapshot-20261016T0008Z.jsonl` — latest target and
  state snapshots: packages 174 and 175 completed, 176 merging, checkpoint
  incomplete.
- `base-progress-current.log` — QEMU block counters, active Portage process,
  and Gentoo emerge log tail captured at 23:15 UTC.
- `live-host-observation-20261015T2326Z.md` — QEMU state and SSH identity
  mismatch before point-in-time snapshot inspection.
- `point-in-time-snapshot-20261015T2330Z.md` — snapshot creation, read-only
  LUKS2/Btrfs inspection, backup checksums, checkpoint state, and commands.
- `point-in-time-snapshot-20261015T2340Z.md` — later snapshot integrity and
  package progress evidence.
- `point-in-time-snapshot-20261015T2347Z.md` — package 174 compiler progress,
  32-bit build evidence, and filtered error scan.
- `point-in-time-snapshot-20261015T2352Z.md` — subsequent build progress
  evidence from the target copy.
- `point-in-time-snapshot-20261015T2355Z.md` — ABI-pass transition and
  updated compiler progress.
- `point-in-time-snapshot-20261016T0004Z.md` — subsequent x86_64 compiler
  progress.
- `point-in-time-snapshot-20261016T0008Z.md` — package completion events,
  checkpoint state, and the read-only tree-log replay limitation.
- `qemu-launch-command.txt` — the running headless QEMU invocation.

The pre-install target copy was checked with `qemu-img check` and contained no
errors (SHA-256
`3cb0de024967f22d2d27eb875686ba876014d26caf00a696d07696753e9242bd`). The
test-only LUKS key is held in a root-only file outside the
repository; neither it nor the temporary LiveGUI account password is captured
here. No installed-system boot has occurred in this retry yet. Desktop,
gaming, development, virtualization, user setup, encrypted reboot, and first
login remain unverified for this run.
