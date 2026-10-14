#!/usr/bin/env bash
set -u

failed=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        printf 'PASS\t%s\n' "$label"
    else
        printf 'FAIL\t%s\n' "$label"
        failed=1
    fi
}

report_untested() {
    printf 'NOT TESTED\t%s\n' "$1"
}

check "PID 1 is systemd" sh -c '[ "$(cat /proc/1/comm)" = systemd ]'
check "encrypted root mapping is open" cryptsetup status gentoo-root
check "root is Btrfs on the Gentoo mapper" sh -c \
    '[ "$(findmnt -n -o FSTYPE /)" = btrfs ] && case "$(findmnt -n -o SOURCE /)" in /dev/mapper/gentoo-root*) exit 0;; *) exit 1;; esac'
check "EFI partition is mounted at /efi" sh -c \
    '[ "$(findmnt -n -o FSTYPE /efi)" = vfat ]'
check "systemd-boot reports installed loader" bootctl status
check "a UKI is installed" sh -c \
    'find /efi/EFI/Linux -maxdepth 1 -type f -name "*.efi" -print -quit | grep -q .'
check "NetworkManager is active" systemctl is-active --quiet NetworkManager.service
check "SDDM is active" systemctl is-active --quiet sddm.service
check "amdgpu kernel driver is loaded" sh -c \
    'lspci -k | grep -A4 -Ei "VGA compatible|Display controller" | grep -q "Kernel driver in use: amdgpu"'
check "KVM device is available" test -c /dev/kvm
if command -v vulkaninfo >/dev/null 2>&1; then
    check "Vulkan query completes" vulkaninfo --summary
else
    report_untested "Vulkan runtime query (install media-libs/vulkan-tools first)"
fi
report_untested "32-bit Vulkan through Steam/Proton"
report_untested "KVM guest boot and graphics acceleration"
report_untested "Restic backup restore from an independent repository"
report_untested "Gentoo rescue-media unlock and file recovery"

exit "$failed"
