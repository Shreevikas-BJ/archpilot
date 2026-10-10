import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agents import factory
from app.agents.json_output import run_json_agent
from app.agents.json_stream import JSONStreamGuard
from app.config import Settings
from app.schemas import ArchitecturePlan, Critique


@pytest.mark.parametrize("fence", ["", "```json\n", "```code\r\n", "```\n"])
def test_every_valid_prefix_is_allowed_including_unicode_escapes_and_json_punctuation(fence):
    payload = {
        "approved": False,
        "confidence": 0.82,
        "risks": ['quotes " braces {} [] backslash \\ newline\nemoji \U0001f600'],
        "unknown": [True, False, None, -1.3e-12, 1e20, {"nested": [1, 2]}],
    }
    text = fence + json.dumps(payload) + ("\n```" if fence else "")
    guard = JSONStreamGuard(Critique)
    for index in range(len(text) + 1):
        guard.text = text[:index]
        guard.check()


def test_every_prefix_of_real_architecture_fixture_is_allowed():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/unsafe_messaging_architecture.json").read_text()
    )["architecture"]
    text = json.dumps(fixture)
    guard = JSONStreamGuard(ArchitecturePlan)
    for index in range(len(text) + 1):
        guard.text = text[:index]
        guard.check()


@pytest.mark.parametrize(
    "text",
    [
        '{"approved": truX',
        '{"approved" false',
        '{"approved": false, "confidence": oops',
        '{"approved":false,"confidence":0.8,}',
        '{"approved":false,"confidence":0.8} trailing prose',
    ],
)
def test_irrecoverable_json_is_rejected_before_model_finishes(text):
    guard = JSONStreamGuard(Critique)
    guard.text = text
    with pytest.raises(json.JSONDecodeError):
        guard.check()


def test_complete_but_schema_invalid_object_is_rejected_early():
    guard = JSONStreamGuard(Critique)
    guard.text = '{"approved":true,"confidence":2}'
    with pytest.raises(ValidationError):
        guard.check()


async def test_broken_stream_closes_without_consuming_tail_and_retries_fresh_plain_chat(
    monkeypatch,
):
    requests = []
    closed = []
    tail_consumed = []

    class Chunks(httpx.AsyncByteStream):
        def __init__(self, attempt):
            self.attempt = attempt

        async def __aiter__(self):
            text = (
                ('{"approved": truX' + " " * 150)
                if self.attempt == 1
                else ('{"approved":false,"confidence":0.9}')
            )
            chunk = {
                "id": "stream-check",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "bonsai-test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": None,
                        "delta": {"role": "assistant", "content": text},
                    }
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n".encode()
            tail_consumed.append(self.attempt)
            chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            yield f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()

        async def aclose(self):
            closed.append(self.attempt)

    def completion(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["stream"] is True
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        assert not {"tools", "tool_choice", "response_format"} & body.keys()
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=Chunks(len(requests))
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(completion)) as client:
        model = OpenAIChatModel(
            "bonsai-test",
            provider=OpenAIProvider(base_url="http://bonsai.test/v1", http_client=client),
        )
        monkeypatch.setattr(factory, "build_model", lambda settings: model)
        agent = factory.build_agent(
            settings=Settings(), output_type=Critique, instructions="Review"
        )
        result = await run_json_agent(agent, "Review architecture.", Critique)
    assert result.approved is False
    assert len(requests) == 2
    assert tail_consumed == [2]
    assert closed == [1, 2]
    assert "previous attempt failed validation" in requests[1]["messages"][1]["content"]
