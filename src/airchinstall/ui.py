from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.cells import cell_len, get_character_cell_size
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Resize
from textual.widgets import Input, Static

from .catalog import OperationCatalog
from .client import SessionClient
from .i18n import MESSAGES

PACMAN_DATABASE = Path("/var/lib/pacman/local")


def layout_mode(*, columns: int, lines: int) -> str:
    return "three-pane" if columns >= 120 and lines >= 30 else "compact"


def local_wiki_version(database: Path = PACMAN_DATABASE) -> str | None:
    for description in sorted(database.glob("arch-wiki-lite-*/desc"), reverse=True):
        try:
            lines = description.read_text(errors="replace").splitlines()
            marker = lines.index("%VERSION%")
            return lines[marker + 1]
        except (OSError, ValueError, IndexError):
            continue
    return None


def _wrap(text: str, width: int) -> list[str]:
    width = max(width, 1)
    lines: list[str] = []
    current: list[str] = []
    cells = 0
    for character in text:
        if character == "\n":
            lines.append("".join(current))
            current, cells = [], 0
            continue
        size = get_character_cell_size(character)
        if current and cells + size > width:
            lines.append("".join(current))
            current, cells = [], 0
        current.append(character)
        cells += size
    lines.append("".join(current))
    return lines


def _labeled(label: str, value: str, width: int) -> list[str]:
    prefix = f"{label}  "
    available = max(1, width - cell_len(prefix))
    wrapped = _wrap(value, available)
    return [
        prefix + wrapped[0],
        *(" " * cell_len(prefix) + line for line in wrapped[1:]),
    ]


def _current_operation_for_snapshot(
    snapshot: dict[str, Any],
    catalog: OperationCatalog,
):
    active = snapshot.get("active_command")
    if active and active.get("command"):
        return catalog.recognize(active["command"])
    operation_id = snapshot.get("current_operation")
    if operation_id:
        return catalog.require(operation_id)
    return None


def _operation_for_snapshot(
    snapshot: dict[str, Any],
    catalog: OperationCatalog,
):
    if operation := _current_operation_for_snapshot(snapshot, catalog):
        return operation
    advice = snapshot.get("advice") or {}
    options = advice.get("options") or []
    if options:
        return catalog.require(options[0]["operation_id"])
    return None


def render_mentor(
    snapshot: dict[str, Any],
    catalog: OperationCatalog,
    *,
    width: int,
    show_details: bool = False,
) -> str:
    lines = [MESSAGES.get("mentor_title"), "-" * max(1, min(width, 20))]
    goal = snapshot.get("goal")
    lines += _labeled(
        MESSAGES.get("goal"), goal["text"] if goal else MESSAGES.get("no_goal"), width
    )
    operation = _current_operation_for_snapshot(snapshot, catalog)
    active = snapshot.get("active_command")
    current_text = operation.title if operation else MESSAGES.get("wait_shell")
    if active and operation is None:
        current_text = f"{MESSAGES.get('unknown_command')}: {active['command']}"
    elif operation is None and (last := snapshot.get("last_observation")):
        current_text = f"{MESSAGES.get('unknown_command')}: {last['command']}"
    lines += _labeled(MESSAGES.get("current"), current_text, width)
    if operation:
        risk = MESSAGES.get(f"risk_{operation.risk.replace('-', '_')}")
        lines += _labeled(MESSAGES.get("risk"), f"{risk} · {operation.impact}", width)
    facts = snapshot.get("facts") or {}
    fact_text = "、".join(sorted(facts)) if facts else MESSAGES.get("no_facts")
    lines += _labeled(MESSAGES.get("facts"), fact_text, width)
    ai_status = {
        "ready": MESSAGES.get("ai_ready"),
        "error": MESSAGES.get("ai_error"),
    }.get(snapshot.get("ai_status"), MESSAGES.get("ai_wait"))
    lines += _labeled(MESSAGES.get("ai"), ai_status, width)
    advice = snapshot.get("advice") or {}
    if advice.get("summary"):
        lines += [""] + _labeled(MESSAGES.get("advice"), advice["summary"], width)
    for index, option in enumerate(advice.get("options") or [], start=1):
        trusted = catalog.require(option["operation_id"])
        lines += _wrap(f"{index}. {trusted.title} — {option['rationale']}", width)
        lines += _labeled(MESSAGES.get("command"), trusted.command, width)
    warnings = advice.get("warnings") or []
    for warning in warnings:
        lines += _labeled(MESSAGES.get("warning"), warning, width)
    if snapshot.get("probe_error"):
        lines += _labeled(
            MESSAGES.get("warning"),
            f"{MESSAGES.get('probe_error')}: {snapshot['probe_error']}",
            width,
        )
    if operation and show_details:
        lines += [""] + _labeled(MESSAGES.get("details"), operation.summary, width)
        lines += _labeled(MESSAGES.get("command"), operation.command, width)
        lines += _labeled(MESSAGES.get("success"), operation.success, width)
    elif operation:
        lines += [""] + _wrap(MESSAGES.get("details_hint"), width)
    return "\n".join(lines)


def render_wiki(
    snapshot: dict[str, Any],
    catalog: OperationCatalog,
    *,
    width: int,
    snapshot_version: str | None = None,
) -> str:
    operation = _operation_for_snapshot(snapshot, catalog)
    if operation is None:
        return f"{MESSAGES.get('wiki_title')}\n--------------------\n{MESSAGES.get('wiki_wait')}。"
    lines = [MESSAGES.get("wiki_title"), "-" * max(1, min(width, 20))]
    lines += _labeled(MESSAGES.get("page"), operation.wiki_page, width)
    lines += _labeled(MESSAGES.get("section"), operation.wiki_section, width)
    lines += _labeled(
        MESSAGES.get("snapshot"),
        snapshot_version or MESSAGES.get("unavailable"),
        width,
    )
    lines += [""] + _wrap(operation.summary, width)
    lines += [""] + _labeled(MESSAGES.get("source"), operation.wiki_url, width)
    return "\n".join(lines)


class MentorApp(App[None]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+d", "toggle_details", "Details", show=False, priority=True)
    ]

    CSS = """
    Screen { background: #10151b; color: #e6edf3; }
    #mentor { height: 1fr; padding: 1 2; overflow-y: auto; }
    #goal { dock: bottom; border-top: solid #2e3a47; }
    """

    def __init__(
        self,
        socket_path: Path,
        catalog: OperationCatalog,
        *,
        initial_snapshot: dict[str, Any] | None = None,
        connect: bool = True,
    ):
        super().__init__()
        self._catalog = catalog
        self._client = SessionClient(socket_path)
        self._snapshot = initial_snapshot or {}
        self._connect = connect
        self._show_details = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("等待 daemon…", id="mentor")
            yield Input(placeholder=MESSAGES.get("goal_prompt"), id="goal")

    def on_mount(self) -> None:
        if self._snapshot:
            self._render_snapshot()
        if self._connect:
            self._listen()

    @work(exclusive=True)
    async def _listen(self) -> None:
        async for snapshot in self._client.snapshots():
            self._snapshot = snapshot
            self._render_snapshot()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            try:
                await self._client.send("goal.set", {"text": text})
                event.input.clear()
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error", timeout=5)

    def on_resize(self, _event: Resize) -> None:
        if self._snapshot:
            self._render_snapshot()

    def action_toggle_details(self) -> None:
        self._show_details = not self._show_details
        if self._snapshot:
            self._render_snapshot()

    def _render_snapshot(self) -> None:
        self.query_one("#mentor", Static).update(
            render_mentor(
                self._snapshot,
                self._catalog,
                width=max(self.size.width - 4, 20),
                show_details=self._show_details,
            )
        )


class WikiApp(App[None]):
    CSS = """
    Screen { background: #10151b; color: #e6edf3; }
    #wiki { height: 1fr; padding: 1 2; overflow-y: auto; }
    """

    def __init__(
        self,
        socket_path: Path,
        catalog: OperationCatalog,
        *,
        initial_snapshot: dict[str, Any] | None = None,
        connect: bool = True,
        snapshot_version: str | None = None,
    ):
        super().__init__()
        self._catalog = catalog
        self._client = SessionClient(socket_path)
        self._snapshot = initial_snapshot or {}
        self._connect = connect
        self._snapshot_version = snapshot_version or local_wiki_version()

    def compose(self) -> ComposeResult:
        yield Static("等待 daemon…", id="wiki")

    def on_mount(self) -> None:
        if self._snapshot:
            self.query_one("#wiki", Static).update(
                render_wiki(
                    self._snapshot,
                    self._catalog,
                    width=max(self.size.width - 4, 20),
                    snapshot_version=self._snapshot_version,
                )
            )
        if self._connect:
            self._listen()

    @work(exclusive=True)
    async def _listen(self) -> None:
        async for snapshot in self._client.snapshots():
            self._snapshot = snapshot
            self.query_one("#wiki", Static).update(
                render_wiki(
                    snapshot,
                    self._catalog,
                    width=max(self.size.width - 4, 20),
                    snapshot_version=self._snapshot_version,
                )
            )

    def on_resize(self, _event: Resize) -> None:
        if self._snapshot:
            self.query_one("#wiki", Static).update(
                render_wiki(
                    self._snapshot,
                    self._catalog,
                    width=max(self.size.width - 4, 20),
                    snapshot_version=self._snapshot_version,
                )
            )
