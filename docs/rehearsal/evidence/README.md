# QEMU rehearsal evidence

These files come from builder state `/var/lib/gentoo-installer-run9`. The
builder and target are QEMU qcow2 disks; no physical drives were attached.

## Completed Gentoo world merge

- `packages-base-world.log.gz` is the installer captured output for command 0,
  `emerge --ask=n --verbose --update --deep --newuse --with-bdeps=y @world`.
- Raw log SHA-256: `a0959e16e9dd9c82c94e8311028ec12d21e6013f372419f7f50005b72746e12a`.
- Compressed artifact SHA-256: `685bc9c190f8d13825786590a999f3c409281e433f022873b168b65cedf1f277`.
- Inspect with `gzip -cd packages-base-world.log.gz`.

## Firmware atom metadata failure

`base-firmware-mask-rejected.log` preserves the second base command's
pre-merge failure. Gentoo metadata provided `sys-kernel/linux-firmware`, but
masked its current ebuild with `~amd64` and the `linux-fw-redistributable`
license. The file SHA-256 is
`ee0c70df79a83d0df25cb5f871352bb2269b86ad1b6a4dc672b7f60c0b21f155`.

The preceding failed resolution named the obsolete atom
`sys-firmware/linux-firmware`; its log hash was recorded as
`ea8d31f684aaa9cfc2c1e6b578e419d6211043f6f2e59ac14d2f0740f698c7ac`. The
installer reused the same log filename on its next attempt, so the original
contents were overwritten before they were copied here. The log naming has
since been changed to retain an independent file for each attempt.

The corrected config accepts the current firmware atom's testing keyword and
license only for that package. The hash reviewed recovery command used the
rehearsal's exact plan:

```sh
sudo python3 -m installer.cli --config /tmp/qemu-workstation.json recover-package \
  --set base --storage-plan /tmp/storage-plan-run3.json \
  --state-dir /var/lib/gentoo-installer-run9 --command-index 1 \
  --confirm-log-sha256 ee0c70df79a83d0df25cb5f871352bb2269b86ad1b6a4dc672b7f60c0b21f155 \
  --non-interactive
```

This log proves resolution stopped before any merge marker. It does not prove
the subsequent package set or boot has completed; see the main rehearsal record.

## Kernel initramfs hook failure

`base-kernel-dracut-failure.log` preserves the first kernel install failure.
The kernel's Btrfs filesystem support was built in, but dracut also needed
`btrfs-progs` userspace tools; Portage reached the kernel before installing
that package because both were in one unordered emerge request. The failed log
SHA-256 is
`70c5a73d324fe036d875a07087c08df58502138d58ec696b05fd8278f5b14693`.
The full 9.1 MiB log is retained as `base-kernel-dracut-failure.log`.

The base stage now installs Btrfs, cryptsetup, and dracut before a separate
kernel command. Hash gated recovery installed `btrfs-progs`, ran the installed
kernel's `emerge --config`, and reopened the package checkpoint. That generated
a 70 MiB (73,231,872 byte) EFI UKI. `objdump -h` showed nonempty `.linux`, `.initrd`, and
`.cmdline` sections; `objdump -s -j .cmdline` showed the expected LUKS UUID,
root mapper, Btrfs `@` subvolume, and `rw`. This is UKI construction evidence;
it is not proof that systemd-boot can load or boot it.

## Desktop package provisioning and recovery

`gentoo-desktop-evidence.tar.gz` contains captured desktop package resolution
attempts, the successful 237-package merge log, and hash-reviewed recovery for
the Gentoo SysV hook failure. Archive SHA-256:
`299074985c3273f8c55888faae6c776a40e2aa593c5e21e415502f4806c9433c`. List
members with `tar -tzf gentoo-desktop-evidence.tar.gz`; inspect one with
`tar -xOf gentoo-desktop-evidence.tar.gz <path>`. The successful emerge log
SHA-256 is `37685752c119ccaa5131f4ccada4216b03d845829cf1d937e6312c13a6bc26e1`.
These logs prove package merge and recovery behavior only, not boot or desktop
runtime behavior.

## Restic smoke round trip

`restic-smoke.log` records the `backup-restore-smoke.sh` run against Restic
0.18.1 in the Ubuntu QEMU builder. It created one uniquely tagged snapshot in
a repository stored on the builder disk, restored the fixture to a new
temporary directory, and byte-compared the marker. The script returned
`PASS`; log SHA-256:
`6208f24ee9f92984404c2398bf343808dec9cf765f40db603a3763391c241c86`.
This validates the script's round-trip logic and the builder's Restic client;
the Gentoo `app-backup/restic` package and restore from the eventual independent
physical backup destination remain to be tested.

## Gentoo Restic system backup and restore

`restic-smoke-gentoo.log` records the fixture round trip using the installed
Gentoo `app-backup/restic-0.19.1`; SHA-256:
`9c4be7de367fc23dc2043c1c07c21e10ba1a6b7e2782009eee9749c671929b2c`.
`restic-gentoo-system.log` records `scripts/backup.sh` snapshotting 673 files
(155.630 MiB) from `/etc`, `/home`, and `/efi`, then restoring
`/etc/hostname` from snapshot `ba736e8b` and byte-comparing it successfully;
SHA-256: `0adc30fdd4b2cd2db408e0523bc2ef2bc339707ea02877abd8e6df4417969d71`.
The encrypted repository and protected password file were stored on the
separate Ubuntu builder disk and bind-mounted into the target for the test.
This is a VM backup/restore check, not a physical independent destination or
full recovery-media restore.

## Gentoo QEMU/KVM runtime smoke

`qemu-kvm-smoke.log` records QEMU 10.2.3 starting a paused `q35` machine with
KVM acceleration, 128 MiB RAM, and no disks, firmware images, or network
devices. It exited cleanly after SIGTERM and the temporary KVM bind mount was
removed. SHA-256: `139e4cc1631319d98885b97578cedaedfa5572f21a07a2e7ba321f4750ff5ff3`.
This validates the QEMU binary and KVM device access only; it does not validate
libvirt or boot a guest OS.

## Gentoo Portage package-set build logs

`package-build-logs.tar.gz` contains the development and virtualization
Portage command logs, including the failed premerge attempts and the successful
retries. The development set first failed to resolve stale `sys-devel/gdb`,
then completed after hash-reviewed recovery. Virtualization resolved two
premerge package/USE conflicts before its successful third attempt. The
installer's persisted package state marks both sets complete. Archive
SHA-256:
`693ca9e5fe57cda4ee78c04cdccbf3f32c8efb1412a7673cec74e40d2ca458ee`.

Reproduce log inspection with:

```sh
tar -tzf docs/rehearsal/evidence/package-build-logs.tar.gz
tar -xOzf docs/rehearsal/evidence/package-build-logs.tar.gz logs/packages-development-command-0-attempt-02.log | tail -30
tar -xOzf docs/rehearsal/evidence/package-build-logs.tar.gz logs/packages-virtualization-command-0-attempt-03.log | tail -30
```
