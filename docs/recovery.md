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

## Installation state

Keep `gentoo-storage-state.json`, `gentoo-stage3-state.json`, package/user
checkpoints, and their JSONL event logs with the reviewed storage plan on the
external recovery device. When a checkpoint has a non-null `started` index,
inspect the target's actual state and Portage logs before proceeding. The
installer intentionally will not retry an interrupted operation automatically.
