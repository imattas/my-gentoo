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
- The base `@world` set resolved 363 packages and was still running at the
  latest capture. Gentoo's emerge log showed package 67/363 in progress at
  22:58 UTC. The checkpoint correctly remains incomplete until the command
  exits successfully.

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
- `base-progress-current.log` — QEMU block counters, active Portage process,
  and Gentoo emerge log tail captured at 22:46 UTC.
- `qemu-launch-command.txt` — the running headless QEMU invocation.

The pre-install target copy was checked with `qemu-img check` and contained no
errors (SHA-256
`3cb0de024967f22d2d27eb875686ba876014d26caf00a696d07696753e9242bd`). The
test-only LUKS key is held in a root-only file outside the
repository; neither it nor the temporary LiveGUI account password is captured
here. No installed-system boot has occurred in this retry yet. Desktop,
gaming, development, virtualization, user setup, encrypted reboot, and first
login remain unverified for this run.
