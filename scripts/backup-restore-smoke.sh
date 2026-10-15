#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY to an initialized independent test repository}"
: "${RESTIC_PASSWORD_FILE:?Set RESTIC_PASSWORD_FILE to a protected password file}"

if [[ ! -r "$RESTIC_PASSWORD_FILE" ]]; then
    printf 'RESTIC_PASSWORD_FILE is not readable\n' >&2
    exit 2
fi
command -v restic >/dev/null || {
    printf 'restic is not installed\n' >&2
    exit 127
}
command -v cmp >/dev/null || {
    printf 'cmp is required\n' >&2
    exit 127
}

workdir="$(mktemp -d "${TMPDIR:-/tmp}/gentoo-restic-smoke.XXXXXX")"
trap 'rm -rf -- "$workdir"' EXIT
source_dir="$workdir/source"
restore_dir="$workdir/restore"
mkdir -p "$source_dir" "$restore_dir"
printf 'gentoo-restic-restore-check\n' >"$source_dir/restore-check.txt"
tag="gentoo-restic-smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$"

restic backup --tag "$tag" "$source_dir"
restic restore latest --tag "$tag" --target "$restore_dir"
cmp "$source_dir/restore-check.txt" \
    "$restore_dir$source_dir/restore-check.txt"
printf 'PASS\tRestic backup and restore round-trip\n'
