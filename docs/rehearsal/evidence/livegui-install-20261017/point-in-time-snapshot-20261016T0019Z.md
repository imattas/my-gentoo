# Point-in-time snapshot: 2026-10-16 00:19 UTC

- QEMU monitor reported the rehearsal VM running at 00:20 UTC. The disposable
  target write counter was 6,127,813,632 bytes; no physical disk is attached.
- The read-only target snapshot log records `media-libs/vulkan-loader-1.4.357.0`
  complete as package 200/363 and `x11-libs/libXinerama-1.1.6` merging as
  package 201/363. The exact captured log tail is in
  `base-emerge-log-snapshot-20261016T0019Z.log`.
- The nearby 00:11 UTC state image still recorded `complete: false` and no
  completed package commands. The target log was read from a separate
  point-in-time copy. Its Btrfs filesystem required read-only
  `rescue=nologreplay`; pending tree-log replay may therefore be absent.
- `target-observe-20261016T0019Z.qcow2` passed `qemu-img check`; the state
  snapshot passed the same check. All inspection mounts, mappings, and NBD
  devices were detached afterwards.
- Reproduce the disk integrity check with:
  `qemu-img check /root/gentoo-qemu-rehearsal/livegui-install/target-observe-20261016T0019Z.qcow2`
- The Gentoo install remains in the base package merge. No claim is made for
  kernel install, post-base package sets, installed-target reboot, LUKS unlock,
  systemd startup, or configured-user login in this clean retry.
