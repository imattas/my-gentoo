#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this disposable integration test as root." >&2
    exit 2
fi

for command in cryptsetup losetup truncate; do
    command -v "$command" >/dev/null || {
        echo "Missing required command: $command" >&2
        exit 2
    }
done

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/gentoo-luks-integration.XXXXXX")
loop_device=
mapping_open=0
cleanup() {
    if [[ $mapping_open -eq 1 ]]; then
        cryptsetup close gentoo-luks-integration
    fi
    if [[ -n $loop_device ]]; then
        losetup --detach "$loop_device"
    fi
    rm -rf -- "$work_dir"
}
trap cleanup EXIT

image="$work_dir/luks2.img"
truncate -s 96M "$image"
loop_device=$(losetup --find --show "$image")

# These are disposable fixture values. They never appear in argv or output.
good_key='gentoo-disposable-integration-key-9e43'
wrong_key='wrong-disposable-integration-key-44a1'
printf '%s' "$good_key" | cryptsetup luksFormat --type luks2 --batch-mode --key-file - "$loop_device"

if printf '%s' "$wrong_key" | cryptsetup open --test-passphrase --key-file - "$loop_device"; then
    echo "FAIL: incorrect disposable key was accepted" >&2
    exit 1
fi
echo "PASS: LUKS2 rejected an incorrect key on the disposable loop device"

printf '%s' "$good_key" | cryptsetup open --test-passphrase --key-file - "$loop_device"
printf '%s' "$good_key" | cryptsetup open --key-file - "$loop_device" gentoo-luks-integration
mapping_open=1
cryptsetup status gentoo-luks-integration >/dev/null
cryptsetup close gentoo-luks-integration
mapping_open=0
echo "PASS: correct disposable key opened and closed only the test mapping"
