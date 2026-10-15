# Recovery

Keep verified Gentoo LiveGUI media and an independent backup device available
through installation and the first successful encrypted boot. The installer
state directory and event logs belong on that external device. The WD_BLACK
SN8100 is excluded from both installer state and automated storage changes.

## Read-only root recovery

Boot the verified live media, open a root shell, and run:

```bash
bash scripts/rescue.sh
```

The script opens only the partition labeled `GENTOO-CRYPTROOT` in read-only
mode and mounts Btrfs subvolume `@` at `/mnt/gentoo-rescue`. It refuses to
reuse an already open `gentoo-root` mapping. Copy needed files to an independently
identified backup disk. To finish, run `umount /mnt/gentoo-rescue` and
`cryptsetup close gentoo-root`.

If the labels are absent or the mapping fails, stop and inspect with `lsblk -f`
and `cryptsetup luksDump`. Do not run formatting, repair, or write-mode mount
commands as part of initial diagnosis.

## Failed production kernel update

Each validated production UKI promotion keeps the previous production image at
`/efi/EFI/Linux/gentoo-fallback.efi` and installs explicit production and
fallback entries in systemd-boot. The menu defaults to production after five
seconds. If the new kernel fails, select **Gentoo Workstation (previous
production kernel)**. Once that system is running, run as root:

```bash
python3 -m installer.cli kernel-rollback --root /
```

This validates systemd-boot, the fallback UKI structure, and its embedded
encrypted-root command line, then atomically restores it as
`gentoo-production.efi`. It refuses a missing, corrupt, symlinked, or stale
fallback image. Before writing, the CLI also requires the ESP to be mounted as
VFAT, match the `GENTOO-ESP` partition label, and reside on the exact
system-disk serial in `config/workstation.yaml`; the supplied root must be
Btrfs subvolume `@` on `/dev/mapper/gentoo-root`. This command has been tested
against temporary EFI fixtures; a post-rollback boot in QEMU remains
unverified. The custom experimental kernel build and signing flow are not
implemented yet. The generated entries use systemd-boot's documented `efi`
entry directive and loader timeout format
([upstream boot manager documentation](https://systemd.io/BOOT/)).

## Restic backup and restore check

Install the `security_backup` package set, connect an independent backup
destination, and create a protected Restic password file. From a root shell,
configure the repository and key file, then initialize the repository once:

```bash
export RESTIC_REPOSITORY=/mnt/backup/gentoo-restic
export RESTIC_PASSWORD_FILE=/root/.config/restic/gentoo-password
chmod 600 "$RESTIC_PASSWORD_FILE"
restic init
bash scripts/backup.sh
bash scripts/backup-restore-smoke.sh
```

`backup.sh` snapshots `/etc`, `/home`, and `/efi`; it does not prune old
snapshots. The smoke script writes a uniquely tagged test snapshot, restores it
to a fresh temporary directory, compares a known file, and removes only that
temporary directory. Keep the repository and password file on independent
storage; losing the password file makes the encrypted repository unreadable.
The smoke test validates a small Restic round trip. It does not replace a
separate full-system restore rehearsal from recovery media.

## Installation state

Keep `gentoo-storage-state.json`, `gentoo-stage3-state.json`, package/user
checkpoints, and their JSONL event logs with the reviewed storage plan on the
external recovery device. When a checkpoint has a non-null `started` index,
inspect the target's actual state and Portage logs before proceeding. The
installer intentionally will not retry an interrupted operation automatically.
