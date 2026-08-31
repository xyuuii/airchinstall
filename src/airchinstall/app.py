from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from .ai import OpenAICompatibleTutor, TutorRequest, TutorUnavailable
from .catalog import OperationCatalog
from .daemon import SessionDaemon
from .probes import system_probe_registry
from .runtime import session_socket_path
from .security import redact_text
from .ui import MentorApp, WikiApp, layout_mode

SESSION_NAME = "airchinstall"


def runtime_dir() -> Path:
    return Path(os.environ.get("AIRCHINSTALL_RUNTIME_DIR", "/run/airchinstall"))


def _config_value(runtime: Path, name: str) -> str:
    value = (runtime / name).read_text().strip()
    if not value:
        raise ValueError(f"missing runtime configuration: {name}")
    return value


def _tutor(runtime: Path, catalog: OperationCatalog) -> OpenAICompatibleTutor:
    return OpenAICompatibleTutor(
        base_url=_config_value(runtime, "ai-base-url"),
        model=_config_value(runtime, "ai-model"),
        key_file=runtime / "ai-key",
        catalog=catalog,
    )


def export_transcript(runtime: Path, destination: Path) -> None:
    source = runtime / "transcript.jsonl"
    if not source.is_file():
        raise FileNotFoundError(f"transcript not found: {source}")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with source.open() as input_file, os.fdopen(descriptor, "w") as output_file:
        for line in input_file:
            output_file.write(redact_text(line))
    destination.chmod(0o600)


async def _run_daemon(runtime: Path) -> None:
    catalog = OperationCatalog.load_default()
    daemon = SessionDaemon(
        catalog=catalog,
        probes=system_probe_registry(),
        tutor=_tutor(runtime, catalog),
        runtime_dir=runtime,
    )
    await daemon.start()
    try:
        await daemon.serve_forever()
    finally:
        await daemon.close()


async def _doctor(runtime: Path) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    linux = sys.platform.startswith("linux")
    checks.append(("Linux", linux, sys.platform))

    arch_live = Path("/run/archiso").is_dir()
    checks.append(("Arch Live environment", arch_live, "/run/archiso"))

    virtualization = "unknown"
    if shutil.which("systemd-detect-virt"):
        detected = await asyncio.to_thread(
            subprocess.run,
            ["systemd-detect-virt", "--vm"],
            capture_output=True,
            text=True,
            check=False,
        )
        virtualization = detected.stdout.strip() or "physical"
    checks.append(("QEMU/KVM", virtualization in {"qemu", "kvm"}, virtualization))

    for command in ("bash", "tmux", "kmscon", "fc-match", "wiki-search"):
        location = shutil.which(command)
        checks.append((command, location is not None, location or "missing"))

    key_file = runtime / "ai-key"
    key_mode = stat.S_IMODE(key_file.stat().st_mode) if key_file.exists() else 0
    checks.append(("AI key mode", key_file.is_file() and key_mode == 0o600, oct(key_mode)))
    try:
        catalog = OperationCatalog.load_default()
        tutor = _tutor(runtime, catalog)
        await tutor.advise(
            TutorRequest(
                goal="验证 Airchinstall 云端 AI 连接",
                facts={},
                available_operation_ids=tuple(operation.id for operation in catalog.operations),
            )
        )
        checks.append(("Cloud AI", True, "ready"))
    except (OSError, TutorUnavailable, ValueError) as error:
        checks.append(("Cloud AI", False, type(error).__name__))
    return checks


def _command(*parts: str) -> str:
    return shlex.join(parts)


def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", *args], check=check, text=True, capture_output=True)


def _wait_for_socket(socket_path: Path, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        time.sleep(0.05)
    raise RuntimeError("Airchinstall daemon did not create its socket")


def _process_command(runtime: Path, *parts: str) -> str:
    environment = [
        "env",
        f"AIRCHINSTALL_RUNTIME_DIR={runtime}",
        f"AIRCHINSTALL_SOCKET={session_socket_path(runtime)}",
        f"AIRCHINSTALL_PYTHON={sys.executable}",
    ]
    if python_path := os.environ.get("PYTHONPATH"):
        environment.append(f"PYTHONPATH={python_path}")
    return _command(*environment, *parts)


def create_tmux_session(
    runtime: Path,
    *,
    session_name: str = SESSION_NAME,
    columns: int | None = None,
    lines: int | None = None,
) -> None:
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    socket_path = session_socket_path(runtime)
    _config_value(runtime, "ai-base-url")
    _config_value(runtime, "ai-model")
    if not (runtime / "ai-key").is_file():
        raise ValueError("missing runtime configuration: ai-key")

    terminal = shutil.get_terminal_size((120, 30))
    terminal_columns = columns if columns is not None else terminal.columns
    terminal_lines = lines if lines is not None else terminal.lines

    if _tmux("has-session", "-t", session_name, check=False).returncode != 0:
        python = sys.executable
        daemon_command = _process_command(runtime, python, "-m", "airchinstall.app", "_daemon")
        shell_rc = Path(__file__).parent / "data" / "airchinstall.bash"
        shell_command = _process_command(
            runtime, "bash", "--noprofile", "--rcfile", str(shell_rc), "-i"
        )
        mentor_command = _process_command(runtime, python, "-m", "airchinstall.app", "_mentor")
        wiki_command = _process_command(runtime, python, "-m", "airchinstall.app", "_wiki")
        output_command = _process_command(
            runtime,
            python,
            "-m",
            "airchinstall.shell_bridge",
            "output",
            "--socket",
            str(socket_path),
        )

        _tmux(
            "new-session",
            "-d",
            "-x",
            str(terminal_columns),
            "-y",
            str(terminal_lines),
            "-s",
            session_name,
            "-n",
            "daemon",
            daemon_command,
        )
        try:
            _wait_for_socket(socket_path)
        except Exception:
            _tmux("kill-session", "-t", session_name, check=False)
            raise
        _tmux("new-window", "-d", "-t", session_name, "-n", "install", shell_command)
        _tmux(
            "split-window",
            "-h",
            "-p",
            "36",
            "-t",
            f"{session_name}:install.0",
            mentor_command,
        )

        if layout_mode(columns=terminal_columns, lines=terminal_lines) == "three-pane":
            _tmux(
                "split-window",
                "-v",
                "-p",
                "44",
                "-t",
                f"{session_name}:install.1",
                wiki_command,
            )
        else:
            _tmux("new-window", "-d", "-t", session_name, "-n", "wiki", wiki_command)
        _tmux("pipe-pane", "-o", "-t", f"{session_name}:install.0", output_command)
        _tmux("set-option", "-t", session_name, "mouse", "on")
        _tmux("set-option", "-t", session_name, "status", "off")
        _tmux("select-window", "-t", f"{session_name}:install")
        _tmux("select-pane", "-t", f"{session_name}:install.0")


def _print_checks(checks: list[tuple[str, bool, str]]) -> None:
    for name, passed, detail in checks:
        print(f"[{'OK' if passed else 'FAIL'}] {name}: {detail}")


def start_session(runtime: Path) -> None:
    checks = asyncio.run(_doctor(runtime))
    _print_checks(checks)
    if not all(passed for _, passed, _ in checks):
        print("Assistant mode unavailable; ordinary Arch rescue Shell remains active.")
        raise SystemExit(1)
    create_tmux_session(runtime)

    if os.environ.get("TMUX"):
        os.execvp("tmux", ["tmux", "switch-client", "-t", SESSION_NAME])
    os.execvp("tmux", ["tmux", "attach-session", "-t", SESSION_NAME])


def _public_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dynamic Arch Linux TTY companion")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start", help="start the tmux assistant session")
    subparsers.add_parser("doctor", help="check the Live environment and required cloud AI")
    export = subparsers.add_parser("export-transcript", help="export a redacted JSONL transcript")
    export.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    internal = arguments[0] if arguments else ""
    runtime = runtime_dir()
    if internal == "_daemon":
        asyncio.run(_run_daemon(runtime))
        return
    if internal == "_mentor":
        MentorApp(session_socket_path(runtime), OperationCatalog.load_default()).run()
        return
    if internal == "_wiki":
        WikiApp(session_socket_path(runtime), OperationCatalog.load_default()).run()
        return

    args = _public_parser().parse_args(arguments)
    if args.command in (None, "start"):
        start_session(runtime)
        return
    if args.command == "doctor":
        checks = asyncio.run(_doctor(runtime))
        _print_checks(checks)
        if not all(passed for _, passed, _ in checks):
            raise SystemExit(1)
        return
    if args.command == "export-transcript":
        export_transcript(runtime, args.path)
        print(args.path)


if __name__ == "__main__":
    main()
