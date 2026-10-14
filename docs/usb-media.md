# Bootable Gentoo installer USB

The prepared drive layout is intended for Ventoy: the official Gentoo LiveGUI
ISO boots from one file, while the writable Ventoy data partition holds this
installer and the pinned Stage 3 archive. The image and installer do not start
disk writes automatically.

After booting the USB in UEFI mode, open the Ventoy volume in the live desktop
and run, from a terminal:

```bash
sudo bash /run/media/*/Ventoy/Gentoo-Workstation/scripts/usb-start.sh
```

The exact desktop mount path can differ; use the path shown by the file manager.
The launcher requires Gentoo LiveGUI, runs read-only inspection, and stores
reports/checkpoints on the USB data partition. Review the complete plan and
follow `docs/installation.md` before authorizing the Samsung erase operation.
