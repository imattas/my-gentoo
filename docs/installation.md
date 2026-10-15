# Installation Preparation

The deployment controller is designed to run from an official Gentoo AMD64
LiveGUI or minimal installation image. Download the current image and its
published verification data from Gentoo, verify it, and write it to a USB
device using a trusted imaging tool. Boot in UEFI mode with Secure Boot
temporarily disabled only if the selected live image requires that; do not
change firmware keys or enable/disable unrelated firmware options.

Before installation, confirm that important files have a separate verified
backup, retain working recovery media, and record the current partition layout
and drive identities. Boot the live environment, establish a network connection,
and run `bash scripts/preflight.sh`. Inspection prints the discovered state and
does not write to disks. Review the Samsung model, serial, stable by-id link,
partitions, mounts, UEFI state, memory, and network. Choose a whole-disk path
from that exact Samsung device's `by_id` values, then render and save a plan on
the removable recovery/storage device, for example:

```bash
python3 -m installer.cli plan \
  --by-id /dev/disk/by-id/<verified-Samsung-whole-disk-id> \
  > /mnt/recovery/gentoo-storage-plan.json
```

Review the complete plan, including the existing partition inventory and its
erasure effects. Before any future write stage, revalidate the saved plan after
confirming the independent backup and recovery media:

```bash
python3 -m installer.cli validate \
  --plan /mnt/recovery/gentoo-storage-plan.json \
  --backup-verified --recovery-media-verified
```

Validation compares current identity, partition, and mount state against the
saved plan. `authorize` additionally requires typing the plan's full SHA-256
and exact disk serial; it only records scope and does not execute commands. To
create that authorization record on the recovery device after you have reviewed
the full plan:

```bash
python3 -m installer.cli authorize \
  --plan /mnt/recovery/gentoo-storage-plan.json \
  --confirm-plan-hash <full-plan-sha256> \
  --confirm-serial '0025_384B_3140_238C.' \
  --backup-verified --recovery-media-verified \
  > /mnt/recovery/gentoo-storage-authorization.json
```

Only after reviewing that plan and explicitly choosing to erase the Samsung
drive, run `install storage` with the recovery device mounted at
`/mnt/recovery`. It requires the hash, serial, exact phrase, fresh inspection,
backup/recovery acknowledgements, and an external state directory. Use a
separate USB or other external disk for `/mnt/recovery`; the SN8100 is protected
and must not hold installer state. The state and event log are stored there. An
interrupted command is never replayed automatically; inspect and resolve the
disk state before continuing.

```bash
python3 -m installer.cli install storage \
  --plan /mnt/recovery/gentoo-storage-plan.json \
  --authorization /mnt/recovery/gentoo-storage-authorization.json \
  --confirm-plan-hash <full-plan-sha256> \
  --confirm-serial '0025_384B_3140_238C.' \
  --confirm-erasure ERASE-SYSTEM-DISK \
  --state-dir /mnt/recovery \
  --backup-verified --recovery-media-verified
```

The configured WD_BLACK SN8100 remains ineligible as an automatic target. Do not
partition either NVMe until the installer renders a fresh plan with the exact
drive identity and the operator explicitly authorizes that specific write.
The Stage 3 archive in the repository is not trusted until checked against
current official Gentoo verification metadata.

`config/workstation.yaml` is JSON, which is a strict subset of YAML. This keeps
the preflight reader limited to Python's standard library in the live image.

## Stage 3 verification

The checked-in Stage 3 archive is pinned by filename and SHA512 in the
workstation config. Its local SHA512 matches the value published in Gentoo's
`DIGESTS` file; signature verification still needs to be completed from verified
Gentoo live media. Download the matching metadata and detached signature beside
the archive, then verify both signatures and the hash before extraction:

```bash
stage3=stage3-amd64-systemd-20261011T170049Z.tar.xz
base=https://distfiles.gentoo.org/releases/amd64/autobuilds/current-stage3-amd64-systemd
curl -fL "$base/$stage3.DIGESTS" -o "$stage3.DIGESTS"
curl -fL "$base/$stage3.asc" -o "$stage3.asc"
python3 -m installer.cli verify-stage3
```

The verified Gentoo LiveGUI media must provide
`/usr/share/openpgp-keys/gentoo-release.asc`. Verify the live ISO itself before
trusting its bundled release keyring. The controller verifies the signed
metadata, the archive's detached signature, and the matching SHA512. Extraction
is blocked if any check fails. After the storage stage completed and the LUKS
mapping was confirmed to come from the planned drive, extract the archive:

```bash
python3 -m installer.cli install stage3 \
  --storage-plan /mnt/recovery/gentoo-storage-plan.json \
  --state-dir /mnt/recovery
```

## Base system, kernel, and desktop

After Stage 3 extraction, configure the profile and base files. The tool confirms
the exact mounted EFI/root filesystems, reads the LUKS, Btrfs, and EFI UUIDs,
checks that GCC accepts `znver4`, then writes Portage settings, `/etc/fstab`,
locale, timezone, hostname, dracut, and kernel command-line configuration.
These values can be changed through the command options:

```bash
python3 -m installer.cli configure \
  --storage-plan /mnt/recovery/gentoo-storage-plan.json \
  --state-dir /mnt/recovery \
  --timezone America/New_York \
  --locale en_US.UTF-8 \
  --hostname gentoo-workstation
```

Install the distribution-managed kernel and baseline tools, then KDE and audio
with separate Portage stages. Portage's `--ask` prompt presents the dependency
plan before each package operation. The base stage installs systemd-boot into
the ESP without writing UEFI NVRAM variables, then requires both the bootloader
and a production UKI to exist before it records success.

```bash
python3 -m installer.cli install packages --set base \
  --storage-plan /mnt/recovery/gentoo-storage-plan.json \
  --state-dir /mnt/recovery
python3 -m installer.cli install packages --set desktop \
  --storage-plan /mnt/recovery/gentoo-storage-plan.json \
  --state-dir /mnt/recovery
```

Gaming, development, virtualization, and backup packages are separate sets:
run the same command with `--set gaming`, `development`, `virtualization`, or
`security_backup` after the desktop set succeeds. The gaming stage installs
`eselect-repository` and Git, enables and syncs Gentoo's `steam-overlay`, then
passes the Steam launcher atom from that repository to Portage. Review the
package plan and any overlay keyword, license, or USE decisions before
continuing. MangoHud and Nix are not in the current main
Gentoo repository, so this installer does not add third-party overlays or run
upstream installers for them. Gentoo may stop at a license,
keyword, or USE-flag decision; review Portage's proposed changes and resolve
those deliberately. The global profile stays stable; the config does not enable
`~amd64` packages by default. Live metadata validation scoped `~amd64` and
`ValveSteamLicense` acceptance to the overlay Steam launcher and scoped
`~amd64` to its masked multilib dependencies and Gamescope.
Virtualization validation also confirmed that the synced QEMU binpkg requires
`sys-firmware/edk2-bin`; the config scopes its `~amd64` keyword acceptance and
sets `net-libs/gnutls` `pkcs11` and `tools` only for the virt-manager
dependency. Do not add the blocking `sys-firmware/edk2` source atom alongside
that binpkg.

Encrypted-root boot also needs `cryptsetup` enabled for `sys-apps/systemd`.
The disposable UEFI rehearsal caught that without this USE flag, the systemd
initramfs omitted `systemd-cryptsetup` and waited forever for the root mapper.
The generated package.use configuration now enables the flag.

Create the interactive login after the desktop stage. The password is entered
through `passwd`'s terminal prompt; it is never passed in command arguments or
written to installer state:

```bash
python3 -m installer.cli install user \
  --username <your-linux-login> \
  --storage-plan /mnt/recovery/gentoo-storage-plan.json \
  --state-dir /mnt/recovery
```

The base configuration uses the stable KDE/systemd desktop profile for the
Stage 3 release, explicit AMD `VIDEO_CARDS`, 32-bit ABI support, and a
memory-bounded build job count. The production kernel is `gentoo-kernel-bin`;
when a different valid production UKI is promoted, the installer saves the
previous image as `gentoo-fallback.efi` and creates separate systemd-boot menu
entries. The loader menu remains visible for five seconds and defaults to
production. If an update fails, select “Gentoo Workstation (previous
production kernel)” from the systemd-boot menu. After booting that image, run
as root to restore it under the production filename:

```bash
python3 -m installer.cli kernel-rollback --root /
```

The rollback command validates the fallback UKI and embedded root command line
before atomically replacing the production image. The checkpointed
`experimental_kernel` package set builds Gentoo's `sys-kernel/gentoo-kernel`
source distribution kernel alongside the production `gentoo-kernel-bin`
package. It explicitly disables local and remote binary packages, so Portage
compiles the source ebuild. It depends on the completed base stage and does not rewrite the
production UKI or systemd-boot default. After it completes, inspect
`/efi/EFI/Linux/` and pass its generated source-kernel UKI to
`kernel-stage-experimental`; that command copies it to the isolated
experimental entry. Choose that entry manually from systemd-boot to test it.
The source-built 7.2.10 experimental kernel has been staged and booted in the
disposable OVMF rehearsal: it unlocked LUKS2, mounted the configured Btrfs
subvolumes, reached systemd `running`, and accepted login. Running the rollback
CLI inside Gentoo after a failed kernel update, Secure Boot signing, and
recovery-media restore remain unverified. Physical reboot and first actual
unlock/boot remain operator-controlled.
