# Live host observation

Observed 2026-10-15 around 23:26 UTC. The VM was not stopped or reset.

## QEMU

- PID 120557 remained `Sl`, elapsed 52:45, approximately 107% CPU.
- The command line still had the verified LiveGUI ISO attached read-only,
  `target-retry.qcow2`, and `state.qcow2`. No physical block device is listed.
- Monitor `info status`: `VM status: running`.
- Monitor `info blockstats`: target `wr_bytes=5277172736`; an earlier adjacent
  observation read `wr_bytes=5256160256`. The target remains actively attached,
  so the qcow2 must not be inspected or modified concurrently.
- Monitor `info usernet` showed a forwarded SSH connection to `10.0.2.15:22`.

## SSH identity mismatch

Using the temporary LiveGUI account on host port 2223 returned:

```text
hostname: livecd
uname -r: 6.18.33.2-microsoft-standard-WSL2
/etc/os-release: Ubuntu 22.04.5 LTS
```

The session did not expose the expected `/dev/vda` target or `/mnt/gentoo` and
`/mnt/recovery` mounts. It is therefore not accepted as a guest status query.
The last trustworthy package log remains the saved 23:15 UTC capture at
110/363. No package completion or boot validation is inferred from current
target write counters.

## Reproduction

From PowerShell in the repository:

```powershell
wsl.exe -d Ubuntu-22.04 -u root -- bash -lc 'ps -p 120557 -o pid,stat,etime,pcpu; ss -lntp | grep 2223'
```

In WSL, query the running QEMU monitor at
`/root/gentoo-qemu-rehearsal/livegui-install/monitor-retry.sock` using QEMU HMP
`info status`, `info usernet`, and `info blockstats`. To identify the SSH
endpoint, run `sshpass` on forwarded port 2223 with the temporary LiveGUI
credentials and read `hostname`, `uname -r`, `/etc/os-release`, and `lsblk`.
Do not store the temporary password in evidence.
