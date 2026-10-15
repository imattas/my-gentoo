# Gentoo installer readiness report

Assessment date: 2026-10-15
Repository: `imattas/my-gentoo`, branch `codex/gentoo-workstation`  
Status: **NOT READY FOR PHYSICAL INSTALLATION**

## Current evidence

- `python -m pytest -q tests/unit`: 50 passed, with 6 subtests. `python -m compileall -q installer tests` and `git diff --check` passed.
- A QEMU/KVM Ubuntu builder booted under OVMF in WSL2. It has only its own system disk and a disposable 140 GiB target qcow2 attached; no physical drive was attached.
- Gentoo Stage 3 release signature and SHA512 were verified, and the archive was extracted into LUKS2 backed Btrfs. The target repository snapshot signature was verified. The synced Gentoo tree selected `default/linux/amd64/23.0/desktop/plasma/systemd`.
- Live Portage resolution found and diagnosed two dependency cycles. With `sys-libs/ncurses -gpm` and `dev-python/pillow -truetype`, the synced `@world` plan resolved and merged all 361 packages, including 237 official binary packages. The base set exposed a stale firmware atom, current keyword/license masks, and a dracut Btrfs tooling order failure; these were corrected, and hash-reviewed recovery generated a valid UKI. The separate desktop set then merged all 237 packages, including multilib Mesa, PipeWire, FFmpeg, KDE Plasma, and SDDM. Live metadata exposed and corrected stale SDDM and NetworkManager applet atoms plus a Radeon `libdrm` USE requirement. A Gentoo SysV compatibility hook then made `systemctl --root enable` fail because `update-rc.d` was absent; the installer now writes the native systemd links directly and has hash-gated recovery for that exact failure.
- Checking Gentoo's current kernel-install guidance against the synced metadata exposed a missing `systemd` USE flag on `sys-kernel/installkernel`; it is now part of the generated configuration and was synchronized into the running target before kernel installation.
- A wrong LUKS test key was rejected by `cryptsetup open --test-passphrase` without creating a mapping. This was run against the disposable QEMU target.
- `validate_boot_assets()` returned `gentoo-production.efi`; the ESP contains systemd-boot, the fallback EFI loader, and the validated production UKI. The target's graphical default, NetworkManager service link, SDDM display-manager link, and `rehearsal` wheel account are configured. `visudo --check`, `getent`, `groups`, and `passwd -S` succeeded inside the chroot.
- The gaming package set completed in QEMU after live metadata checks corrected the Steam overlay's keyword/license requirements and the current Gamescope and libudev atoms. The development package set is still merging from source (currently `llvm-core/lldb-22.1.8`); virtualization and Gentoo backup package sets have not run yet.
- A Restic 0.18.1 smoke test in the Ubuntu QEMU builder created a tagged snapshot, restored a fixture, and byte-compared it. The reproducible output is in [the evidence log](rehearsal/evidence/restic-smoke.log). This does not validate Gentoo's Restic package or an independent physical backup destination.
- The LUKS test passphrase was deliberately not saved in repository state or logs. It is not available in the current rehearsal context, so a target-only reboot and first-login test cannot yet be performed.
- Implemented code covers explicit device identity checks, checkpoint persistence, target chroot mount cleanup, package command logs, and UKI content checks. Unit fixtures exercise these paths; they do not substitute for end-to-end proof.

The detailed run log, commands, disk identities, and evidence paths are in [the QEMU rehearsal record](rehearsal/gentoo-install-2026-10-14.md). The target's live Portage log is `/mnt/gentoo/var/log/emerge.log` in the builder; run state and logs are under `/var/lib/gentoo-installer-run9` in the builder.

## Readiness by area

| Area | Status | Evidence and remaining work |
|---|---|---|
| Device discovery and destructive target guard | Implemented; unit tested | Exact identity and plan hash checks exist. Positive and negative discovery scenarios still need disposable Linux integration coverage. |
| Stage 3 and base repository setup | Exercised in QEMU | Signed Stage 3 and repository snapshot verified; profile selected from actual synced metadata. |
| Portage base `@world` | Tested in QEMU | Live plan resolved and all 361 packages merged. This does not establish a working boot. |
| Requested package sets | Partial | Base, desktop, and gaming package sets completed in QEMU; gaming metadata and merges were checked against the synced Gentoo tree. Development is actively merging from source. Virtualization and Gentoo backup package sets remain. |
| Chroot orchestration and checkpoints | Implemented; unit tested | Bind mounts, resolver restoration, package logs, and failure state are implemented. Interrupted installation recovery is not yet fully integrated-tested. |
| LUKS2 and Btrfs | Storage stage exercised; boot unproven | Disposable target was encrypted, formatted, and mounted with the configured Btrfs subvolumes. Wrong-key rejection is proven. Initramfs unlock and boot-time subvolume mounts are not. |
| systemd-boot and UKI | Assets validated; boot pending | Installer validation returns `gentoo-production.efi`; the ESP contains the loader, fallback loader, and UKI with `.linux`, `.initrd`, `.cmdline` sections and expected LUKS/Btrfs tokens. Firmware boot and initramfs unlock remain unproven. The test passphrase must be supplied at the rehearsal console or a new disposable target must be installed with a known test passphrase. |
| KDE Wayland, NetworkManager, PipeWire | Packages installed; runtime untested | Native service links and graphical default are present. No systemd boot, Wayland login, network connection, or audio stream has been observed. |
| AMDGPU/RADV and 32-bit Vulkan | Packages built; runtime untested | Mesa multilib, Radeon settings, and Vulkan loader are installed. The VM has no RX 7900 XTX passthrough, so hardware rendering and Vulkan workloads remain untested. |
| Steam/Proton/Gamescope | Packages installed; runtime untested | Steam overlay and package resolution/install passed in QEMU. No Steam login, Proton game, Gamescope session, or GPU accelerated workload has run. |
| Development and virtualization | Partial | Development package merge is running; virtualization package metadata includes `virt-manager`. No full merge or runtime KVM/libvirt/container guest test yet. |
| Production/experimental kernels | Partial | Separate package intent and production UKI guard exist. Kernel update rollback and a failed-update recovery have not been demonstrated. |
| Backup and restore | Partially tested | A Restic builder-VM fixture round trip passed and is logged. Gentoo's `app-backup/restic` merge, actual system backup, independent destination, and full recovery-media restore remain. |
| Failure-injection matrix and diagnostics | Partial | Unit tests cover selected state and image failures. QEMU evidence includes wrong-key rejection, stale atoms, keyword/license/USE failures, a kernel post-install failure, and the systemd SysV-hook failure; reviewed recovery logs and all desktop attempts are archived. Interrupted installation, corrupt state, wrong identity, invalid boot image, unavailable package, backup restore, and failed-kernel rollback still need the full disposable integration matrix. |

## Remaining hardware-dependent checks

- Physical UEFI firmware boot and the chosen Secure Boot policy.
- Discovery of the actual NVMe device identities and a reviewed plan that preserves the independent data SSD.
- Supply the rehearsal LUKS passphrase at the target console or rebuild the disposable target with a known test passphrase; no encrypted-root reboot or configured-user login has been observed.
- Radeon RX 7900 XTX firmware, amdgpu, Mesa RADV, KDE Wayland output, and 64-bit/32-bit Vulkan workloads.
- Real Ethernet/Wi-Fi, DNS, firewall, audio devices, PipeWire, suspend/resume, and multi-monitor behavior.
- Steam/Proton and Gamescope workload on the actual GPU (package installation passed in QEMU, runtime did not).
- Physical-host virtualization extensions and KVM/libvirt guest boot.
- Independent backup destination, Restic restore, and rescue-media file recovery.

## Release gate

Do not install this project on a physical drive until the disposable VM reboots through systemd-boot, unlocks LUKS2 from initramfs, mounts the expected Btrfs subvolumes, reaches systemd, and verifies login as the configured user. Then complete backup restoration and recovery after a failed kernel update, plus the remaining integration failure matrix. These gates have not passed, so this project is not production-ready.
