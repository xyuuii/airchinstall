from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path


class SessionClient:
    def __init__(self, socket_path: Path):
        self._socket_path = socket_path

    async def snapshots(self) -> AsyncIterator[dict[str, object]]:
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
                try:
                    while line := await reader.readline():
                        message = json.loads(line)
                        if message.get("type") == "snapshot":
                            yield message["payload"]
                finally:
                    writer.close()
                    await writer.wait_closed()
            except (FileNotFoundError, ConnectionRefusedError, ConnectionResetError):
                await asyncio.sleep(0.2)

    async def send(self, message_type: str, payload: dict[str, object]) -> dict[str, object]:
        reader, writer = await asyncio.open_unix_connection(self._socket_path)
        try:
            await reader.readline()  # initial snapshot
            message = {"v": 1, "type": message_type, "payload": payload}
            writer.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
            await writer.drain()
            response = json.loads(await reader.readline())
            if response.get("type") == "error":
                raise ValueError(response["payload"]["message"])
            return response["payload"]
        finally:
            writer.close()
            await writer.wait_closed()
