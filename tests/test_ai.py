import json

import httpx
import pytest

from airchinstall.ai import OpenAICompatibleTutor, TutorRequest, TutorUnavailable
from airchinstall.catalog import OperationCatalog


@pytest.mark.asyncio
async def test_ai_receives_only_goal_facts_and_trusted_operations(tmp_path):
    catalog = OperationCatalog.load_default()
    key_file = tmp_path / "ai-key"
    key_file.write_text("secret-key")
    key_file.chmod(0o600)
    captured = {}

    def handler(request: httpx.Request):
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "可以先确认网络或磁盘。",
                                    "options": [
                                        {
                                            "operation_id": "check-network",
                                            "rationale": "下载前确认联网",
                                        },
                                        {
                                            "operation_id": "list-disks",
                                            "rationale": "先了解设备",
                                        },
                                    ],
                                    "warnings": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tutor = OpenAICompatibleTutor(
            base_url="https://example.invalid/v1",
            model="test-model",
            key_file=key_file,
            catalog=catalog,
            client=client,
        )
        advice = await tutor.advise(
            TutorRequest(
                goal="我想安装一个桌面环境",
                facts={"boot.uefi": True},
                available_operation_ids=("check-network", "list-disks"),
            )
        )

    prompt = captured["body"]["messages"][1]["content"]
    assert advice.options[0].operation_id == "check-network"
    assert captured["authorization"] == "Bearer secret-key"
    assert "secret-key" not in json.dumps(captured["body"])
    assert "terminal_output" not in prompt
    assert "check-network" in prompt
    assert "ping -c 3 ping.archlinux.org" in prompt


@pytest.mark.asyncio
async def test_ai_cannot_return_an_operation_outside_the_catalog(tmp_path):
    catalog = OperationCatalog.load_default()
    key_file = tmp_path / "ai-key"
    key_file.write_text("secret-key")
    key_file.chmod(0o600)

    def handler(_request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"summary":"bad","options":[{"operation_id":"rm-root","rationale":"bad"}]}'
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tutor = OpenAICompatibleTutor(
            base_url="https://example.invalid/v1",
            model="test-model",
            key_file=key_file,
            catalog=catalog,
            client=client,
        )
        with pytest.raises(TutorUnavailable, match="unavailable operation"):
            await tutor.advise(
                TutorRequest(
                    goal="anything",
                    facts={},
                    available_operation_ids=("check-network",),
                )
            )


@pytest.mark.asyncio
async def test_ai_requires_two_distinct_options_when_catalog_has_enough(tmp_path):
    catalog = OperationCatalog.load_default()
    key_file = tmp_path / "ai-key"
    key_file.write_text("secret-key")
    key_file.chmod(0o600)

    def handler(_request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"summary":"too few","options":[{"operation_id":"check-network","rationale":"only one"}]}'
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tutor = OpenAICompatibleTutor(
            base_url="https://example.invalid/v1",
            model="test-model",
            key_file=key_file,
            catalog=catalog,
            client=client,
        )
        with pytest.raises(TutorUnavailable, match="2 to 3"):
            await tutor.advise(
                TutorRequest(
                    goal="了解环境",
                    facts={},
                    available_operation_ids=("inspect-uefi", "check-network", "list-disks"),
                )
            )


@pytest.mark.asyncio
async def test_ai_retries_one_timeout_then_accepts_structured_response(tmp_path):
    catalog = OperationCatalog.load_default()
    key_file = tmp_path / "ai-key"
    key_file.write_text("secret-key")
    key_file.chmod(0o600)
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow provider", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "recovered",
                                    "options": [
                                        {"operation_id": "check-network", "rationale": "one"},
                                        {"operation_id": "list-disks", "rationale": "two"},
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tutor = OpenAICompatibleTutor(
            base_url="https://example.invalid/v1",
            model="test-model",
            key_file=key_file,
            catalog=catalog,
            client=client,
        )
        advice = await tutor.advise(
            TutorRequest(
                goal="了解环境",
                facts={},
                available_operation_ids=("check-network", "list-disks"),
            )
        )

    assert calls == 2
    assert advice.summary == "recovered"


@pytest.mark.asyncio
async def test_ai_stops_after_two_timeouts(tmp_path):
    catalog = OperationCatalog.load_default()
    key_file = tmp_path / "ai-key"
    key_file.write_text("secret-key")
    key_file.chmod(0o600)
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("still slow", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tutor = OpenAICompatibleTutor(
            base_url="https://example.invalid/v1",
            model="test-model",
            key_file=key_file,
            catalog=catalog,
            client=client,
        )
        with pytest.raises(TutorUnavailable):
            await tutor.advise(
                TutorRequest(
                    goal="了解环境",
                    facts={},
                    available_operation_ids=("check-network", "list-disks"),
                )
            )

    assert calls == 2


def test_cloud_adapter_rejects_insecure_remote_base_url(tmp_path):
    key_file = tmp_path / "ai-key"
    key_file.write_text("secret-key")
    key_file.chmod(0o600)

    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleTutor(
            base_url="http://remote.example/v1",
            model="test-model",
            key_file=key_file,
            catalog=OperationCatalog.load_default(),
        )
