#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY to an independent backup repository}"
: "${RESTIC_PASSWORD_FILE:?Set RESTIC_PASSWORD_FILE to a protected password file}"

if [[ ! -r "$RESTIC_PASSWORD_FILE" ]]; then
    printf 'RESTIC_PASSWORD_FILE is not readable\n' >&2
    exit 2
fi

command -v restic >/dev/null || {
    printf 'restic is not installed\n' >&2
    exit 127
}

restic backup \
    --tag gentoo-workstation \
    --exclude-caches \
    /etc /home /efi
