# Gentoo Workstation Installer

This repository contains a staged deployment controller for the workstation
described in [ARCHITECTURE.md](ARCHITECTURE.md). The target is Gentoo amd64,
systemd, KDE Plasma Wayland, encrypted Btrfs on the Samsung 990 PRO, with a
separately protected WD_BLACK SN8100.

## Current status

- `inspect`: Linux live-environment hardware, network, firmware, and disk report
- `plan` / `validate` / `authorize`: exact-device storage plan with explicit
  backup, recovery, hash, and serial gates
- `install storage` / `resume storage`: checkpointed encrypted Btrfs preparation
- `verify-stage3` / `install stage3`: signature and checksum verification, then
  extraction into the verified encrypted Btrfs root
- `configure`: stable KDE/systemd profile, Portage, fstab, encrypted-root UKI,
  locale, timezone, and hostname setup
- `install packages`: base kernel/boot and KDE/audio stages, followed by
  separately gated gaming, development, virtualization, and backup groups
- `install user`: desktop-gated local account creation with an interactive
  password prompt
- Encrypted production and experimental kernel boots and console/SSH login are
  verified in QEMU; a separate full install from Gentoo LiveGUI is in progress
- Hardware runtime checks, independent recovery-media restore, and physical
  deployment remain unverified

The commands that partition or format storage are available only in the Gentoo
Linux live environment. They fail on Windows. Review
[docs/installation.md](docs/installation.md) before preparing live media. Never
use the WD_BLACK SN8100 for installer state or modify it before system boot has
been verified and it has its own separate authorization.

## Development checks

```sh
python3 -m unittest discover -s tests/unit -v
python3 -m compileall -q installer tests
```
