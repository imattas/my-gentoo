# Gentoo QEMU installation rehearsal

Run date: 2026-10-14 to 2026-10-15. Status: **in progress; not a production readiness pass**.

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
- Local unit suite after current installer fixes: `python -m pytest -q tests/unit` — 50 passed, 6 subtests.
  `python -m compileall -q installer tests` and `git diff --check` passed.

## Completed provisioning and current gate

The `@world` command completed all 361 packages. The base command initially
failed before merging because the firmware atom had changed category, then
failed resolution because Gentoo masks the current firmware ebuild by keyword
and redistributable license. Those observations are preserved in
`/var/lib/gentoo-installer-run9/logs/packages-base-command-1.log` in the builder.
The config now uses `sys-kernel/linux-firmware`, with package specific `~amd64`
and `linux-fw-redistributable` acceptance. A bounded recovery command verifies
the failed log hash and exact storage/base checkpoint hashes before reopening
a command. The base merge then exposed a kernel hook order failure: dracut's
Btrfs module also needs `btrfs-progs` userspace tools. The first saved kernel
failure log is in [`evidence/base-kernel-dracut-failure.log`](evidence/base-kernel-dracut-failure.log).
The installer now separates base tools from the kernel command. Hash reviewed
recovery installed `btrfs-progs` and successfully ran
`emerge --config =sys-kernel/gentoo-kernel-bin-6.18.54`; its output is in the
builder's `logs/package-recovery-kernel-20261015T015334Z.log`. That generated
the first UKI at
`/mnt/gentoo/efi/EFI/Linux/b9e356061f78ffd6207d6a6f6ad01cea-6.18.54-gentoo-dist-bin.efi`.
`objdump` confirmed nonempty Linux, initrd, and command-line PE sections. The
base package set and separate 237-package desktop set then completed. Live
metadata rejected the old SDDM and NetworkManager applet atoms and required
`video_cards_radeon` for `x11-libs/libdrm`; these were corrected. A Gentoo SysV
hook caused offline `systemctl --root enable` to call unavailable
`update-rc.d`; the installer now creates native systemd links and its recovery
command accepts only the recorded failure with matching hashes.
`validate_boot_assets()` returned `gentoo-production.efi`. The target has its
graphical default, NetworkManager and SDDM links, and `rehearsal` wheel account.
`visudo --check`, `getent`, `groups`, and `passwd -S` succeeded in the chroot.

The LUKS test passphrase was not saved in the repository or rehearsal logs and
is unavailable in the current session. Thus systemd-boot reboot, encrypted
unlock, and interactive login remain unverified. Enter the original test key
at the disposable VM console if it is known; otherwise recreate the disposable
target with an operator-known test key and repeat the rehearsal. Run state and
logs remain in `/var/lib/gentoo-installer-run9` in the builder.

The gaming package set completed after resolving its live keyword and license
requirements against Gentoo metadata. Its command logs remain under
`/var/lib/gentoo-installer-run9/logs`; Steam, Proton, and Gamescope runtime
behavior is untested. The development package set is still compiling
`llvm-core/lldb-22.1.8` from source. Virtualization and Gentoo `security_backup`
package sets have not run. A Restic 0.18.1 fixture backup and restore round
trip passed in the Ubuntu builder; its log and SHA-256 are recorded in
[`evidence/README.md`](evidence/README.md). This does not validate Gentoo's
Restic package or the eventual independent backup destination.

## Not yet proven

This rehearsal completed package provisioning and installer UKI validation,
but has not rebooted from systemd-boot, unlocked LUKS from the initramfs,
mounted Btrfs during target boot, reached systemd, or interactively logged in
as the configured user. KDE, networking, audio, AMDGPU/RADV, 32-bit Vulkan,
Steam, development, virtualization, backup restore, kernel rollback, and the
full failure-injection matrix remain unverified. Do not treat this report as
authorization to install on a physical drive.
