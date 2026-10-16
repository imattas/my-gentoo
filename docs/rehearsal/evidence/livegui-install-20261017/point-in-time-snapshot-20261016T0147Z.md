# Point-in-time snapshot: 2026-10-16 01:47 UTC

- The target observation image `target-observe-20261016T0145Z.qcow2` has a
  recorded WSL mtime of 01:45:53 UTC. `qemu-img check` passed with no errors.
- Its emerge log records Mesa package 251 complete and `sys-apps/util-linux`
  package 252 compiling.
- Installed Mesa USE metadata is:
  `X abi_x86_32 abi_x86_64 amd64 cpu_flags_x86_sse2 elibc_glibc kernel_linux llvm llvm_slot_22 opengl proprietary-codecs video_cards_radeonsi vulkan wayland zstd`.
- A separate state image, `state-observe-20261016T0147Z.qcow2`, passed
  `qemu-img check`. Mounted read-only with ext4 `ro,noload`, it recorded
  `complete: false`, `completed: []`, `package_set: base`, and only the
  `@world` command-started event. No package command is checkpointed complete.
- QEMU reported the VM running at 01:46:47 UTC. The target is disposable; no
  physical drive is attached.
- The target LUKS/Btrfs inspection used read-only mappings and
  `rescue=nologreplay`; the state image used `ro,noload`. All mounts and NBD
  devices were detached after inspection. No passphrase is included.
- Base `@world` is still active. Kernel, remaining sets, reboot, encrypted root
  unlock, systemd startup, and configured-user login remain unverified in this
  clean retry.
