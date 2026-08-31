from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .catalog import OperationCatalog


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    command_id: str
    command: str
    cwd: str
    exit_code: int
    output_excerpt: str = ""
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: Any
    source: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Goal(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    status: str = "active"


class AdviceOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_id: str
    rationale: str


class Advice(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    options: tuple[AdviceOption, ...] = Field(default=(), max_length=3)
    warnings: tuple[str, ...] = ()


class SessionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    facts: dict[str, Any]
    goal: Goal | None
    observed_operations: tuple[str, ...]
    current_operation: str | None
    last_observation: Observation | None
    advice: Advice | None


class AssistantSession:
    """Owns the verified installation context behind a small behavior interface."""

    def __init__(self, catalog: OperationCatalog):
        self._catalog = catalog
        self._facts: dict[str, Any] = {}
        self._goal: Goal | None = None
        self._observed_operations: list[str] = []
        self._current_operation: str | None = None
        self._last_observation: Observation | None = None
        self._advice: Advice | None = None

    def set_goal(self, text: str) -> SessionSnapshot:
        goal = text.strip()
        if not goal:
            raise ValueError("goal must not be empty")
        self._goal = Goal(text=goal)
        self._advice = None
        return self.snapshot()

    def observe(self, observation: Observation, verified_facts: list[Fact]) -> SessionSnapshot:
        self._last_observation = observation
        operation = self._catalog.recognize(observation.command)
        self._current_operation = operation.id if operation else None
        self._advice = None
        if operation is None:
            return self.snapshot()

        if operation.id not in self._observed_operations:
            self._observed_operations.append(operation.id)
        for fact in verified_facts:
            if fact.key in operation.produces and fact.source == operation.probe:
                self._facts[fact.key] = fact.value
        return self.snapshot()

    def apply_advice(self, advice: Advice) -> SessionSnapshot:
        for option in advice.options:
            self._catalog.require(option.operation_id)
        self._advice = advice
        return self.snapshot()

    def available_operations(self):
        known = self._facts.keys()
        return tuple(
            operation
            for operation in self._catalog.available(self._facts)
            if not operation.produces <= known
        )

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            facts=dict(self._facts),
            goal=self._goal,
            observed_operations=tuple(self._observed_operations),
            current_operation=self._current_operation,
            last_observation=self._last_observation,
            advice=self._advice,
        )
