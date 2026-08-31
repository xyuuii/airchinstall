from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .catalog import OperationCatalog
from .domain import Advice


class TutorRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    goal: str
    facts: dict[str, object]
    available_operation_ids: tuple[str, ...]
    last_observation: dict[str, object] | None = None


class TutorProvider(Protocol):
    async def advise(self, request: TutorRequest) -> Advice: ...


class TutorUnavailable(RuntimeError):
    """The external tutor could not return a valid structured response."""


class OpenAICompatibleTutor:
    """Cloud AI adapter; it can select trusted operations but never execute them."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        key_file: Path,
        catalog: OperationCatalog,
        client: httpx.AsyncClient | None = None,
    ):
        parsed = urlparse(base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
        if parsed.scheme != "https" and not local_http:
            raise ValueError("cloud AI base URL must use HTTPS")
        if not model.strip():
            raise ValueError("AI model must not be empty")
        if not key_file.is_file() or stat.S_IMODE(key_file.stat().st_mode) != 0o600:
            raise ValueError("AI key file must exist with mode 0600")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._key_file = key_file
        self._catalog = catalog
        self._client = client

    async def advise(self, request: TutorRequest) -> Advice:
        key = self._key_file.read_text().strip()
        if not key:
            raise ValueError("AI API key is empty")

        available = [
            self._catalog.require(operation_id) for operation_id in request.available_operation_ids
        ]
        prompt = json.dumps(
            {
                "goal": request.goal,
                "verified_facts": request.facts,
                "last_observation": request.last_observation,
                "available_operations": [
                    {
                        "id": operation.id,
                        "title": operation.title,
                        "command": operation.command,
                        "impact": operation.impact,
                        "risk": operation.risk,
                        "produces": sorted(operation.produces),
                        "summary": operation.summary,
                        "wiki": f"{operation.wiki_page}#{operation.wiki_section}",
                    }
                    for operation in available
                ],
                "response_contract": {
                    "summary": "string",
                    "options": [
                        {
                            "operation_id": "2-3 distinct trusted ids when available",
                            "rationale": "string",
                        }
                    ],
                    "warnings": ["string"],
                    "required_option_count": f"{min(2, len(available))} to {min(3, len(available))}",
                },
            },
            ensure_ascii=False,
        )
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 Airchinstall 的解释助手。只引用提供的 operation id；"
                        "不执行命令，不选择磁盘，不臆测系统事实。"
                        "没有可选 operation 时返回空 options。只输出 JSON。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        try:
            response = await self._post(payload, key)
            content = response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as error:
            raise TutorUnavailable(type(error).__name__) from None
        if content.startswith("```"):
            content = (
                content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            )
        try:
            advice = Advice.model_validate_json(content)
        except ValidationError as error:
            raise TutorUnavailable("invalid structured Advice") from error
        allowed = set(request.available_operation_ids)
        option_ids = [option.operation_id for option in advice.options]
        minimum = min(2, len(allowed))
        maximum = min(3, len(allowed))
        if not minimum <= len(option_ids) <= maximum:
            raise TutorUnavailable(f"Advice must contain {minimum} to {maximum} options")
        if len(option_ids) != len(set(option_ids)):
            raise TutorUnavailable("Advice options must be distinct")
        for option in advice.options:
            if option.operation_id not in allowed:
                raise TutorUnavailable(
                    f"Advice referenced an unavailable operation: {option.operation_id}"
                )
        return advice

    async def _post(self, payload: dict[str, object], key: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if self._client is not None:
            return await self._post_with_retry(self._client, payload, headers)
        async with httpx.AsyncClient(timeout=15) as client:
            return await self._post_with_retry(client, payload, headers)

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.status_code >= 500 and attempt == 0:
                    continue
                response.raise_for_status()
                return response
            except httpx.TransportError as error:
                last_error = error
                if attempt:
                    raise
        raise RuntimeError("AI request failed") from last_error
