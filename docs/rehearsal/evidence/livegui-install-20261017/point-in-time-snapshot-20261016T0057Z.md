# Point-in-time snapshot: 2026-10-16 00:57 UTC

- QEMU monitor reported the rehearsal VM running. The target's cumulative write
  counter was 8,854,373,376 bytes. The only attached install target is a
  disposable qcow2.
- `target-observe-20261016T0057Z.qcow2` passed `qemu-img check` with no errors.
- The read-only `@log` snapshot showed packages 243 (`net-libs/gnutls`),
  244 (`net-libs/libmicrohttpd`), and 245 (`net-libs/nghttp2`) complete;
  package 246 (`net-misc/curl`) was compiling. The set is still base `@world`
  (363 packages total).
- LUKS and Btrfs were read-only; Btrfs used `rescue=nologreplay`, which may
  omit pending tree-log replay. Inspection mounts, mapper, NBD device, and
  temporary normalized key were removed.
- Kernel installation, the remaining package sets, installed-target reboot,
  encrypted unlock, systemd startup, and configured-user login remain untested
  in this clean retry. Physical installation remains gated.
