# Validation record

The Windows development checkout can validate renderers and mocked state
transitions. It cannot prove the Linux live-media path, physical storage,
encrypted boot, graphics, audio, or recovery behavior.

## Before any physical installation

Boot verified Gentoo LiveGUI media, attach the independent recovery disk, and
run `python3 scripts/preflight.sh`. Save the report externally. Review a newly
rendered storage plan, verify the backup and recovery media, and inspect every
partition and command. The Samsung erase operation still requires the exact
plan hash, exact serial, backup/recovery acknowledgements, and the explicit
`ERASE-SYSTEM-DISK` confirmation described in `installation.md`.

## After first boot

Run `bash scripts/verify.sh` as the desktop user. It reports observed checks as
`PASS`, `FAIL`, or `NOT TESTED`; a pass only records the command's current
result. Then separately test Steam/Proton with a real 32-bit Vulkan workload,
boot a disposable KVM guest, restore a sample file from an independent Restic
repository, and boot rescue media to retrieve a file. Record evidence and
results before describing those capabilities as working.

The full encrypted UEFI QEMU rehearsal and physical deployment have not been
run from this Windows workspace. Do not use the installer on either NVMe until
the live-media plan review and backup/recovery gates have been completed.
