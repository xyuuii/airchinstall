from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from .ai import TutorProvider, TutorRequest, TutorUnavailable
from .catalog import OperationCatalog
from .domain import AssistantSession, Observation
from .probes import ProbeRegistry, ProbeUnavailable
from .runtime import session_socket_path
from .security import redact_text, safe_excerpt, sanitize_data

PROTOCOL_VERSION = 1


class SessionDaemon:
    """Owns one Assistant Session and publishes snapshots over a Unix socket."""

    def __init__(
        self,
        *,
        catalog: OperationCatalog,
        probes: ProbeRegistry,
        tutor: TutorProvider,
        runtime_dir: Path,
    ):
        self._catalog = catalog
        self._probes = probes
        self._probes.require_registered(operation.probe for operation in catalog.operations)
        self._tutor = tutor
        self._runtime_dir = runtime_dir
        self._session = AssistantSession(catalog)
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._active_command: dict[str, str] | None = None
        self._active_output = ""
        self._pending_output = ""
        self._ai_status = "unknown"
        self._probe_error: str | None = None
        self._revision = 0
        self.socket_path = session_socket_path(runtime_dir)
        self._transcript_path = runtime_dir / "transcript.jsonl"

    async def start(self) -> SessionDaemon:
        self._runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._runtime_dir.chmod(0o700)
        self.socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)
        self.socket_path.chmod(0o600)
        return self

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in tuple(self._clients):
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        self.socket_path.unlink(missing_ok=True)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._clients.add(writer)
        await self._send(writer, self._snapshot_message())
        try:
            while line := await reader.readline():
                try:
                    message = json.loads(line)
                    await self._apply(message)
                    await self._broadcast(self._snapshot_message())
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    await self._send(
                        writer,
                        {
                            "v": PROTOCOL_VERSION,
                            "type": "error",
                            "payload": {"message": str(error)},
                        },
                    )
                    await self._broadcast(self._snapshot_message())
        finally:
            self._clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def _apply(self, message: dict[str, object]) -> None:
        if message.get("v") != PROTOCOL_VERSION:
            raise ValueError("unsupported protocol version")
        message_type = message["type"]
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise TypeError("payload must be an object")

        if message_type == "goal.set":
            self._session.set_goal(safe_excerpt(str(payload["text"])))
            self._revision += 1
            await self._refresh_advice()
            return
        if message_type == "observation":
            observation = Observation.model_validate(payload)
            await self._apply_observation(observation)
            return
        if message_type == "command.started":
            if self._active_command is not None:
                raise ValueError("a command is already active")
            self._active_command = {
                "command_id": str(payload["command_id"]),
                "command": safe_excerpt(str(payload["command"]), limit=8192),
                "cwd": safe_excerpt(str(payload["cwd"]), limit=1024),
            }
            # ponytail: pipe-pane can beat the preexec socket for very fast
            # commands. Keep a small pre-start tail; replace with explicit PTY
            # sequence markers if prompt noise becomes material.
            self._active_output = self._pending_output
            self._pending_output = ""
            self._revision += 1
            return
        if message_type == "output.chunk":
            command_id = str(payload.get("command_id", ""))
            if self._active_command is None:
                self._pending_output = safe_excerpt(
                    self._pending_output + str(payload["text"]),
                    limit=8192,
                )
                return
            if command_id and self._active_command["command_id"] != command_id:
                raise ValueError(f"no active command: {command_id}")
            self._active_output = safe_excerpt(
                self._active_output + str(payload["text"]),
                limit=65536,
            )
            return
        if message_type == "command.finished":
            active = self._require_active(str(payload["command_id"]))
            # ponytail: pipe-pane and Bash hooks use separate sockets; a short grace
            # window keeps trailing output. Add per-command output sequence IDs if
            # high-volume commands prove this insufficient.
            await asyncio.sleep(0.05)
            observation = Observation(
                command_id=active["command_id"],
                command=active["command"],
                cwd=active["cwd"],
                exit_code=int(payload["exit_code"]),
                output_excerpt=safe_excerpt(self._active_output),
            )
            self._active_command = None
            self._active_output = ""
            await self._apply_observation(observation)
            return
        if message_type == "ping":
            return
        raise ValueError(f"unsupported message type: {message_type}")

    async def _apply_observation(self, observation: Observation) -> None:
        observation = observation.model_copy(
            update={
                "command": safe_excerpt(observation.command, limit=8192),
                "cwd": safe_excerpt(observation.cwd, limit=1024),
                "output_excerpt": safe_excerpt(observation.output_excerpt),
            }
        )
        operation = self._catalog.recognize(observation.command)
        facts = []
        if operation is not None and observation.exit_code == 0:
            try:
                facts = self._probes.collect(operation.probe)
                facts = [
                    fact.model_copy(update={"value": sanitize_data(fact.value)}) for fact in facts
                ]
                self._probe_error = None
            except ProbeUnavailable as error:
                self._probe_error = error.probe_name
        self._session.observe(observation, facts)
        self._revision += 1
        self._append_transcript(observation)
        if self._session.snapshot().goal is not None:
            await self._refresh_advice()

    def _require_active(self, command_id: str) -> dict[str, str]:
        if self._active_command is None or self._active_command["command_id"] != command_id:
            raise ValueError(f"no active command: {command_id}")
        return self._active_command

    async def _refresh_advice(self) -> None:
        revision = self._revision
        snapshot = self._session.snapshot()
        goal = snapshot.goal
        if goal is None:
            return
        request = TutorRequest(
            goal=goal.text,
            facts=snapshot.facts,
            last_observation=(
                {
                    "command": snapshot.last_observation.command,
                    "exit_code": snapshot.last_observation.exit_code,
                }
                if snapshot.last_observation
                else None
            ),
            available_operation_ids=tuple(
                operation.id for operation in self._session.available_operations()
            ),
        )
        try:
            advice = await self._tutor.advise(request)
        except TutorUnavailable:
            if revision != self._revision:
                return
            self._ai_status = "error"
            raise ValueError("cloud AI unavailable") from None
        if revision != self._revision:
            return
        self._ai_status = "ready"
        self._session.apply_advice(advice)

    def _append_transcript(self, observation: Observation) -> None:
        record = observation.model_dump(mode="json")
        record["command"] = redact_text(observation.command)
        record["output_excerpt"] = safe_excerpt(observation.output_excerpt)
        descriptor = os.open(
            self._transcript_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        with os.fdopen(descriptor, "a") as transcript:
            transcript.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _snapshot_message(self) -> dict[str, object]:
        payload = self._session.snapshot().model_dump(mode="json")
        payload["ai_status"] = self._ai_status
        payload["probe_error"] = self._probe_error
        payload["active_command"] = dict(self._active_command) if self._active_command else None
        if self._active_command:
            payload["active_command"]["output_excerpt"] = safe_excerpt(self._active_output)
        return {
            "v": PROTOCOL_VERSION,
            "type": "snapshot",
            "payload": payload,
        }

    async def _broadcast(self, message: dict[str, object]) -> None:
        for writer in tuple(self._clients):
            try:
                await self._send(writer, message)
            except (BrokenPipeError, ConnectionResetError):
                self._clients.discard(writer)

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, message: dict[str, object]) -> None:
        writer.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
        await writer.drain()
