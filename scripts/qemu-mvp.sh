#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
STATE_DIR=$PROJECT_DIR/.qemu
DISK=$STATE_DIR/airchinstall.qcow2
VARS_COPY=$STATE_DIR/OVMF_VARS.fd
BOOT_DIR=$STATE_DIR/boot

DRY_RUN=0
DISK_ONLY=0
HEADLESS=0
ISO=''

die() { printf 'qemu-mvp: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  qemu-mvp.sh [--dry-run] [--headless] /path/to/archlinux.iso
  qemu-mvp.sh --disk-only

Creates a persistent 32 GiB virtual disk and forwards guest SSH to
127.0.0.1:60022. The host machine's physical disks are never attached.
EOF
}

while (($#)); do
  case $1 in
    --dry-run) DRY_RUN=1 ;;
    --disk-only) DISK_ONLY=1 ;;
    --headless) HEADLESS=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [[ -z $ISO ]] || die 'only one ISO path may be supplied'; ISO=$1 ;;
  esac
  shift
done

if (( DRY_RUN )); then
  printf '%s\n' \
    "State directory: $STATE_DIR" \
    "Virtual disk: $DISK (32 GiB, virtio)" \
    "Boot mode: $([[ $DISK_ONLY == 1 ]] && printf 'virtual disk' || printf 'UEFI Arch ISO')" \
    "Display: $([[ $HEADLESS == 1 ]] && printf 'serial console' || printf 'graphical console')" \
    'Network: QEMU user NAT with SSH 127.0.0.1:60022 -> guest:22' \
    'Host disks: none attached'
  exit 0
fi

command -v qemu-system-x86_64 >/dev/null || die 'qemu-system-x86_64 is required'
command -v qemu-img >/dev/null || die 'qemu-img is required'

if (( DISK_ONLY )); then
  [[ -f $DISK ]] || die "virtual disk not found: $DISK"
else
  [[ -n $ISO ]] || die 'an Arch ISO path is required'
  [[ -f $ISO ]] || die "ISO not found: $ISO"
fi
(( ! HEADLESS || ! DISK_ONLY )) || die '--headless currently supports the Live ISO only'

mkdir -p "$STATE_DIR"
[[ -f $DISK ]] || qemu-img create -f qcow2 "$DISK" 32G

QEMU_BIN=$(command -v qemu-system-x86_64)
QEMU_PREFIX=$(cd -- "$(dirname -- "$QEMU_BIN")/.." && pwd -P)
OVMF_CODE=${AIRCHINSTALL_OVMF_CODE:-}
OVMF_VARS=${AIRCHINSTALL_OVMF_VARS:-}

if [[ -z $OVMF_CODE ]]; then
  for candidate in \
    /usr/share/edk2/x64/OVMF_CODE.4m.fd \
    /usr/share/OVMF/OVMF_CODE.fd \
    "$QEMU_PREFIX/share/qemu/edk2-x86_64-code.fd"; do
    if [[ -f $candidate ]]; then OVMF_CODE=$candidate; break; fi
  done
fi
if [[ -z $OVMF_VARS ]]; then
  for candidate in \
    /usr/share/edk2/x64/OVMF_VARS.4m.fd \
    /usr/share/OVMF/OVMF_VARS.fd \
    "$QEMU_PREFIX/share/qemu/edk2-i386-vars.fd"; do
    if [[ -f $candidate ]]; then OVMF_VARS=$candidate; break; fi
  done
fi
[[ -n $OVMF_CODE && -f $OVMF_CODE ]] || die 'OVMF firmware not found; set AIRCHINSTALL_OVMF_CODE'

firmware=(-bios "$OVMF_CODE")
if [[ -n $OVMF_VARS && -f $OVMF_VARS ]]; then
  [[ -f $VARS_COPY ]] || cp "$OVMF_VARS" "$VARS_COPY"
  firmware=(
    -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE"
    -drive "if=pflash,format=raw,file=$VARS_COPY"
  )
else
  printf 'qemu-mvp: writable OVMF vars not found; firmware boot entries may not persist\n' >&2
fi

accel=(-accel tcg,thread=multi -cpu max)
if [[ $(uname -s) == Linux && -r /dev/kvm ]]; then
  accel=(-accel kvm -cpu host)
elif [[ $(uname -s) == Darwin && $(uname -m) == x86_64 ]]; then
  accel=(-accel hvf -cpu host)
fi

args=(
  -name airchinstall-mvp
  -machine q35
  "${accel[@]}"
  -smp 4
  -m 4096
  "${firmware[@]}"
  -drive "file=$DISK,format=qcow2,if=virtio"
  -device virtio-rng-pci
  -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:60022-:22
)

if (( DISK_ONLY )); then
  args+=(-boot order=c,menu=on)
else
  args+=(-cdrom "$ISO" -boot order=d,menu=on)
  if (( HEADLESS )); then
    command -v bsdtar >/dev/null || die 'bsdtar is required for headless boot'
    mkdir -p "$BOOT_DIR"
    if [[ ! -f $BOOT_DIR/arch/boot/x86_64/vmlinuz-linux ]]; then
      bsdtar -xf "$ISO" -C "$BOOT_DIR" \
        arch/boot/x86_64/vmlinuz-linux \
        arch/boot/x86_64/initramfs-linux.img
    fi
    ISO_LABEL=$(dd if="$ISO" bs=1 skip=32808 count=32 2>/dev/null | tr -d ' ')
    [[ -n $ISO_LABEL ]] || die 'could not read Arch ISO volume label'
    args+=(
      -kernel "$BOOT_DIR/arch/boot/x86_64/vmlinuz-linux"
      -initrd "$BOOT_DIR/arch/boot/x86_64/initramfs-linux.img"
      -append "archisobasedir=arch archisolabel=$ISO_LABEL cow_spacesize=2G console=tty0 console=ttyS0,115200n8"
      -nographic
    )
  fi
fi

printf 'Starting QEMU. Persistent disk: %s\n' "$DISK"
printf 'SSH after setting a root password: ssh -p 60022 root@127.0.0.1\n'
exec qemu-system-x86_64 "${args[@]}"
