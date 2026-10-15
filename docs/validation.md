# Validation record

See [readiness-report.md](readiness-report.md) for the current feature-by-feature
status and the production release gate. Encrypted UEFI boot and first-login
proof passed in a disposable QEMU VM; a full live-media-to-first-boot installer
rehearsal remains unfinished. Unit-test success is not install or boot evidence.

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

The OVMF/QEMU disposable builder completed the Gentoo base world, configured
package sets, and production UKI boot. The VM unlocked LUKS2, mounted the
configured Btrfs subvolumes, reached systemd `running`, and accepted login as
the configured user. The file-backed LUKS negative-unlock integration test
also passed: a wrong test key was rejected and the correct test key opened only
the temporary loop mapping; its image and mapping were removed. Logs and exact
commands are linked from `readiness-report.md` and the rehearsal evidence
index.

The storage stage and read-only rescue entrypoint also have a destructive
integration rehearsal on Ubuntu
22.04/WSL2: `wsl.exe -d Ubuntu-22.04 -u root -- bash -lc 'cd
/mnt/c/Users/ian/Downloads/genroo && PYTHONPATH=. python3
scripts/integration/storage-stage-loop.py'`. It creates an 8 GiB sparse file,
attaches only that file through a newly allocated loop device, then executes
the real GPT, LUKS2, Btrfs, FAT32, subvolume, mount, and checkpoint operations.
The harness refuses to proceed if its target identity or existing installer
mounts/mapping are unsafe, and cleans up only resources it created. Because
this WSL environment does not populate `/dev/disk/by-partlabel`, the harness
confirms GPT labels with `blkid` and creates temporary test aliases to the
verified loop partitions. It then closed the mapping and invoked
`scripts/rescue.sh` against the same disposable encrypted filesystem. The
script mounted Btrfs read-only, retrieved a fixture file, and refused a
mismatched target serial without opening a mapping. The harness stubs only the
QEMU-style model/serial fields absent from loop devices and injects the fixture
key through a temporary wrapper; partitioning, encryption, filesystems,
mounts, and retrieval use real Linux tools. The guarded kernel rollback CLI
also replaced an invalid UKI on the mounted disposable Btrfs/VFAT target and
refused a mismatched serial without writing. This CLI rehearsal ran under
Ubuntu, not inside the booted Gentoo VM; no reboot followed it. The test does
not constitute a booted recovery-media check or validate physical-drive/
firmware behavior. The captured run is
[`storage-stage-loop.log`](rehearsal/evidence/storage-stage-loop.log).

The previous-production UKI preservation and rollback CLI have integration
tests on temporary EFI files, and both current systemd-boot entries were
rehearsed in QEMU to the LUKS prompt using a disposable qcow2 overlay. The
production UKI's full unlock/login proof and the disposable LUKS negative-unlock test
passed. Reproduce kernel recovery coverage with
`python -m unittest discover -s tests/integration -v`; reproduce the LUKS check
with `bash scripts/integration/luks-negative-unlock.sh` as root on Linux.
Backup restore from recovery media, an actual QEMU boot after kernel rollback,
remaining failure-injection executions, Wayland/GPU/audio/network workload
checks, experimental kernel provisioning, and physical hardware validation are
still open. The follow-up menu boots stopped at LUKS because the disposable
test key was removed; the earlier successful production UKI boot provides
unlock/login validation. Do not use the installer on a physical drive until the release gate
in `readiness-report.md` and the live-media plan review and backup/recovery gates
have been completed.
