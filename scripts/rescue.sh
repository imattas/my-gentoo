#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this from verified Gentoo LiveGUI media as root." >&2
    exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config_path=${GENTOO_WORKSTATION_CONFIG:-"$script_dir/../config/workstation.yaml"}
if [[ ! -r "$config_path" ]]; then
    echo "Cannot read workstation identity config: $config_path" >&2
    exit 2
fi
if ! target_identity=$(python3 - "$config_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    config = json.load(config_file)
storage = config["storage"]
target = storage["system_target"]
data = storage["data_disk"]
values = (target["model"], target["serial"], data["serial"])
if any(not isinstance(value, str) or not value.strip() for value in values):
    raise SystemExit("system and data disk identities must be non-empty strings")
print("\t".join(value.strip() for value in values))
PY
); then
    echo "Cannot read valid system and protected disk identities from $config_path" >&2
    exit 2
fi
IFS=$'\t' read -r expected_model expected_serial protected_serial <<<"$target_identity"
if [[ -z "$expected_serial" || -z "$protected_serial" || "$expected_serial" == "$protected_serial" ]]; then
    echo "Configured system and protected disk identities are missing or collide." >&2
    exit 2
fi

crypt_partition=/dev/disk/by-partlabel/GENTOO-CRYPTROOT
mountpoint=/mnt/gentoo-rescue

if [[ ! -e "$crypt_partition" ]]; then
    echo "The labeled Gentoo encrypted-root partition was not found." >&2
    exit 2
fi
parent_name=$(lsblk -no PKNAME "$crypt_partition" | sed 's/[[:space:]]*$//')
if [[ ! "$parent_name" =~ ^[[:alnum:]_.+-]+$ ]]; then
    echo "Could not safely identify the labeled partition's parent disk." >&2
    exit 2
fi
parent_disk="/dev/$parent_name"
disk_model=$(lsblk -dn -o MODEL "$parent_disk" | sed 's/[[:space:]]*$//')
disk_serial=$(lsblk -dn -o SERIAL "$parent_disk" | sed 's/[[:space:]]*$//')
if [[ "$disk_model" != "$expected_model" || "$disk_serial" != "$expected_serial" || "$disk_serial" == "$protected_serial" ]]; then
    echo "Labeled partition identity mismatch; refusing to open it." >&2
    echo "Expected model: $expected_model; serial: $expected_serial" >&2
    echo "Observed model: $disk_model; serial: $disk_serial" >&2
    exit 2
fi
if cryptsetup status gentoo-root >/dev/null 2>&1; then
    echo "The gentoo-root mapping is already open; refusing to reuse an unknown mapping." >&2
    exit 2
fi

cryptsetup open --readonly "$crypt_partition" gentoo-root
mkdir -p "$mountpoint"
mount -t btrfs -o ro,subvol=@ /dev/mapper/gentoo-root "$mountpoint"
echo "Gentoo root is mounted read-only at $mountpoint."
echo "Copy recovered files to a separately identified external backup device."
