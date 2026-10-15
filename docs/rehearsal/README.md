# QEMU builder and Gentoo installation rehearsal

The builder booted on 2026-10-14. A Gentoo install rehearsal continued through
2026-10-15 against a separate disposable encrypted qcow2 target. The target
completed encrypted UEFI boot, Btrfs mounts, systemd startup, and configured
user login. This document records the builder setup; current status and
evidence are in [`gentoo-install-2026-10-14.md`](gentoo-install-2026-10-14.md).
No physical drive was attached.

The guest used 4 vCPUs, 8 GiB RAM, an Ubuntu cloud-image overlay, and a separate
blank 140 GiB `target.qcow2`. Both disks were qcow2 files under
`/root/gentoo-qemu-rehearsal`; no physical disk was attached to QEMU. The image
SHA256 matched the adjacent Ubuntu `SHA256SUMS`. OVMF code and a copied variable
store were used. User-mode networking forwarded host port 2222 to guest SSH.

The executed QEMU command was:

```sh
qemu-system-x86_64 \
  -machine q35,accel=kvm -cpu host -smp 4 -m 8G \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=OVMF_VARS_4M.fd \
  -drive file=ubuntu-overlay.qcow2,if=virtio,format=qcow2 \
  -drive file=target.qcow2,if=virtio,format=qcow2 \
  -drive file=seed.iso,media=cdrom,readonly=on \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2222-:22 \
  -device virtio-net-pci,netdev=n0 \
  -display none -serial file:builder-serial.log
```

SSH became available and `/var/tmp/rehearsal-ready` was present:

```sh
ssh -i id_ed25519 -p 2222 \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  gentoo-rehearsal@127.0.0.1 \
  'sudo test -f /var/tmp/rehearsal-ready'
```

The matching builder serial log is [`builder-serial.log`](builder-serial.log).
The installer ran against the disposable target. Gentoo world and configured
package sets completed, and the generated production UKI booted successfully
after adding systemd's `cryptsetup` USE flag. See the rehearsal record for the
boot and first-login evidence and for remaining unverified release gates.
The cloud seed and ephemeral SSH private key remain outside the repository in
the WSL rehearsal directory. Do not reuse the ephemeral key.
