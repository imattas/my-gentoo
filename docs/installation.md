# Installation Preparation

The deployment controller is designed to run from an official Gentoo AMD64
LiveGUI or minimal installation image. Download the current image and its
published verification data from Gentoo, verify it, and write it to a USB
device using a trusted imaging tool. Boot in UEFI mode with Secure Boot
temporarily disabled only if the selected live image requires that; do not
change firmware keys or enable/disable unrelated firmware options.

Before installation, confirm that important files have a separate verified
backup, retain working recovery media, and record the current partition layout
and drive identities. Boot the live environment, establish a network connection,
and run `bash scripts/preflight.sh`. Inspection prints the discovered state and
does not write to disks. Review the Samsung model, serial, stable by-id link,
partitions, mounts, UEFI state, memory, and network. Choose a whole-disk path
from that exact Samsung device's `by_id` values, then render and save a plan on
the removable recovery/storage device, for example:

```bash
python3 -m installer.cli plan \
  --by-id /dev/disk/by-id/<verified-Samsung-whole-disk-id> \
  > /mnt/recovery/gentoo-storage-plan.json
```

Review the complete plan, including the existing partition inventory and its
erasure effects. Before any future write stage, revalidate the saved plan after
confirming the independent backup and recovery media:

```bash
python3 -m installer.cli validate \
  --plan /mnt/recovery/gentoo-storage-plan.json \
  --backup-verified --recovery-media-verified
```

Validation compares current identity, partition, and mount state against the
saved plan. `authorize` additionally requires typing the plan's full SHA-256
and exact disk serial; it only records scope and does not execute commands.

The configured WD_BLACK SN8100 remains ineligible as an automatic target. Do not
partition either NVMe until the installer renders a fresh plan with the exact
drive identity and the operator explicitly authorizes that specific write.
The Stage 3 archive in the repository is not trusted until checked against
current official Gentoo verification metadata.

`config/workstation.yaml` is JSON, which is a strict subset of YAML. This keeps
the preflight reader limited to Python's standard library in the live image.
