from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_command(command: str) -> str:
    return " ".join(command.strip().split()).removesuffix(";")


class Operation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    title_en: str
    command: str
    impact: str
    risk: Literal["readonly", "modifies-system", "irreversible"]
    patterns: tuple[str, ...]
    produces: frozenset[str]
    probe: str
    summary: str
    success: str
    wiki_page: str
    wiki_section: str
    wiki_url: str
    prerequisites: dict[str, object] = Field(default_factory=dict)

    @field_validator("patterns")
    @classmethod
    def valid_patterns(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in patterns:
            re.compile(pattern)
        return patterns

    def matches(self, command: str) -> bool:
        normalized = normalize_command(command)
        return any(re.fullmatch(pattern, normalized) for pattern in self.patterns)


class CatalogDocument(BaseModel):
    version: Literal[1]
    operations: tuple[Operation, ...]


class OperationCatalog:
    def __init__(self, operations: tuple[Operation, ...]):
        self._operations = operations
        self._by_id = {operation.id: operation for operation in operations}
        if len(self._by_id) != len(operations):
            raise ValueError("duplicate operation id")

    @classmethod
    def load(cls, path: Path) -> OperationCatalog:
        with path.open("rb") as catalog_file:
            document = CatalogDocument.model_validate(tomllib.load(catalog_file))
        return cls(document.operations)

    @classmethod
    def load_default(cls) -> OperationCatalog:
        return cls.load(Path(__file__).parent / "data" / "operations.toml")

    @property
    def operations(self) -> tuple[Operation, ...]:
        return self._operations

    def recognize(self, command: str) -> Operation | None:
        return next(
            (operation for operation in self._operations if operation.matches(command)),
            None,
        )

    def require(self, operation_id: str) -> Operation:
        try:
            return self._by_id[operation_id]
        except KeyError as error:
            raise ValueError(f"unknown operation: {operation_id}") from error

    def available(self, facts: dict[str, object]) -> tuple[Operation, ...]:
        return tuple(
            operation
            for operation in self._operations
            if all(facts.get(key) == value for key, value in operation.prerequisites.items())
        )
