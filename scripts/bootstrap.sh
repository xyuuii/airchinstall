#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
RUNTIME_DIR=/run/airchinstall
NETWORK_CHECK_URL=https://archlinux.org/
PACKAGES=(
  arch-wiki-lite
  fontconfig
  kmscon
  pango
  python
  python-httpx
  python-pydantic
  python-textual
  tmux
  ttf-dejavu
  wqy-microhei
)

YES=0
MODE=bootstrap

say() { printf '[airchinstall] %s\n' "$*"; }
die() { printf '[airchinstall] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: bootstrap.sh [--yes] [--dry-run]

Installs Airchinstall into the volatile overlay of the official Arch ISO,
configures Chinese TTY rendering and required cloud AI, then starts tmux.
The first milestone refuses physical hardware.
EOF
}

print_plan() {
  printf '%s\n' \
    '1. Verify official Arch ISO and QEMU/KVM' \
    '2. Verify Live network (open iwctl when Wi-Fi needs manual setup)' \
    "3. Install official packages: ${PACKAGES[*]}" \
    '4. Configure kmscon + Pango + CJK monospace fallback' \
    '5. Read base URL, model and API Key into /run/airchinstall (mode 600)' \
    '6. Install the volatile airchinstall CLI under /run' \
    '7. Validate cloud AI; failure returns to the rescue Shell' \
    '8. Start real Bash + mentor + Wiki tmux session'
}

require_safe_context() {
  [[ $EUID -eq 0 ]] || die 'run as root inside the Arch live environment'
  [[ -d /run/archiso ]] || die 'the first milestone only supports the official Arch ISO'
  [[ -f $PROJECT_ROOT/src/airchinstall/__init__.py ]] || die 'copy the complete repository, not bootstrap.sh alone'
  command -v pacman >/dev/null || die 'pacman is required'
  command -v systemd-detect-virt >/dev/null || die 'systemd-detect-virt is required'
  local virtualization
  virtualization=$(systemd-detect-virt --vm 2>/dev/null || true)
  [[ $virtualization == qemu || $virtualization == kvm ]] || \
    die "QEMU/KVM required; detected: ${virtualization:-physical hardware}"
}

online() {
  command -v curl >/dev/null && curl -fsSI --connect-timeout 5 "$NETWORK_CHECK_URL" >/dev/null
}

ensure_network() {
  say 'Checking the Live network'
  if online; then
    say 'Network ready'
    return
  fi
  if command -v iwctl >/dev/null && command -v iw >/dev/null && iw dev 2>/dev/null | grep -q 'Interface '; then
    say 'Use iwctl to connect Wi-Fi, then exit iwctl'
    iwctl </dev/tty >/dev/tty 2>/dev/tty || true
  fi
  online || die 'network unavailable; fix it in the rescue Shell and rerun bootstrap'
}

install_runtime() {
  say "Installing ${#PACKAGES[@]} official Arch packages into the volatile Live overlay"
  df -h / /run/archiso/cowspace 2>/dev/null || true
  if (( ! YES )); then
    local reply=''
    printf 'Install the Airchinstall runtime packages now? [y/N] '
    read -r reply </dev/tty || true
    [[ $reply =~ ^[Yy]$ ]] || die 'cancelled'
  fi
  say 'Waiting for the official Arch package keyring'
  if systemctl cat pacman-init.service >/dev/null 2>&1; then
    systemctl start pacman-init.service
  else
    pacman-key --init
  fi
  pacman-key --populate archlinux
  # This is an ephemeral ArchISO overlay, not an installed system. A full
  # upgrade pulls every firmware package and commonly exhausts cowspace.
  pacman -Sy --needed --noconfirm archlinux-keyring
  pacman -S --needed --noconfirm "${PACKAGES[@]}" || \
    die 'package installation failed; check network and ArchISO cowspace'
}

configure_kmscon() {
  say 'Configuring kmscon CJK rendering'
  install -d -m 0755 /etc/kmscon
  cat > /etc/kmscon/kmscon.conf <<'EOF'
font-engine=pango
font-name=DejaVu Sans Mono, WenQuanYi Micro Hei Mono
font-size=16
term=kmscon
no-reset-env
dpms-timeout=0
EOF
  fc-match 'WenQuanYi Micro Hei Mono' | grep -qi WenQuanYi || die 'CJK font lookup failed'
}

read_required() {
  local variable_name=$1 prompt=$2 hidden=${3:-0} value=''
  while [[ -z $value ]]; do
    printf '%s' "$prompt"
    if (( hidden )); then
      read -rs value </dev/tty || true
      printf '\n'
    else
      read -r value </dev/tty || true
    fi
  done
  printf -v "$variable_name" '%s' "$value"
}

configure_ai() {
  say 'Configuring required OpenAI-compatible cloud AI for this boot only'
  install -d -m 0700 "$RUNTIME_DIR"
  local base_url='' model='' api_key='' input=''
  stty -echo </dev/tty
  trap 'stty echo </dev/tty' EXIT
  trap 'exit 130' INT TERM
  printf 'Base URL [https://api.openai.com/v1]: '
  read -r input </dev/tty || true
  printf '\n'
  base_url=${input:-https://api.openai.com/v1}
  read_required model 'Model: ' 1
  read_required api_key 'API Key: ' 1
  stty echo </dev/tty
  trap - INT TERM EXIT
  printf 'Base URL: %s\nModel: %s\n' "$base_url" "$model"
  printf '%s' "$base_url" > "$RUNTIME_DIR/ai-base-url"
  printf '%s' "$model" > "$RUNTIME_DIR/ai-model"
  printf '%s' "$api_key" > "$RUNTIME_DIR/ai-key"
  chmod 0600 "$RUNTIME_DIR"/ai-*
  api_key=''
}

install_cli() {
  local launcher=$RUNTIME_DIR/bin/airchinstall python_bin
  python_bin=$(command -v python)
  install -d -m 0700 "$RUNTIME_DIR/bin"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'export PYTHONPATH=%q\n' "$PROJECT_ROOT/src"
    printf 'exec %q -m airchinstall "$@"\n' "$python_bin"
  } > "$launcher"
  chmod 0700 "$launcher"
}

launch() {
  export AIRCHINSTALL_RUNTIME_DIR=$RUNTIME_DIR
  export PATH=$RUNTIME_DIR/bin:$PATH
  export LANG=C.UTF-8
  local current_tty
  current_tty=$(tty 2>/dev/null || true)
  if [[ -n ${SSH_TTY:-} || $current_tty == /dev/ttyS* ]]; then
    say 'SSH/serial terminal detected; using its Unicode renderer'
    exec "$RUNTIME_DIR/bin/airchinstall" start
  fi
  say 'Starting Chinese kmscon on tty2; return with Ctrl+Alt+F1'
  systemctl stop getty@tty2.service >/dev/null 2>&1 || true
  if ! kmscon --no-reset-env --vt=2 --switchvt --oneshot --login -- \
    "$RUNTIME_DIR/bin/airchinstall" start; then
    say 'kmscon failed; returning to the rescue Shell'
  fi
}

while (($#)); do
  case $1 in
    --yes) YES=1 ;;
    --dry-run) MODE=dry-run ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

if [[ $MODE == dry-run ]]; then
  print_plan
  exit 0
fi

require_safe_context
ensure_network
install_runtime
configure_kmscon
configure_ai
install_cli
launch
