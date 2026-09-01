#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
STATE_DIR=$PROJECT_DIR/.parallels
VM_NAME=airchinstall-arm
ARCHBOOT_SIGNING_FINGERPRINT=5B7E3FB71B7F10329A1C03AB771DF6627EDF681F
ARCHBOOT_KEYSERVER=hkps://keyserver.ubuntu.com
ISO=''
DRY_RUN=0
GPG_HOME=''

die() { printf 'parallels-arm-mvp: %s\n' "$*" >&2; exit 1; }

cleanup() {
  [[ -z $GPG_HOME ]] || rm -rf -- "$GPG_HOME"
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: parallels-arm-mvp.sh [--dry-run] /path/to/archboot-aarch64.iso

Creates an Apple Silicon Parallels VM for the signed Archboot AArch64 Live ISO.
The VM has a 32 GiB virtual disk and no shared host disks, folders, clipboard,
or cloud drives. It does not start the ISO; start the VM yourself in Parallels.
EOF
}

verify_archboot_iso() {
  local fingerprint signature
  command -v gpg >/dev/null || die 'gpg is required to verify the Archboot ISO'
  signature=$ISO.sig
  [[ -f $signature ]] || die "Archboot signature not found: $signature"
  GPG_HOME=$(mktemp -d) || die 'could not create an isolated GPG directory'
  chmod 700 "$GPG_HOME"
  gpg --batch --homedir "$GPG_HOME" --keyserver "$ARCHBOOT_KEYSERVER" \
    --recv-keys "$ARCHBOOT_SIGNING_FINGERPRINT" >/dev/null || \
    die 'could not retrieve the Archboot signing key'
  fingerprint=$(gpg --batch --homedir "$GPG_HOME" --with-colons --fingerprint \
    | awk -F: '$1 == "fpr" {print $10; exit}')
  [[ $fingerprint == "$ARCHBOOT_SIGNING_FINGERPRINT" ]] || die 'unexpected Archboot signing key'
  gpg --batch --homedir "$GPG_HOME" --verify "$signature" "$ISO" >/dev/null 2>&1 || \
    die 'Archboot ISO signature verification failed'
}

while (($#)); do
  case $1 in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [[ -z $ISO ]] || die 'only one ISO path may be supplied'; ISO=$1 ;;
  esac
  shift
done

if (( DRY_RUN )); then
  printf '%s\n' \
    "State directory: $STATE_DIR" \
    "VM: $VM_NAME (Apple Silicon AArch64)" \
    'Virtual disk: 32 GiB (Parallels virtual disk)' \
    'Boot mode: UEFI ARM64 Archboot AArch64 ISO' \
    'Network: Parallels shared NAT' \
    'Host disks, folders, clipboard, and cloud drives: not shared'
  exit 0
fi

[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || \
  die 'Apple Silicon macOS is required'
command -v prlctl >/dev/null || die 'prlctl is required'
[[ -n $ISO ]] || die 'an Archboot AArch64 ISO path is required'
[[ -f $ISO ]] || die "ISO not found: $ISO"
verify_archboot_iso
if prlctl list -a -o name | sed 1d | grep -Fqx "$VM_NAME"; then
  die "VM already exists: $VM_NAME"
fi

mkdir -p "$STATE_DIR"
prlctl create "$VM_NAME" --ostype linux --distribution linux --no-hdd --dst "$STATE_DIR"
prlctl set "$VM_NAME" --isolate-vm on --shf-host off --shf-host-defined off \
  --shared-profile off --smart-mount off --shared-clipboard off --shared-cloud off
prlctl set "$VM_NAME" --sh-app-host-to-guest off --sh-app-guest-to-host off \
  --show-guest-app-folder-in-dock off --show-guest-notifications off \
  --share-host-location off --auto-share-camera off --auto-share-smart-card off
prlctl set "$VM_NAME" --cpus 4 --memsize 4096
prlctl set "$VM_NAME" --device-add hdd --size 32768 --iface sata --type expand
prlctl set "$VM_NAME" --device-set cdrom0 --image "$ISO" --connect
prlctl set "$VM_NAME" --bios-type efi-arm64 --efi-secure-boot off \
  --device-bootorder 'cdrom0 hdd0'

printf 'Created %s. Start it manually in Parallels Desktop.\n' "$VM_NAME"
