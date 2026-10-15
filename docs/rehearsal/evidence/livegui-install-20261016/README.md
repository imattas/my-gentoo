# Interrupted LiveGUI installation rehearsal

The run used a disposable 100 GiB target qcow2 (`GQ-LIVEGUI-INSTALL-20261016`)
and a separate 16 GiB ext4 state qcow2 (`GQ-LIVEGUI-STATE-20261016`). No
physical storage was attached. The Gentoo LiveGUI ISO was read-only.

The persistent package event journal records successful completion of the
`@world`, base package, production binary kernel, sudoers validation, and
systemd-boot commands. It records the desktop emerge invocation as started,
with no completion event. The desktop state remains incomplete, and the
captured desktop command log contains its start record only. After the guest
stopped responding, QEMU was reset. LiveGUI returned to KDE, the ext4 state
disk was mounted read-only, and no emerge process was running. QEMU block
counters show no further writes to the encrypted target after the reset. The
target's LUKS2 container remains closed; this run has not yet resumed.

Files:

- `gentoo-package-events.jsonl` — persistent command start and completion
  events from the state disk.
- `gentoo-packages-desktop.json` — desktop checkpoint, still incomplete.
- `packages-desktop-livegui.log` — desktop command launch record.
- `qemu-live-status.log` — QEMU status, block counters, host CPU sample, and
  guest emerge-process query after recovery.

The earlier `@world` and base completion times are in UTC in the event journal.
The QEMU host status capture includes the host's local timestamp. The LUKS
passphrase and temporary live-account password are not included in this
evidence. To reproduce the status capture, keep QEMU running and query its HMP
socket with `info status` and `info blockstats`; inspect the guest with
`pgrep -a emerge` after mounting only the separate state disk read-only.
