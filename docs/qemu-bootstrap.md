# QEMU terminal MVP

This is the disposable validation path for the first dynamic framework slice:

1. a real Arch shell where the learner types commands;
2. Chinese mentor and Wiki Textual clients beside that shell;
3. required OpenAI-compatible AI grounded in the trusted Operation Catalog.

It deliberately refuses physical hardware and does not automate disk installation.

## 1. Prepare QEMU and an official Arch ISO

Install QEMU on the host and download the current ISO from the [official Arch download page](https://archlinux.org/download/). Verify its signature before use.

On macOS with Homebrew:

```bash
brew install qemu
```

On Arch Linux:

```bash
sudo pacman -S qemu-desktop edk2-ovmf
```

Inspect the launch plan without changing anything:

```bash
./scripts/qemu-mvp.sh --dry-run /path/to/archlinux.iso
```

## 2. Boot the disposable installation machine

```bash
./scripts/qemu-mvp.sh /path/to/archlinux.iso
```

For a serial-only host session (including CI-style manual validation), boot the
same UEFI Live ISO with:

```bash
./scripts/qemu-mvp.sh --headless /path/to/archlinux.iso
```

The launcher creates only `.qemu/airchinstall.qcow2`, a 32 GiB virtual disk. It never attaches a host disk. On Apple Silicon, x86_64 Arch runs through QEMU emulation and will be slower.

If QEMU firmware is installed in a non-standard location, set `AIRCHINSTALL_OVMF_CODE` and optionally `AIRCHINSTALL_OVMF_VARS`. A writable vars image is required for persistent UEFI boot entries.

In the Arch console, set a temporary root password so the host can copy the prototype:

```bash
passwd
```

From another host terminal, copy the complete source tree:

```bash
ssh -p 60022 root@127.0.0.1 'mkdir -p /root/airchinstall'
scp -P 60022 -r README.md pyproject.toml src scripts root@127.0.0.1:/root/airchinstall/
```

## 3. Run the bootstrap

For the fastest check, run it over SSH; the host terminal supplies Unicode fonts:

```bash
ssh -p 60022 root@127.0.0.1
/root/airchinstall/scripts/bootstrap.sh
```

To test `kmscon` itself, copy the repository first, return to the QEMU console, and run the same command there. The bootstrap stops the unused tty2 getty, starts `kmscon` on tty2, and launches the tmux layout.

The bootstrap asks for an OpenAI-compatible base URL, model and hidden API Key. The three values are written under `/run/airchinstall` with mode `0600`; `/run` is volatile and cleared on reboot. If validation fails, bootstrap returns to the normal rescue Shell.

## 4. Acceptance checks

- The left pane is a real Bash and accepts commands typed by the user.
- The right panes display Chinese without missing glyph boxes.
- `stat -c '%a %n' /run/airchinstall/ai-key` prints `600`.
- `systemd-detect-virt --vm` prints `qemu` or `kvm`.
- `lsblk` shows the disposable target as `/dev/vda`; no host disk is present.
- UEFI, network and disk checks can be run in any order and converge on the same Facts.
- Catalog-external commands may be explained but never become trusted recommendations.
- Exiting QEMU preserves `.qemu/airchinstall.qcow2` for the next boot.

The `--headless` console is normally 80×24, so it exercises the compact layout:
real Bash and Mentor remain side by side, while Wiki moves to its own tmux
window. A terminal of at least 120×30 exercises the three-pane layout.

After a manual Arch installation is complete, boot only the virtual disk:

```bash
./scripts/qemu-mvp.sh --disk-only
```

This framework slice does not yet install the system. The later full-install milestone passes only when the virtual disk reaches a login prompt; a progress counter is never sufficient.
