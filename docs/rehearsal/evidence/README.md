# QEMU rehearsal evidence

These files come from builder state `/var/lib/gentoo-installer-run9`. The
builder and target are QEMU qcow2 disks; no physical drives were attached.

## Completed Gentoo world merge

- `packages-base-world.log.gz` is the installer captured output for command 0,
  `emerge --ask=n --verbose --update --deep --newuse --with-bdeps=y @world`.
- Raw log SHA-256: `a0959e16e9dd9c82c94e8311028ec12d21e6013f372419f7f50005b72746e12a`.
- Compressed artifact SHA-256: `685bc9c190f8d13825786590a999f3c409281e433f022873b168b65cedf1f277`.
- Inspect with `gzip -cd packages-base-world.log.gz`.

## Firmware atom metadata failure

`base-firmware-mask-rejected.log` preserves the second base command's
pre-merge failure. Gentoo metadata provided `sys-kernel/linux-firmware`, but
masked its current ebuild with `~amd64` and the `linux-fw-redistributable`
license. The file SHA-256 is
`ee0c70df79a83d0df25cb5f871352bb2269b86ad1b6a4dc672b7f60c0b21f155`.

The preceding failed resolution named the obsolete atom
`sys-firmware/linux-firmware`; its log hash was recorded as
`ea8d31f684aaa9cfc2c1e6b578e419d6211043f6f2e59ac14d2f0740f698c7ac`. The
installer reused the same log filename on its next attempt, so the original
contents were overwritten before they were copied here. The log naming has
since been changed to retain an independent file for each attempt.

The corrected config accepts the current firmware atom's testing keyword and
license only for that package. The hash reviewed recovery command used the
rehearsal's exact plan:

```sh
sudo python3 -m installer.cli --config /tmp/qemu-workstation.json recover-package \
  --set base --storage-plan /tmp/storage-plan-run3.json \
  --state-dir /var/lib/gentoo-installer-run9 --command-index 1 \
  --confirm-log-sha256 ee0c70df79a83d0df25cb5f871352bb2269b86ad1b6a4dc672b7f60c0b21f155 \
  --non-interactive
```

This log proves resolution stopped before any merge marker. It does not prove
the subsequent package set or boot has completed; see the main rehearsal record.

## Kernel initramfs hook failure

`base-kernel-dracut-failure.log` preserves the first kernel install failure.
The kernel's Btrfs filesystem support was built in, but dracut also needed
`btrfs-progs` userspace tools; Portage reached the kernel before installing
that package because both were in one unordered emerge request. The failed log
SHA-256 is
`70c5a73d324fe036d875a07087c08df58502138d58ec696b05fd8278f5b14693`.
The full 9.1 MiB log is retained as `base-kernel-dracut-failure.log`.

The base stage now installs Btrfs, cryptsetup, and dracut before a separate
kernel command. Hash gated recovery installed `btrfs-progs`, ran the installed
kernel's `emerge --config`, and reopened the package checkpoint. That generated
a 70 MiB (73,231,872 byte) EFI UKI. `objdump -h` showed nonempty `.linux`, `.initrd`, and
`.cmdline` sections; `objdump -s -j .cmdline` showed the expected LUKS UUID,
root mapper, Btrfs `@` subvolume, and `rw`. This is UKI construction evidence;
it is not proof that systemd-boot can load or boot it.

## Desktop package provisioning and recovery

`gentoo-desktop-evidence.tar.gz` contains captured desktop package resolution
attempts, the successful 237-package merge log, and hash-reviewed recovery for
the Gentoo SysV hook failure. Archive SHA-256:
`299074985c3273f8c55888faae6c776a40e2aa593c5e21e415502f4806c9433c`. List
members with `tar -tzf gentoo-desktop-evidence.tar.gz`; inspect one with
`tar -xOf gentoo-desktop-evidence.tar.gz <path>`. The successful emerge log
SHA-256 is `37685752c119ccaa5131f4ccada4216b03d845829cf1d937e6312c13a6bc26e1`.
These logs prove package merge and recovery behavior only, not boot or desktop
runtime behavior.
