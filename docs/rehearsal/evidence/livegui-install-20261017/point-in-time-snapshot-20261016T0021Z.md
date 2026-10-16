# Point-in-time snapshot: 2026-10-16 00:21 UTC

- QEMU target copy: `target-observe-20261016T0021Z.qcow2`.
- `qemu-img check` reported no errors. The running rehearsal remained active
  after inspection; the target is a disposable qcow2 and no physical disk is
  attached.
- The read-only target `@log` snapshot recorded packages 206
  (`media-libs/glu`) and 207 (`virtual/glu`) complete, package 208
  (`media-libs/freeglut`) complete, and package 209
  (`media-libs/libwebp-1.6.0`) compiling/merging. The resolved base `@world`
  plan contains 363 packages. This observation copy was mounted read-only with
  Btrfs `rescue=nologreplay` because a normal read-only mount requested pending
  tree-log replay; pending replay content may be absent.
- No `!!!`, `fatal error:`, `ERROR:`, `failed`, or `FAILED` markers were found
  in the inspected Portage `build.log` files.
- Installed package metadata from this target snapshot:
  - `media-libs/vulkan-loader-1.4.357.0`: USE includes `abi_x86_32` and
    `abi_x86_64`.
  - `dev-util/spirv-tools-1.4.357.0`: USE includes `abi_x86_32` and
    `abi_x86_64`.
- LUKS was opened read-only from the snapshot; mounts, mapper, temporary key
  file, and NBD device were removed after inspection. The passphrase is not
  recorded.
- The clean retry is still inside base `@world`. Kernel and remaining package
  sets, installed-target UEFI boot, encrypted unlock, systemd startup, and
  configured-user login have not been reached in this retry.

Reproduce the read-only inspection as documented in the adjacent
`point-in-time-snapshot-20261016T0014Z.md`, substituting the image name above.
