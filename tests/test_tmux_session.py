import json
import os
import socket
import subprocess
import time
from pathlib import Path

from airchinstall.app import create_tmux_session
from airchinstall.runtime import session_socket_path


def test_tmux_session_starts_real_bash_daemon_and_two_textual_clients(tmp_path, monkeypatch):
    session_name = f"airchinstall-test-{os.getpid()}"
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[1] / "src"))
    for name, value in {
        "ai-base-url": "https://example.invalid/v1",
        "ai-model": "test-model",
        "ai-key": "test-key",
    }.items():
        file = tmp_path / name
        file.write_text(value)
        file.chmod(0o600)

    try:
        create_tmux_session(tmp_path, session_name=session_name, columns=120, lines=30)
        windows = subprocess.run(
            [
                "tmux",
                "list-windows",
                "-t",
                session_name,
                "-F",
                "#{window_name}:#{window_panes}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        commands = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-s",
                "-t",
                session_name,
                "-F",
                "#{pane_current_command}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        size = subprocess.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                f"{session_name}:install",
                "#{window_width}x#{window_height}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        assert windows == ["daemon:1", "install:3"]
        assert size == "120x30"
        assert "bash" in commands
        assert sum(command.casefold().startswith("python") for command in commands) >= 3

        time.sleep(0.3)
        subprocess.run(
            [
                "tmux",
                "send-keys",
                "-t",
                f"{session_name}:install.0",
                "printf 'hello-tmux\\n'",
                "Enter",
            ],
            check=True,
        )
        time.sleep(0.4)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(session_socket_path(tmp_path)))
            snapshot = json.loads(client.makefile().readline())["payload"]
        assert snapshot["last_observation"]["command"] == "printf 'hello-tmux\\n'"
        assert "hello-tmux" in snapshot["last_observation"]["output_excerpt"]
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)
