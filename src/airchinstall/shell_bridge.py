from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import time

from .security import redact_text, safe_excerpt


def parse_event_line(line: str) -> dict[str, object]:
    fields = line.rstrip("\n").split("\t")
    if fields[0] == "started" and len(fields) == 4:
        command = base64.b64decode(fields[2], validate=True).decode(errors="replace")
        cwd = base64.b64decode(fields[3], validate=True).decode(errors="replace")
        return {
            "v": 1,
            "type": "command.started",
            "payload": {
                "command_id": fields[1],
                "command": redact_text(command),
                "cwd": cwd,
            },
        }
    if fields[0] == "finished" and len(fields) == 3:
        return {
            "v": 1,
            "type": "command.finished",
            "payload": {"command_id": fields[1], "exit_code": int(fields[2])},
        }
    raise ValueError("invalid shell event")


class SocketSender:
    def __init__(self, socket_path: str):
        self._socket_path = socket_path
        self._socket: socket.socket | None = None

    def send(self, message: dict[str, object]) -> None:
        payload = (json.dumps(message, ensure_ascii=False) + "\n").encode()
        for attempt in range(20):
            try:
                if self._socket is None:
                    self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self._socket.connect(self._socket_path)
                    self._socket.recv(65536)  # initial snapshot
                self._drain_snapshots()
                self._socket.sendall(payload)
                return
            except (FileNotFoundError, ConnectionRefusedError, BrokenPipeError):
                if self._socket is not None:
                    self._socket.close()
                    self._socket = None
                if attempt == 19:
                    raise
                time.sleep(0.1)

    def _drain_snapshots(self) -> None:
        assert self._socket is not None
        self._socket.setblocking(False)
        try:
            while self._socket.recv(65536):
                pass
        except BlockingIOError:
            pass
        finally:
            self._socket.setblocking(True)


def bridge_events(sender: SocketSender) -> None:
    for line in sys.stdin:
        if line.strip():
            sender.send(parse_event_line(line))


def bridge_output(sender: SocketSender) -> None:
    while chunk := sys.stdin.buffer.read1(4096):
        sender.send(
            {
                "v": 1,
                "type": "output.chunk",
                "payload": {
                    "command_id": "",
                    "text": safe_excerpt(chunk.decode(errors="replace")),
                },
            }
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("events", "output"))
    parser.add_argument(
        "--socket",
        default=os.environ.get("AIRCHINSTALL_SOCKET", "/run/airchinstall/session.sock"),
    )
    args = parser.parse_args(argv)
    sender = SocketSender(args.socket)
    if args.mode == "events":
        bridge_events(sender)
    else:
        bridge_output(sender)


if __name__ == "__main__":
    main()
