import asyncio
import json

import pytest

from airchinstall.ai import TutorRequest, TutorUnavailable
from airchinstall.catalog import OperationCatalog
from airchinstall.daemon import SessionDaemon
from airchinstall.domain import Advice, AdviceOption, Fact
from airchinstall.probes import ProbeRegistry


class FakeTutor:
    async def advise(self, request: TutorRequest) -> Advice:
        operation_id = request.available_operation_ids[0]
        return Advice(
            summary="根据当前事实给出选项。",
            options=(AdviceOption(operation_id=operation_id, rationale="可信目录操作"),),
        )


class FailingTutor:
    async def advise(self, _request: TutorRequest) -> Advice:
        raise TutorUnavailable("provider is down and may include sensitive details")


class CapturingTutor(FakeTutor):
    def __init__(self):
        self.requests = []

    async def advise(self, request: TutorRequest) -> Advice:
        self.requests.append(request)
        return await super().advise(request)


class RacingTutor:
    def __init__(self):
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def advise(self, request: TutorRequest) -> Advice:
        if request.goal == "first goal":
            self.first_started.set()
            await self.release_first.wait()
        return Advice(
            summary=request.goal,
            options=(
                AdviceOption(
                    operation_id=request.available_operation_ids[0],
                    rationale="current goal",
                ),
            ),
        )


async def read_message(reader: asyncio.StreamReader):
    return json.loads(await asyncio.wait_for(reader.readline(), timeout=1))


async def send_message(writer: asyncio.StreamWriter, message: dict):
    writer.write((json.dumps(message) + "\n").encode())
    await writer.drain()


@pytest.mark.asyncio
async def test_socket_clients_receive_snapshots_and_reconnect_to_current_state(
    tmp_path,
):
    probes = ProbeRegistry(
        {
            "uefi": lambda: [Fact(key="boot.uefi", value=True, source="uefi")],
            "network": lambda: [Fact(key="network.online", value=True, source="network")],
            "disks": lambda: [Fact(key="disks.inventory", value=["/dev/vda"], source="disks")],
        }
    )
    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=probes,
        tutor=FakeTutor(),
        runtime_dir=tmp_path,
    )
    await daemon.start()
    try:
        reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
        initial = await read_message(reader)
        assert initial["type"] == "snapshot"
        assert initial["payload"]["facts"] == {}

        await send_message(
            writer,
            {"v": 1, "type": "goal.set", "payload": {"text": "我想先了解当前环境"}},
        )
        goal_snapshot = await read_message(reader)
        assert goal_snapshot["payload"]["goal"]["text"] == "我想先了解当前环境"
        assert goal_snapshot["payload"]["advice"]["options"][0]["operation_id"] == "inspect-uefi"

        await send_message(
            writer,
            {
                "v": 1,
                "type": "observation",
                "payload": {
                    "command_id": "cmd-1",
                    "command": "ping -c 3 ping.archlinux.org",
                    "cwd": "/root",
                    "exit_code": 0,
                },
            },
        )
        observed = await read_message(reader)
        assert observed["payload"]["facts"] == {"network.online": True}
        writer.close()
        await writer.wait_closed()

        reader2, writer2 = await asyncio.open_unix_connection(daemon.socket_path)
        reconnected = await read_message(reader2)
        assert reconnected["payload"]["facts"] == {"network.online": True}
        assert reconnected["payload"]["goal"]["text"] == "我想先了解当前环境"
        writer2.close()
        await writer2.wait_closed()
    finally:
        await daemon.close()


@pytest.mark.asyncio
async def test_command_lifecycle_builds_one_redacted_observation(tmp_path):
    probes = ProbeRegistry(
        {
            "uefi": lambda: [Fact(key="boot.uefi", value=True, source="uefi")],
            "network": lambda: [Fact(key="network.online", value=True, source="network")],
            "disks": lambda: [Fact(key="disks.inventory", value=["/dev/vda"], source="disks")],
        }
    )
    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=probes,
        tutor=FakeTutor(),
        runtime_dir=tmp_path,
    )
    await daemon.start()
    try:
        reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
        await read_message(reader)

        await send_message(
            writer,
            {
                "v": 1,
                "type": "command.started",
                "payload": {
                    "command_id": "cmd-2",
                    "command": "ls /sys/firmware/efi/efivars",
                    "cwd": "/root",
                },
            },
        )
        started = await read_message(reader)
        assert started["payload"]["active_command"]["command_id"] == "cmd-2"

        await send_message(
            writer,
            {
                "v": 1,
                "type": "output.chunk",
                "payload": {
                    "command_id": "cmd-2",
                    "text": "\u001b[31mEFI\u001b[0m OPENAI_API_KEY=sk-never-log-this",
                },
            },
        )
        await read_message(reader)

        await send_message(
            writer,
            {
                "v": 1,
                "type": "command.finished",
                "payload": {"command_id": "cmd-2", "exit_code": 0},
            },
        )
        finished = await read_message(reader)
        assert finished["payload"]["facts"] == {"boot.uefi": True}
        assert finished["payload"]["active_command"] is None
        transcript = (tmp_path / "transcript.jsonl").read_text()
        assert "sk-never-log-this" not in transcript
        assert "\\u001b" not in transcript
    finally:
        writer.close()
        await writer.wait_closed()
        await daemon.close()


@pytest.mark.asyncio
async def test_ai_failure_is_reported_without_killing_rescue_shell_state(tmp_path):
    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=ProbeRegistry(
            {
                "uefi": list,
                "network": list,
                "disks": lambda: [
                    Fact(
                        key="disks.inventory",
                        value=[{"model": "API Key: fact-secret-value"}],
                        source="disks",
                    )
                ],
            }
        ),
        tutor=FailingTutor(),
        runtime_dir=tmp_path,
    )
    await daemon.start()
    try:
        reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
        await read_message(reader)
        await send_message(
            writer,
            {"v": 1, "type": "goal.set", "payload": {"text": "配置网络"}},
        )
        error = await read_message(reader)
        assert error == {
            "v": 1,
            "type": "error",
            "payload": {"message": "cloud AI unavailable"},
        }
        writer.close()
        await writer.wait_closed()

        reader2, writer2 = await asyncio.open_unix_connection(daemon.socket_path)
        snapshot = await read_message(reader2)
        assert snapshot["payload"]["goal"]["text"] == "配置网络"
        assert snapshot["payload"]["ai_status"] == "error"
        writer2.close()
        await writer2.wait_closed()
    finally:
        await daemon.close()


@pytest.mark.asyncio
async def test_probe_failure_does_not_claim_a_fact_or_kill_daemon(tmp_path):
    def failed_probe():
        raise OSError("lsblk disappeared")

    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=ProbeRegistry({"uefi": list, "network": list, "disks": failed_probe}),
        tutor=FakeTutor(),
        runtime_dir=tmp_path,
    )
    await daemon.start()
    try:
        reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
        await read_message(reader)
        await send_message(
            writer,
            {
                "v": 1,
                "type": "observation",
                "payload": {
                    "command_id": "cmd-probe",
                    "command": "lsblk -J",
                    "cwd": "/root",
                    "exit_code": 0,
                },
            },
        )
        snapshot = await read_message(reader)
        assert snapshot["payload"]["facts"] == {}
        assert snapshot["payload"]["probe_error"] == "disks"
        writer.close()
        await writer.wait_closed()
    finally:
        await daemon.close()


@pytest.mark.asyncio
async def test_daemon_redacts_every_protocol_entry_before_snapshot_log_or_ai(tmp_path):
    tutor = CapturingTutor()
    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=ProbeRegistry(
            {
                "uefi": list,
                "network": list,
                "disks": lambda: [
                    Fact(
                        key="disks.inventory",
                        value=[{"model": "API Key: fact-secret-value"}],
                        source="disks",
                    )
                ],
            }
        ),
        tutor=tutor,
        runtime_dir=tmp_path,
    )
    await daemon.start()
    try:
        reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
        await read_message(reader)
        await send_message(
            writer,
            {
                "v": 1,
                "type": "goal.set",
                "payload": {"text": "help API Key: goal-secret-value"},
            },
        )
        await read_message(reader)
        await send_message(
            writer,
            {
                "v": 1,
                "type": "observation",
                "payload": {
                    "command_id": "cmd-secret",
                    "command": "echo OPENAI_API_KEY=command-secret-value",
                    "cwd": "/tmp/sk-cwd-secret-value",
                    "exit_code": 0,
                    "output_excerpt": "API Key: output-secret-value",
                },
            },
        )
        await read_message(reader)
        await send_message(
            writer,
            {
                "v": 1,
                "type": "observation",
                "payload": {
                    "command_id": "cmd-fact",
                    "command": "lsblk -J",
                    "cwd": "/root",
                    "exit_code": 0,
                },
            },
        )
        snapshot = await read_message(reader)

        serialized = json.dumps(
            {
                "snapshot": snapshot,
                "requests": [request.model_dump() for request in tutor.requests],
                "transcript": (tmp_path / "transcript.jsonl").read_text(),
            }
        )
        assert "goal-secret" not in serialized
        assert "command-secret" not in serialized
        assert "cwd-secret" not in serialized
        assert "output-secret" not in serialized
        assert "fact-secret" not in serialized
    finally:
        writer.close()
        await writer.wait_closed()
        await daemon.close()


@pytest.mark.asyncio
async def test_slower_old_ai_response_cannot_replace_new_goal_advice(tmp_path):
    tutor = RacingTutor()
    daemon = SessionDaemon(
        catalog=OperationCatalog.load_default(),
        probes=ProbeRegistry({"uefi": list, "network": list, "disks": list}),
        tutor=tutor,
        runtime_dir=tmp_path,
    )

    first = asyncio.create_task(
        daemon._apply({"v": 1, "type": "goal.set", "payload": {"text": "first goal"}})
    )
    await tutor.first_started.wait()
    await daemon._apply({"v": 1, "type": "goal.set", "payload": {"text": "second goal"}})
    tutor.release_first.set()
    await first

    snapshot = daemon._snapshot_message()["payload"]
    assert snapshot["goal"]["text"] == "second goal"
    assert snapshot["advice"]["summary"] == "second goal"
