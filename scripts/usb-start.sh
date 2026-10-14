#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_dir"

if [[ ! -f /etc/gentoo-release ]]; then
    echo "Boot the Gentoo LiveGUI USB first; this launcher only runs in Gentoo LiveGUI." >&2
    exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
    echo "Reopen the terminal as root, then run: bash '$repo_dir/scripts/usb-start.sh'" >&2
    exit 2
fi
command -v python3 >/dev/null || { echo "python3 is required in the live environment." >&2; exit 2; }

state_dir="$repo_dir/state"
mkdir -p "$state_dir"
echo "Installer files: $repo_dir"
echo "External installer state: $state_dir"
echo
echo "Read-only hardware and disk inspection:"
python3 -m installer.cli inspect | tee "$state_dir/preflight-report.json"
echo
echo "Next: review target model/serial/by-id in that report, then render a plan:"
echo "  python3 -m installer.cli plan --by-id /dev/disk/by-id/<exact-Samsung-990-PRO-id> > '$state_dir/gentoo-storage-plan.json'"
echo "Review docs/installation.md before validation or any storage write."
