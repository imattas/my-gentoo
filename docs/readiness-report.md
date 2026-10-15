# Gentoo installer readiness report

Assessment date: 2026-10-15
Repository: `imattas/my-gentoo`, branch `codex/gentoo-workstation`  
Status: **NOT READY FOR PHYSICAL INSTALLATION**

## Current evidence

- `python -m pytest -q tests/unit`: 48 passed, with 6 subtests. `python -m compileall -q installer tests` and `git diff --check` passed.
- A QEMU/KVM Ubuntu builder booted under OVMF in WSL2. It has only its own system disk and a disposable 140 GiB target qcow2 attached; no physical drive was attached.
- Gentoo Stage 3 release signature and SHA512 were verified, and the archive was extracted into LUKS2 backed Btrfs. The target repository snapshot signature was verified. The synced Gentoo tree selected `default/linux/amd64/23.0/desktop/plasma/systemd`.
- Live Portage resolution found and diagnosed two dependency cycles. With `sys-libs/ncurses -gpm` and `dev-python/pillow -truetype`, the synced `@world` plan resolved and merged all 361 packages, including 237 official binary packages. The separate base set exposed an obsolete firmware atom, real `~amd64` and license masks, and a dracut Btrfs tooling order failure. The atom, package scoped exceptions, and base/kernel stage order are fixed. Hash reviewed checkpoint recovery installed `btrfs-progs`, successfully reran kernel `emerge --config`, and generated a valid UKI section layout with the expected encrypted-root command line. systemd-boot installation and VM boot are still pending.
- Checking Gentoo's current kernel-install guidance against the synced metadata exposed a missing `systemd` USE flag on `sys-kernel/installkernel`; it is now part of the generated configuration and was synchronized into the running target before kernel installation.
- A wrong LUKS test key was rejected by `cryptsetup open --test-passphrase` without creating a mapping. This was run against the disposable QEMU target.
- Implemented code covers explicit device identity checks, checkpoint persistence, target chroot mount cleanup, package command logs, and UKI content checks. Unit fixtures exercise these paths; they do not substitute for end-to-end proof.

The detailed run log, commands, disk identities, and evidence paths are in [the QEMU rehearsal record](rehearsal/gentoo-install-2026-10-14.md). The target's live Portage log is `/mnt/gentoo/var/log/emerge.log` in the builder; run state and logs are under `/var/lib/gentoo-installer-run9` in the builder.

## Readiness by area

| Area | Status | Evidence and remaining work |
|---|---|---|
| Device discovery and destructive target guard | Implemented; unit tested | Exact identity and plan hash checks exist. Positive and negative discovery scenarios still need disposable Linux integration coverage. |
| Stage 3 and base repository setup | Exercised in QEMU | Signed Stage 3 and repository snapshot verified; profile selected from actual synced metadata. |
| Portage base `@world` | Tested in QEMU | Live plan resolved and all 361 packages merged. This does not establish a working boot. |
| Requested package sets | Partial | Base set and systemd-boot installation commands completed. The desktop set is merging after two stale atom corrections and an AMD Radeon `libdrm` USE correction. Gaming, development, virtualization, and backup remain. Steam overlay metadata and its package have not yet been validated in the VM. |
| Chroot orchestration and checkpoints | Implemented; unit tested | Bind mounts, resolver restoration, package logs, and failure state are implemented. Interrupted installation recovery is not yet fully integrated-tested. |
| LUKS2 and Btrfs | Storage stage exercised; boot unproven | Disposable target was encrypted, formatted, and mounted with the configured Btrfs subvolumes. Wrong-key rejection is proven. Initramfs unlock and boot-time subvolume mounts are not. |
| systemd-boot and UKI | Loader installed; boot pending | The ESP contains `EFI/systemd/systemd-bootx64.efi`, the fallback loader, and the project-generated UKI with `.linux`, `.initrd`, `.cmdline` sections and the exact LUKS/Btrfs root tokens. Installer validation, firmware boot, and encrypted unlock remain unproven. |
| KDE Wayland, NetworkManager, PipeWire | Configuration only | No completed target desktop session, network service, audio service, or login has been observed. |
| AMDGPU/RADV and 32-bit Vulkan | Configuration only | Gentoo USE/VIDEO_CARDS and ABI intent are configured; no GPU renderer or 32-bit Vulkan workload has been run. |
| Steam/Proton/Gamescope | Unfinished | Overlay setup, package resolution, installation, and game launch are unverified. |
| Development and virtualization | Configuration only | Package availability/build, host KVM/libvirt, and guest/container operation are unverified. |
| Production/experimental kernels | Partial | Separate package intent and production UKI guard exist. Kernel update rollback and a failed-update recovery have not been demonstrated. |
| Backup and restore | Unfinished | Restic is listed, but no backup policy or restore rehearsal exists. |
| Failure-injection matrix and diagnostics | Partial | Unit tests cover selected state and image failures. Real QEMU evidence includes a rejected wrong LUKS key, package atom/keyword/license failures, and a failed kernel post-install hook with reviewed hash recovery. The initial unavailable-atom log was overwritten by a later retry; later failure logs are preserved. Interrupted install, corrupt state, wrong identity, invalid boot image, and package-unavailable cases still need reproducible integration runs and preserved results. |

## Remaining hardware-dependent checks

- Physical UEFI firmware boot and the chosen Secure Boot policy.
- Discovery of the actual NVMe device identities and a reviewed plan that preserves the independent data SSD.
- Radeon RX 7900 XTX firmware, amdgpu, Mesa RADV, KDE Wayland output, and 64-bit/32-bit Vulkan workloads.
- Real Ethernet/Wi-Fi, DNS, firewall, audio devices, PipeWire, suspend/resume, and multi-monitor behavior.
- Steam/Proton and Gamescope workload on the actual GPU.
- Physical-host virtualization extensions and KVM/libvirt guest boot.
- Independent backup destination, Restic restore, and rescue-media file recovery.

## Release gate

Do not install this project on a physical drive until the disposable VM completes package installation, generates and validates the intended UKI, boots it through systemd-boot, unlocks LUKS2 from initramfs, mounts the expected Btrfs root, reaches systemd, and verifies login as the configured user. Preserve commands, serial output, Portage logs, and each failure-injection result. Also rehearse backup restoration and recovery after a failed kernel update. These gates have not passed, so this project is not production-ready.
