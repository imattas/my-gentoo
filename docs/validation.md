# Validation record

See [readiness-report.md](readiness-report.md) for the current feature-by-feature
status and the production release gate. The full QEMU rehearsal is still
unfinished; unit-test success is not install or boot evidence.

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

The previous-production UKI preservation and rollback CLI have integration
tests on temporary EFI files, and the disposable LUKS negative-unlock test
passed. Reproduce kernel recovery coverage with
`python -m unittest discover -s tests/integration -v`; reproduce the LUKS check
with `bash scripts/integration/luks-negative-unlock.sh` as root on Linux.
Backup restore from recovery media, an actual QEMU boot after kernel rollback,
remaining failure-injection executions, Wayland/GPU/audio/network workload
checks, experimental kernel provisioning, and physical hardware validation are
still open. Do not use the installer on a physical drive until the release gate
in `readiness-report.md` and the live-media plan review and backup/recovery gates
have been completed.
