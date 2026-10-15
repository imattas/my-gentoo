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

## Encrypted UEFI boot and first login

`gentoo-uki-initramfs-first-attempt.log` records the initial boot failure: the
systemd initramfs lacked `systemd-cryptsetup` because the generated
`sys-apps/systemd` USE flags omitted `cryptsetup`. The package configuration
was corrected and Gentoo rebuilt systemd from source. The successful retry is
captured in `gentoo-encrypted-boot-login.log`; the sanitized log shows the
firmware loading the fallback EFI loader, the production UKI starting, the
LUKS prompt and unlock, normal systemd targets, and a console login as
`rehearsal`. `gentoo-first-boot-verification.log` records `systemctl
is-system-running` returning `running`, the logged-in user and `wheel` group,
and `findmnt` output for Btrfs `/`, `/home`, `/.snapshots`, `/var/log`, and
the VFAT ESP. The guest used only disposable qcow2 disk serial
`GQ-BOOT-261015`; no physical disk was attached. The disposable test key and
login password are not present in these evidence files. SHA-256 hashes:

- `gentoo-encrypted-boot-login.log`: `862e5a23a9e3a13fff1c9e619e0d4d8c5de091f17e70e079274206643600eddd`
- `gentoo-first-boot-verification.log`: `8a0cb73b703c7e64e5ff9083ba3772cc6582f36ea9536330cdbf55605f6672fa`
- `gentoo-uki-initramfs-first-attempt.log`: `b520f879ba3259c3db277b09c229014d8a18f7951caf5b1efb6c3c2506f4eebd`

Reproduce the project-side UKI validation with the repository's boot asset
validator against the rehearsal ESP mount. The successful VM output above is
runtime evidence; package-install and UKI section inspection alone are not.

## Disposable LUKS2 wrong-key integration test

Run `bash scripts/integration/luks-negative-unlock.sh` as root on Linux with
`cryptsetup`, `losetup`, and `truncate`. It creates a temporary file, attaches
only that new file to an allocated loop device, formats LUKS2, rejects a wrong
fixture key, then checks and opens the mapping with the correct fixture key.
An exit trap closes the mapping, detaches the loop device, and removes the
temporary directory. The run in this rehearsal passed under Ubuntu 22.04 in
WSL2. Output is in `luks-negative-unlock.log`. This verifies cryptsetup's
negative and positive key paths against disposable file-backed storage; it is
not a substitute for the separate encrypted UEFI boot rehearsal. The output
record SHA-256 is
`e1cd52e7fcacfec6adbc03a58b2c5742fc687a1a3fbcacfc93d667d841e80b4c`.

## Installer and rollback verification record

`readiness-verification.log` preserves the reproducible unit, CLI integration,
compile, and whitespace-check command output. It records 53 unit tests plus 6
subtests and 6 temporary-EFI rollback integration cases passing. SHA-256:
`92d363eed15b0ae6f1c380b9661f0023a0b573bcbae2c1a369838b67e1fbd77d`.
The rollback integration fixture simulates a failed update by placing an
invalid production image beside a known-good fallback; it verifies the CLI
restores the fallback and refuses corrupt fallback images, an unmounted ESP,
the wrong ESP partition identity, the wrong parent-disk serial, or a root that
is not the expected Btrfs `@` mapper. It does not reboot a VM after rollback.

## Current explicit systemd-boot production and fallback entries

`gentoo-explicit-production-entry-boot.log` and
`gentoo-explicit-fallback-entry-boot.log` record QEMU/KVM OVMF serial excerpts
from boots of the current ESP menu configuration on a disposable qcow2
copy-on-write overlay backed by the successful rehearsal target. The first
boot displayed the explicit production entry and selected it after the five
second default timeout. The second boot isolated other UKIs in that overlay so
the previous-production fallback entry was the only choice. Both logs show
Linux 6.18.54, the expected LUKS UUID, device discovery, and the cryptsetup
passphrase prompt. No passphrase was entered: the disposable key had already
been removed. Therefore these runs prove entry selection and boot to encrypted
root unlock only; the earlier `gentoo-encrypted-boot-login.log` remains the
unlock, mount, systemd, and login proof. No physical disk was attached.

SHA-256:

- `gentoo-explicit-production-entry-boot.log`: `17dea1a88bda98b8177b395eca1c17162551ed30d749f1e7b38b1cb576636e46`
- `gentoo-explicit-fallback-entry-boot.log`: `546f1d3b5bc7473d46870638321680d2abc2f0a572ae6941602824f5ef2a14e0`

## Current WSL Restic fixture round trip

`restic-smoke-wsl-current.log` captures a fresh execution of
`scripts/backup-restore-smoke.sh` using Ubuntu WSL's Restic 0.12.1 and a
temporary file-backed repository. The one-file fixture restored and passed the
script's byte comparison. The temporary repository and password file were
removed at exit; this is a client/script smoke test, not recovery from an
independent backup disk. SHA-256:
`6d0a503b93f4e2646f41cb05e77f1165da9cf991b9f9051c539a140e121b3aa4`.

## Storage resume refusal integration checks

`storage-resume-integration.log` records `python -m unittest discover -s
tests/integration -v`, `python -m pytest -q tests/unit`, compileall, and
`git diff --check`. The three new CLI-level integration cases enter through
`resume storage` and verify that malformed checkpoint JSON, an unexpected disk
serial, and a storage command already marked started each stop before calling
the storage command runner. Discovery and command execution are controlled test
fixtures; these cases do not write a block device. The full integration suite
reports 9 passed; unit tests report 53 passed and 6 subtests passed. SHA-256:
`bfd0ce6c11645aa21655d1a8a542154e3825cf0a52faa7479439729a308c6d3c`.

## QEMU boot after simulated failed-kernel rollback

`gentoo-kernel-rollback-qemu-boot.log` records a disposable-overlay recovery
rehearsal. The test replaced the production UKI with an invalid stub, invoked
the project's `rollback_production_uki()` function to restore the preserved
fallback, regenerated the production/fallback boot entries, and booted the
result under OVMF/QEMU. The restored image reached the encrypted-root
passphrase prompt. No test key was entered. The ESP passed `fsck.vfat -n`
before and after the boot, QEMU exited cleanly through QMP, and the qcow2 check
reported no errors. This is a function-level rollback and boot rehearsal; the
guarded `kernel-rollback` CLI was not invoked inside Gentoo. Evidence SHA-256:
`d50f4c2ed6f73ebf422f1eb6eea4925caaa1308c13aaf1f8c31d945c8bb8162d`.

## Current full test and static-check run

`readiness-verification-current.log` records the latest unit and integration
test runs plus compileall, rescue-script syntax, and whitespace checks. It
reports 55 unit tests, 6 unit subtests, and 11 integration tests passing.
SHA-256:
`82dd86adfaa317946fdde62fa87665479181c1fcf27dbce5f64c5caf04f96ada`.

The two `recover-package` integration cases execute the CLI against a temporary
state directory and a Gentoo-style unavailable-atom log. The correct confirmed
log digest reopens the failed checkpoint; an incorrect digest is refused and
leaves it closed. Neither case executes Portage or touches a block device.

## Destructive storage-stage loop rehearsal

`storage-stage-loop.log` captures the actual storage stage running against an
8 GiB sparse file attached as a fresh loop device under Ubuntu 22.04/WSL2. GPT
partitioning, LUKS2 formatting/opening, Btrfs and FAT32 formatting, all four
Btrfs subvolumes, all planned mounts, and checkpoint/event-log persistence
passed. The actual `scripts/rescue.sh` then reopened that LUKS2 filesystem,
mounted Btrfs read-only, and retrieved a fixture file. A second invocation
with a mismatched disk serial refused before opening a mapper. The harness
cleans its temporary file, mounts, mapper, aliases, and loop device. WSL did
not provide by-partlabel udev links, so the harness created temporary aliases
only after direct GPT-label verification on the test loop partitions. It
stubs the loop device's absent model/serial fields and supplies the test key
through a temporary command wrapper. This proves storage and the rescue script
on a disposable filesystem, not booted recovery media, an independent backup,
a full installation rehearsal, or physical hardware.
Reproduce it with:
`wsl.exe -d Ubuntu-22.04 -u root -- bash -lc 'cd
/mnt/c/Users/ian/Downloads/genroo && PYTHONPATH=. python3
scripts/integration/storage-stage-loop.py'`. SHA-256:
`2d3e451fc643cc9ec9e65ad2b5376886879117dc6567bdd8910cac475cc33017`.
