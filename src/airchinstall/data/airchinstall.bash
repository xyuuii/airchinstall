# Airchinstall Bash adapter. This file is sourced as the rcfile of a dedicated
# interactive Bash pane; it does not modify the user's installed system.

: "${AIRCHINSTALL_RUNTIME_DIR:=/run/airchinstall}"
: "${AIRCHINSTALL_SOCKET:=$AIRCHINSTALL_RUNTIME_DIR/session.sock}"
: "${AIRCHINSTALL_PYTHON:=python3}"

mkdir -p "$AIRCHINSTALL_RUNTIME_DIR"
chmod 700 "$AIRCHINSTALL_RUNTIME_DIR"

_AIR_FIFO="$AIRCHINSTALL_RUNTIME_DIR/shell-$$.fifo"
rm -f "$_AIR_FIFO"
mkfifo -m 600 "$_AIR_FIFO"
"$AIRCHINSTALL_PYTHON" -m airchinstall.shell_bridge events --socket "$AIRCHINSTALL_SOCKET" <"$_AIR_FIFO" &
_AIR_BRIDGE_PID=$!
exec 9>"$_AIR_FIFO"

_AIR_AT_PROMPT=0
_AIR_COMMAND_ID=

_air_b64() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

_air_emit_started() {
  printf 'started\t%s\t%s\t%s\n' "$1" "$(_air_b64 "$2")" "$(_air_b64 "$PWD")" >&9
}

_air_emit_finished() {
  printf 'finished\t%s\t%s\n' "$1" "$2" >&9
}

_air_preexec() {
  [[ $_AIR_AT_PROMPT == 1 ]] || return 0
  _AIR_AT_PROMPT=0
  local command
  command=$(history 1 | sed 's/^ *[0-9][0-9]* *//')
  [[ -n $command ]] || return 0
  _AIR_COMMAND_ID="$$-$SECONDS-$RANDOM"
  _air_emit_started "$_AIR_COMMAND_ID" "$command"
}

_air_precmd() {
  local exit_code=$?
  if [[ -n $_AIR_COMMAND_ID ]]; then
    _air_emit_finished "$_AIR_COMMAND_ID" "$exit_code"
    _AIR_COMMAND_ID=
  fi
  _AIR_AT_PROMPT=1
  return "$exit_code"
}

_air_cleanup() {
  _AIR_AT_PROMPT=0
  exec 9>&-
  kill "$_AIR_BRIDGE_PID" 2>/dev/null || true
  rm -f "$_AIR_FIFO"
}

HISTCONTROL=
HISTFILE=/dev/null
trap '_air_preexec' DEBUG
trap '_air_cleanup' EXIT
PROMPT_COMMAND=_air_precmd
PS1='[airchinstall \w]# '
