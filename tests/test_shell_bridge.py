import asyncio
import base64
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

from airchinstall.catalog import OperationCatalog
from airchinstall.daemon import SessionDaemon
from airchinstall.domain import Advice, Fact
from airchinstall.probes import ProbeRegistry
from airchinstall.shell_bridge import parse_event_line


def encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def test_started_event_is_decoded_and_redacted_before_socket():
    message = parse_event_line(
        f"started\tcmd-7\t{encoded('OPENAI_API_KEY=sk-secret')}\t{encoded('/root')}"
    )

    assert message == {
        "v": 1,
        "type": "command.started",
        "payload": {"command_id": "cmd-7", "command": "[REDACTED]", "cwd": "/root"},
    }


def test_finished_event_preserves_only_id_and_exit_code():
    message = parse_event_line("finished\tcmd-7\t23")

    assert message == {
        "v": 1,
        "type": "command.finished",
        "payload": {"command_id": "cmd-7", "exit_code": 23},
    }


class UnusedTutor:
    async def advise(self, _request):
        return Advice(summary="unused")


def read_until(file_descriptor: int, marker: bytes, timeout: float = 5) -> bytes:
    deadline = time.monotonic() + timeout
    output = b""
    while marker not in output and time.monotonic() < deadline:
        ready, _, _ = select.select([file_descriptor], [], [], 0.1)
        if ready:
            output += os.read(file_descriptor, 4096)
    if marker not in output:
        raise AssertionError(f"did not see prompt; output={output!r}")
    return output


@pytest.mark.asyncio
async def test_real_interactive_bash_emits_one_completed_observation(tmp_path):
    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=ProbeRegistry(
            {
                "uefi": lambda: [Fact(key="boot.uefi", value=False, source="uefi")],
                "network": lambda: [Fact(key="network.online", value=True, source="network")],
                "disks": lambda: [Fact(key="disks.inventory", value=[], source="disks")],
            }
        ),
        tutor=UnusedTutor(),
        runtime_dir=tmp_path,
    )
    await daemon.start()
    master, slave = os.openpty()
    environment = os.environ.copy()
    environment.update(
        {
            "AIRCHINSTALL_RUNTIME_DIR": str(tmp_path),
            "AIRCHINSTALL_SOCKET": str(daemon.socket_path),
            "AIRCHINSTALL_PYTHON": sys.executable,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        }
    )
    shell_rc = Path(__file__).parents[1] / "src" / "airchinstall" / "data" / "airchinstall.bash"
    process = subprocess.Popen(  # noqa: ASYNC220 - PTY lifecycle is the behavior under test
        ["bash", "--noprofile", "--rcfile", str(shell_rc), "-i"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
        close_fds=True,
    )
    os.close(slave)
    try:
        await asyncio.to_thread(read_until, master, b"[airchinstall")
        os.write(master, b"printf 'hello-hook\\n'\n")
        await asyncio.to_thread(read_until, master, b"[airchinstall")
        await asyncio.sleep(0.2)

        reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
        snapshot = json.loads(await reader.readline())["payload"]
        assert snapshot["last_observation"]["command"] == "printf 'hello-hook\\n'"
        assert snapshot["last_observation"]["exit_code"] == 0
        writer.close()
        await writer.wait_closed()
    finally:
        os.write(master, b"exit\n")
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
        os.close(master)
        await daemon.close()

    assert not (tmp_path / "bash-history").exists()
