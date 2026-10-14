# Gentoo Workstation Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable Gentoo deployment controller for the approved workstation architecture, then use its inspection and rendered plans to guide installation on the Samsung 990 PRO.

**Architecture:** Python CLI with declarative YAML configuration and small auditable Linux utilities. Discovery, plan rendering, and validation are read-only; each mutating stage is explicit, checkpointed, revalidated, and fail-closed. Disk mutation requires a reviewed plan naming model, serial, stable by-id path, exact partitions, and an explicit authorization for that operation.

**Tech Stack:** Python 3, YAML, Bash/system utilities, Gentoo Portage, QEMU for disposable Linux validation.

**Spec:** `ARCHITECTURE.md` (approved deployment architecture)

## Global Constraints

- Never touch the WD_BLACK SN8100 without its own exact-drive erasure authorization.
- Never partition or format the Samsung disk without a newly reviewed exact-device write plan and explicit authorization.
- Do not infer disk identity from `/dev/sdX` or `/dev/nvmeXnY`; resolve and recheck stable by-id identity, model, and serial.
- Do not record secrets in arguments, logs, state, or Git; prompt interactively for encryption secrets.
- Preserve recovery points and a known-good production boot path; physical reboot remains operator-controlled.
- Report checks as passed, failed, blocked, or not tested; configuration presence is not runtime proof.

## Review Focus

- Device order changes between inspection and execution: re-resolve by-id, model, serial, and partition table immediately before writes.
- Interrupted stage or missing checkpoint: inspect actual device state and never replay a destructive operation automatically.
- Untrusted or stale Stage 3 archive: require official manifest/signature or checksum verification before unpacking.
- Insufficient EFI space or incorrect encrypted-root UUID: stop before creating/updating a boot entry.
- Missing network, firmware, graphics, or recovery media in the live environment: report the blocking prerequisite without advancing.

## Files

- Create `config/workstation.yaml`, `config/packages.yaml`, `config/kernel.yaml` for the approved machine and package intent.
- Create `installer/cli.py` plus focused modules under `installer/{discovery,planning,authorization,stages,state,verification}/` for commands and stage boundaries.
- Create `templates/` and `provisioning/` files only when consumed by an implemented stage; avoid speculative package lists.
- Create `scripts/preflight.sh`, `scripts/verify.sh`, `scripts/rescue.sh` as auditable operator entrypoints.
- Create `docs/{installation,recovery,operations,validation}.md` documenting actual commands and evidence.
- Create tests for config/schema, mock block devices, stage idempotency/failure injection, and disposable UEFI QEMU install before relying on unattended deployment.

## Tasks

### Task 1: Configuration and read-only discovery

**Files:** `config/workstation.yaml`, `installer/discovery/`, `installer/cli.py`, `scripts/preflight.sh`, `docs/installation.md`

- [ ] Define target hardware, system disk model/serial, storage policy, stable profile intent, locale/timezone prompts, and build parallelism as data; do not store the data disk as an eligible install target.
- [ ] Implement `gentoo-installer inspect` to report CPU, RAM, firmware boot mode, network, block devices, model/serial/by-id links, existing partition tables, and mount state without writes.
- [ ] Make discovery fail closed on duplicate/unknown device identity and keep logs on a non-target location.
- [ ] Document preparing and booting official Gentoo LiveGUI/minimal media and capturing an external backup/recovery inventory.

### Task 2: Deterministic storage plan and authorization boundary

**Files:** `installer/planning/`, `installer/authorization/`, `installer/cli.py`, `docs/installation.md`

- [ ] Implement `gentoo-installer plan` to render GPT, 2 GiB ESP, LUKS2, Btrfs filesystem/subvolumes, mount layout, and exact commands from current discovered identity without executing them.
- [ ] Include the full model, serial, by-id path, current partition inventory, intended partition sizes, and irreversible effects in the plan.
- [ ] Implement `gentoo-installer validate` to re-discover devices and reject stale plans, identity changes, unexpected partitions/mounts, absent backups, or missing recovery media.
- [ ] Require a separate explicit authorization token/phrase scoped to the exact reviewed plan hash before any destructive stage can start.

### Task 3: Checkpointed storage and Stage 3 setup

**Files:** `installer/stages/storage.py`, `installer/stages/stage3.py`, `installer/state/`, `templates/storage/`, `docs/recovery.md`

- [ ] Implement partition, encryption, filesystem, subvolume, and mount stages as individually invoked operations with preconditions, postcondition checks, durable external logs, and versioned state records.
- [ ] Prompt for LUKS secrets through a non-logging interactive mechanism; derive UUIDs after creation and never guess them.
- [ ] Fetch or validate the Stage 3 archive against current official Gentoo metadata; verify before extraction and reject the unverified local archive.
- [ ] Unpack and configure the chroot only after all artifact and mount checks pass; resume by inspecting actual state, never by blindly replaying a stage.

### Task 4: Base system, kernel, encrypted boot, and desktop

**Files:** `config/packages.yaml`, `config/kernel.yaml`, `installer/stages/`, `templates/portage/`, `templates/kernel/`, `templates/boot/`, `provisioning/desktop/`, `docs/installation.md`

- [ ] Configure the current stable desktop/systemd/multilib profile after checking `eselect profile list` in the target chroot; document any selective testing keywords.
- [ ] Configure conservative Zen 4 compiler settings and memory-aware build parallelism; retain the distribution-managed production kernel.
- [ ] Install and configure initramfs, UKI, and systemd-boot with actual LUKS/Btrfs identifiers; retain a known-good fallback and check EFI capacity.
- [ ] Install KDE Plasma Wayland, SDDM, AMD firmware/Mesa RADV and RadeonSI, 32-bit graphics, PipeWire/WirePlumber, and NetworkManager.
- [ ] Keep Secure Boot signing as a later optional stage; never enroll firmware keys automatically.

### Task 5: Workstation packages, recovery, and runtime verification

**Files:** `provisioning/{gaming,development,virtualization,security}/`, `installer/verification/`, `scripts/{verify,rescue}.sh`, `docs/{recovery,operations,validation}.md`

- [ ] Add Steam/Proton tooling, development toolchains, QEMU/KVM/libvirt/OVMF, Podman/Distrobox, Nix development-shell support, nftables, and Restic using package-specific Gentoo configuration.
- [ ] Keep vulnerable guest networks isolated; do not claim isolation, graphics acceleration, boot integrity, or backup recovery until observed and recorded.
- [ ] Verify production boot, encrypted unlock, Btrfs mounts, desktop/GPU/audio/network, 32-bit Vulkan, KVM guest, backup restore, and rescue-media recovery with explicit pass/fail/blocked/not-tested results.
- [ ] Mark physical reboot and first-host hardware/game validation as operator-controlled gates; configure the SN8100 only after a distinct authorization.

### Task 6: Disposable validation and first physical deployment

**Files:** `tests/`, `docs/validation.md`, deployment state/log output

- [ ] Validate configuration, shell, and Python behavior with focused checks, mock block-device fixtures, idempotency and failure-injection cases.
- [ ] Run a complete UEFI QEMU install using disposable encrypted virtual storage and confirm recovery to a known-good kernel.
- [ ] Generate and review the physical Samsung write plan only after the live USB preflight and backup/recovery gates pass.
- [ ] Execute only the specifically authorized system-disk stages; stop for operator-controlled reboot, then record observed hardware and gaming results.

