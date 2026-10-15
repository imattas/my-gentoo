# Gentoo QEMU installation rehearsal

Run date: 2026-10-14 to 2026-10-15. Status: **encrypted boot/login rehearsal passed; project is not production-ready**.

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

The LUKS test passphrase was not saved in the repository or rehearsal logs.
After enabling `cryptsetup` for `sys-apps/systemd` and rebuilding it from
source, a fresh disposable qcow2 target booted through OVMF, unlocked LUKS2,
mounted the configured Btrfs subvolumes, reached systemd `running`, and
accepted a console login as `rehearsal`. Sanitized serial and verification
logs are in [`evidence/README.md`](evidence/README.md). The test passphrase
and login password are excluded from the repository.

Gaming, development, virtualization, and `security_backup` package sets are
complete. The development set compiled LLDB and bpftrace from source. The
virtualization set initially failed during premerge dependency resolution:
QEMU's binpkg required `edk2-bin`, while the configured `edk2` atom blocked it;
virt-manager also required GnuTLS `pkcs11` and `tools`. The config now selects
`sys-firmware/edk2-bin ~amd64` and scopes the GnuTLS USE flags. Recovery was
gated by the failed-log SHA-256, then the corrected 69-package set completed.
The full Portage logs remain in `/var/lib/gentoo-installer-run9/logs` in the
builder.

QEMU 10.2.3 started a diskless paused guest using the builder's `/dev/kvm` and
was stopped cleanly; no drive was attached. Gentoo Restic 0.19.1 passed the
fixture restore test, backed up 673 files (155.630 MiB) from `/etc`, `/home`,
and `/efi`, and restored `/etc/hostname` to a temporary directory for a
successful byte comparison. Restic ran against a repository on the separate
Ubuntu builder disk. Logs and hashes are recorded in
[`evidence/README.md`](evidence/README.md); this is not an independent
physical-media or full-system recovery-media restore rehearsal.

## Remaining unverified functionality

The disposable UEFI encrypted-boot and configured-user console-login gate has
passed. The installer now preserves the previous production UKI, writes
explicit systemd-boot production/fallback entries, and provides
`kernel-rollback`; its CLI success and corrupt-fallback refusal have passed
against temporary EFI fixtures. A file-backed LUKS2 integration run also
proved wrong-key rejection and correct-key unlock, then removed its loop image.
Reproduce with `python -m unittest discover -s tests/integration -v` and
`bash scripts/integration/luks-negative-unlock.sh` (Linux root).

The source-built `sys-kernel/gentoo-kernel-7.2.10` experimental UKI has since
booted under OVMF, unlocked the rehearsal LUKS2 root, mounted all configured
Btrfs subvolumes, reached systemd `running`, and accepted SSH login. Its build,
initramfs repair, and boot are documented in
[`evidence/README.md`](evidence/README.md) and
[`evidence/gentoo-experimental-first-boot-verification.log`](evidence/gentoo-experimental-first-boot-verification.log).
A separate overlay rehearsal restored a known-good UKI after simulating a
failed production image and booted it to the encrypted-root prompt. The
`kernel-rollback` CLI has not yet run inside the booted Gentoo system followed
by a reboot; full installation from Gentoo LiveGUI and booted recovery-media
restore also remain unverified. KDE Wayland, real networking, audio,
AMDGPU/RADV, 32-bit Vulkan, Steam/Proton, libvirt-managed guests, and container
workloads remain unverified at runtime. This rehearsal is not authorization to
install on a physical drive.
