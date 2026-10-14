#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this from verified Gentoo LiveGUI media as root." >&2
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
if [[ "$disk_model" != "Samsung SSD 990 PRO with Heatsink 2TB" || "$disk_serial" != "0025_384B_3140_238C." ]]; then
    echo "Labeled partition identity mismatch; refusing to open it." >&2
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
