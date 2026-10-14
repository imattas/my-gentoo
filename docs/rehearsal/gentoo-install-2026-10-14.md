# Gentoo QEMU installation rehearsal

Run date: 2026-10-14. Status: **in progress; not a production readiness pass**.

## Isolation and reproducibility

The installer ran inside the Ubuntu 22.04 QEMU/KVM builder under WSL2. QEMU
received only the Ubuntu builder disk and a disposable 140 GiB `target.qcow2`;
no host block device or physical drive was attached. The target uses virtio
serial `GQ-TARGET-261014`; the Ubuntu builder uses `GQ-RUNNER-261014`. OVMF
boots the builder. QEMU user networking forwards host port 2222 to builder SSH.
The builder command and boot evidence are in [`README.md`](README.md) and
[`builder-serial.log`](builder-serial.log).

The disposable target was partitioned as GPT with a 2 GiB ESP and a LUKS2
container holding Btrfs. Btrfs subvolumes `@`, `@home`, `@snapshots`, and `@log`
were created and mounted. LUKS UUID: `896d5209-1bc7-46eb-86f3-4c0c41523a9d`;
Btrfs UUID: `8e8230f1-f4f6-4368-8db2-262a2b7e26cf`; ESP UUID: `468E-8F8B`.
The passphrase is not included in this report, state, or logs.

## Completed evidence

- Stage 3 archive signature and SHA512 were verified against Gentoo release
  metadata, then extracted to the encrypted Btrfs target.
- The live Portage snapshot dated 2026-10-13 was fetched by `emerge-webrsync`
  and its OpenPGP signature verified as trusted. The target selected
  `default/linux/amd64/23.0/desktop/plasma/systemd` from the synced profile tree.
- Initial package resolution against the official signed x86-64-v3 binhost
  found a `gpm`/`ncurses` cycle, then a `docutils`/`pillow`/`harfbuzz`/`glib`
  cycle. Portage's suggested USE changes (`ncurses -gpm`, `pillow -truetype`)
  removed both cycles. The updated plan resolved 361 packages (237 binaries).
- A deliberate wrong LUKS test key was rejected by
  `cryptsetup open --test-passphrase`; this read-only test did not create a
  mapping or alter the header.
- Local unit suite: `python -m pytest -q tests/unit` — 42 passed, 4 subtests.
  `python -m compileall -q installer tests` and `git diff --check` passed.

## Active work and logs

The base Portage world update is running on the target. It resolved 361
packages and is being installed with bounded single-job parallelism in the
10 GiB VM. At the latest check it had merged 213 of 361 packages. Portage's
live log is `/mnt/gentoo/var/log/emerge.log` in the builder. The installer
state directory is `/var/lib/gentoo-installer-run9`; after each package command
returns, captured output is written under its `logs/` directory. The VM's
`/var/lib` state disk and target qcow2 remain outside the repository until
copied into this directory.

## Not yet proven

This rehearsal has not yet completed the package install, produced and
validated the project's UKI, rebooted from systemd-boot, unlocked LUKS from the
initramfs, mounted Btrfs during target boot, reached systemd, or logged in as
the configured user. KDE, audio, AMDGPU/RADV, 32-bit Vulkan, Steam, development,
virtualization, backup restore, kernel rollback, and the failure-injection
matrix remain unverified. Do not treat this report as authorization to install
on a physical drive.
