# Gentoo Workstation: Deployment Architecture

**Status:** Approved target design; implementation pending  
**Target:** Linux-only desktop, AMD Ryzen 7 7800X3D, Radeon RX 7900 XTX, ASRock X670E Steel Legend, Samsung 990 PRO 2 TB, WD_BLACK SN8100 4 TB  
**Owner:** Local machine operator  
**Automation:** Codex-assisted, resumable Gentoo deployment

## 1. Goals and constraints

Build a Gentoo workstation for high-performance gaming, systems programming, reverse engineering, cybersecurity research, and virtualized labs. The machine must remain practical as a daily driver while supporting custom kernel and Mesa experiments. The installer must be executable by a coding agent in a suitable live Linux environment, with observable progress, deterministic configuration, recovery points, and meaningful verification.

The design favors a stable production baseline with selective testing packages and separate experimental builds. Hardware tuning must be benchmark-driven rather than assumed beneficial. The machine will not dual-boot Windows.

## 2. System architecture

| Layer | Decision | Notes |
|---|---|---|
| Distribution | Gentoo Linux amd64 | Stable profile, selective `~amd64` keywords |
| Init | systemd | Integrated service, log, and virtualization management |
| Profile | Desktop/systemd/multilib | Confirm exact current profile with `eselect profile list` |
| Package management | Portage | USE flags, package-specific overrides, pinned versions |
| Desktop | KDE Plasma 6, KWin Wayland | SDDM; XWayland compatibility |
| Audio | PipeWire, WirePlumber | Per-device validation |
| Networking | NetworkManager | Firewall managed separately |
| Graphics | Kernel AMDGPU, Mesa RADV, RadeonSI | Include multilib Vulkan/OpenGL support for Steam |
| Production kernel | Distribution-managed Gentoo kernel | Known-good baseline |
| Experimental kernel | Custom `gentoo-sources` build | Separate boot entry and rollback path |
| Boot | UEFI, systemd-boot, Unified Kernel Images | Secure Boot signing as a separately verified stage |
| Filesystem | LUKS2 + Btrfs | zstd compression, explicit subvolumes |
| Virtualization | QEMU/KVM, libvirt, OVMF | Isolated lab networks |
| Containers | Podman, Distrobox | Project-specific dependencies |
| Reproducibility | Nix package manager for development shells | Portage remains host system manager |
| Security | nftables, encryption, sudo | Secure Boot optional until signed-UKI setup verified |
| Backup | Restic to independent storage | Btrfs snapshots are not backups |

## 3. Physical storage and boot

### Samsung 990 PRO, 2 TB: system disk

Use stable `/dev/disk/by-id/` identifiers verified against `lsblk`, `udevadm`, and drive model/serial. The exact partition identifiers are generated only after inspection.

- GPT partition table.
- 2 GiB EFI System Partition (FAT32), mounted at `/efi`, for systemd-boot and signed/unsigned UKIs.
- Remaining capacity: LUKS2 container, Btrfs filesystem.
- Btrfs subvolumes: `@` mounted `/`, `@home` mounted `/home`, `@snapshots` mounted `/.snapshots`, `@log` mounted `/var/log`.
- Suggested mount settings: `compress=zstd:3,noatime`; enable periodic TRIM using `fstrim.timer` after compatibility validation.
- Use zram for swap initially; no hibernation guarantee until a compatible encrypted disk-swap design is explicitly implemented.

### WD_BLACK SN8100, 4 TB: data disk

- GPT, LUKS2, Btrfs mounted at `/data`.
- Directories/subvolumes for `steam`, `vms`, `datasets`, `projects`, `builds`.
- Create no-COW directories for selected VM image workloads **before** files are created where benchmarking supports this choice; account for the resulting loss of Btrfs data checksums for those files.
- Do not modify this drive until system boot is verified and a separate erasure authorization names this exact drive. The architecture's approval is not disk-erasure authorization.

### Boot sequence

`UEFI → systemd-boot → production or experimental UKI → initramfs → LUKS2 unlock → Btrfs root → systemd → SDDM → Plasma Wayland`

Maintain a known-good production UKI when deploying experimental kernels. EFI partition free space and UKI retention must be monitored. Kernel command-line root and unlock identifiers must be derived from actual UUIDs, not guessed. Secure Boot is enabled only after enrolling/verifying signing keys, signing all required boot components, and confirming recovery procedures. Kernel lockdown implications for BPF, kexec, modules, and debug interfaces must be documented and tested. Do not fake or bypass boot-integrity attestations.

## 4. Hardware and graphics configuration

- AMD Ryzen 7 7800X3D: use Zen 4-appropriate compiler settings conservatively (`-O2 -pipe -march=znver4` as a candidate, subject to toolchain verification). Avoid global `-Ofast` and indiscriminate LTO.
- Build parallelism should account for actual RAM and memory pressure, not only 16 logical CPU threads.
- Radeon RX 7900 XTX: kernel AMDGPU + firmware + Mesa RADV for Vulkan, RadeonSI for OpenGL. Verify 32-bit userspace graphics for Steam/Proton.
- Multiple monitors: KWin Wayland first, with validation of refresh rates, VRR, scaling, HDR (if required), suspend/resume, and XWayland applications.
- UEFI: SVM and IOMMU enabled for KVM; record firmware settings. EXPO and ReBAR only if supported and stable. No unattended firmware changes.
- Confirm network controller drivers, audio, Bluetooth, USB peripherals, and input devices from live hardware inspection.

## 5. Software workloads

### Gaming

Steam (multilib), Proton, MangoHud, GameMode, Gamescope where compatible, and controller support. Establish native and Proton game baselines before testing alternate Mesa/kernel builds. Measure average FPS, 1% lows, frametimes, and stability. Unsupported kernel anti-cheat remains a compatibility limitation regardless of distro.

### Development

Native GCC, Clang/LLVM, binutils, CMake, Ninja, GDB, LLDB, Rust, Python, Go, Node.js, Git, perf, bpftool, bpftrace, and related debugging tools. Use per-project virtual environments, containers, or Nix flakes for reproducibility. Do not let Nix replace Portage as the system package manager.

### Cybersecurity and kernel research

QEMU/KVM, libvirt, OVMF, virt-manager; separate guest networks for vulnerable lab systems. Maintain guest images for general Linux, security tooling, and custom kernel debugging. Isolate potentially hostile samples and test targets from the home LAN. Host eBPF/tracing capabilities are evaluated against the actual kernel configuration and Secure Boot lockdown state.

## 6. Deployment controller architecture

The coding agent **develops, tests, and orchestrates** a deterministic installation engine. The engine, rather than ad-hoc model-generated root commands, executes reviewed stages. A suggested Python CLI calls small, auditable Bash/system utilities and uses declarative YAML configuration.

```text
Codex agent
  ├── architecture/config authoring
  ├── static checks and disposable VM tests
  ├── live-environment orchestration
  └── troubleshooting and evidence review
           │
           ▼
Deployment CLI + state machine
  ├── discovery / preflight
  ├── plan and authorization
  ├── partition / encryption / mounts
  ├── stage3 / chroot / Portage
  ├── kernel / initramfs / UKI / boot
  ├── desktop / GPU / gaming
  ├── development / virtualization / security
  └── verification / reporting / recovery
```

### Required repository layout

```text
gentoo-workstation/
├── AGENTS.md
├── README.md
├── config/
│   ├── workstation.yaml
│   ├── packages.yaml
│   └── kernel.yaml
├── installer/
│   ├── cli.py
│   ├── discovery/
│   ├── planning/
│   ├── authorization/
│   ├── stages/
│   ├── state/
│   └── verification/
├── templates/
│   ├── portage/
│   ├── kernel/
│   ├── boot/
│   ├── storage/
│   └── services/
├── provisioning/
│   ├── desktop/
│   ├── gaming/
│   ├── development/
│   ├── virtualization/
│   └── security/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── qemu/
├── docs/
│   ├── installation.md
│   ├── recovery.md
│   ├── operations.md
│   └── validation.md
└── scripts/
    ├── preflight.sh
    ├── verify.sh
    └── rescue.sh
```

### Execution stages

| Stage | Work | Exit gate |
|---|---|---|
| 0 | Inspect hardware, firmware, network, backups, required games | Complete inventory and compatibility report |
| 1 | Resolve by-id disk identifiers and render exact write plan | Operator approves exact disk and erasure scope |
| 2 | Partition and encrypt authorized system disk | Re-read layout, UUIDs, LUKS status |
| 3 | Create Btrfs subvolumes and mount tree | Validate mount topology |
| 4 | Fetch/verify stage3; unpack and configure chroot | Verified artifacts and working Portage |
| 5 | Select profile, configure packages and services | Configuration checks pass |
| 6 | Build/install production kernel, initramfs, UKI, boot manager | Verify EFI entries and encrypted-root parameters |
| 7 | Install KDE, AMD graphics, audio, networking | Package and service validation |
| 8 | Install gaming, development, KVM, container tools | Tool availability and smoke tests |
| 9 | Configure backups, firewall, recovery, optional signing | Recovery evidence and security checks |
| 10 | First physical reboot (operator controlled) | Actual host boots and unlocks successfully |
| 11 | Validate hardware and gaming, establish baseline | Final report with pass/fail/untested |
| 12 | Separately authorize and configure data SSD | Exact data-disk identity and backup gate |

Each stage is checkpointed with a versioned state record, input hashes, verified output conditions, and logs. `resume` must revalidate existing state before proceeding; never repeat a destructive action solely because a checkpoint is missing. Install logs and state must be persisted to an external or otherwise non-target location during disk preparation, then copied into the installed system. Do not record passphrases or key material.

### Proposed CLI

```bash
gentoo-installer inspect
gentoo-installer plan
gentoo-installer validate
gentoo-installer install
gentoo-installer resume
gentoo-installer verify
gentoo-installer report
```

These are proposed commands to implement, **not** currently available Gentoo commands.

## 7. Authorization and execution boundaries

The user has approved the architecture and wants substantial automation. This approval does not prove that existing files are backed up or authorize an unspecified disk wipe. The deployment engine can autonomously perform nondestructive inspection, downloads, builds, configuration, and VM tests. It may perform disk writes only after the operator reviews a plan identifying exact drive model, serial, stable path, partitions, and irreversible consequences, and explicitly authorizes that specific operation. A separate confirmation is required to erase the second SSD. The agent must never broaden the authorized scope on its own.

Encryption secrets are entered interactively through non-logging mechanisms and never stored in Git, prompts, command arguments, or logs. No automatic BIOS/UEFI trust-key enrollment or firmware changes. Physical reboot and final hardware checks remain operator-mediated. Installation must fail closed on ambiguous device identity, insufficient backups, missing recovery media, or unexpected partition changes.

## 8. Verification and acceptance criteria

- **Build and test:** ShellCheck/formatters, Python tests, schema validation, mock block-device tests, idempotency and failure-injection tests, full disposable QEMU install with encrypted root and UEFI boot.
- **Boot:** Production UKI appears in boot manager and boots; initramfs unlocks LUKS2; root mounts expected Btrfs subvolume; fallback kernel retained.
- **Graphics:** AMDGPU bound, RADV Vulkan enumerated, KDE Wayland session starts, all monitors detected, hardware acceleration operational.
- **Gaming:** Steam launches, 32-bit Vulkan dependencies present, at least one known-compatible game tested on physical hardware; benchmark results recorded, not fabricated.
- **Development:** C/C++/Rust/Python smoke builds pass; GDB/LLDB work; Nix shell enters; containers build and run.
- **Virtualization:** KVM available, libvirt starts, OVMF guest boots, lab network isolation verified.
- **Security:** LUKS2 status checked, firewall active, boot-signing state accurately reported, backup and restore test documented.
- **Recovery:** Rescue media can unlock and mount encrypted root, restore known-good boot image, and recover from a failed experimental kernel.

Classify checks as **passed**, **failed**, **blocked**, or **not tested**. Never treat a configuration file's existence as proof that a feature works.

## 9. Operational practices

- Stable Portage profile and production kernel as baseline; selectively keyword newer packages and record reasons.
- Before risky upgrades: back up configuration and important data, retain previous working kernel/UKI, record installed package versions.
- Monitor EFI space, Btrfs usage, SSD health, kernel logs, and backup freshness.
- Benchmark one tuning change at a time, retain reproducible results, and revert regressions.
- Keep an offline copy of LUKS recovery information and a verified rescue USB.
- Track deviations from this architecture in version control and an architecture decision log.

## 10. Open decisions for implementation

1. Actual installed RAM capacity and available build memory.
2. Exact current SSD contents, partition tables, backup locations, and verified erasure scope.
3. Monitor models, refresh rates, HDR/VRR requirements, and peripheral inventory.
4. Must-play games and any Windows-only or anti-cheat-dependent workflows.
5. Preferred encryption unlock method, recovery strategy, and optional TPM enrollment.
6. Whether to enable signed Secure Boot UKIs after the initial boot.
7. Backup destination and retention policy.
8. Exact current Gentoo profile, package names, USE flags, firmware, and kernel version as validated against upstream documentation at implementation time.

## 11. Authoritative references

- Gentoo AMD64 Handbook: https://wiki.gentoo.org/wiki/Handbook:AMD64
- Gentoo kernel documentation: https://wiki.gentoo.org/wiki/Kernel
- Gentoo systemd-boot: https://wiki.gentoo.org/wiki/Systemd-boot
- Gentoo AMDGPU: https://wiki.gentoo.org/wiki/AMDGPU
- Gentoo Steam: https://wiki.gentoo.org/wiki/Steam
- Btrfs documentation: https://btrfs.readthedocs.io/
- systemd UKI documentation: https://www.freedesktop.org/software/systemd/man/latest/ukify.html

This document is the implementation contract, not a claim that the installer or its tests already exist.
