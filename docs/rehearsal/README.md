# QEMU builder smoke run

Run date: 2026-10-14. This is evidence that WSL2 KVM, OVMF, QEMU user networking,
the Ubuntu cloud builder, and SSH worked. It is **not** a Gentoo installation
test.

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
No installer was run against the target disk, and the target was not booted.
The cloud seed and ephemeral SSH private key remain outside the repository in
the WSL rehearsal directory. Do not reuse the ephemeral key.
