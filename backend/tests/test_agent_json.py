import json
from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agents import factory
from app.agents.json_output import (
    AgentJSONError,
    parse_json_output,
    run_json_agent,
    strip_json_fences,
)
from app.agents.orchestrator import ArchitectureOrchestrator
from app.agents.responsibility import MessagingConcern, Plane
from app.api import routes
from app.config import Settings
from app.db.session import get_session
from app.schemas import ArchitecturePlan, ArchitectureRequest, Critique, ResearchPlan, SearchSource


@pytest.mark.parametrize("fence", [None, "json", "JSON", "code", ""])
def test_plain_and_fenced_json_are_validated(fence):
    content = json.dumps({"approved": True, "confidence": 0.9})
    text = content if fence is None else f"```{fence}\n{content}\n```"
    output = parse_json_output(f" \n{text}\n ", Critique)
    assert isinstance(output, Critique)
    assert output.approved is True
    assert output.confidence == 0.9


def test_fence_helper_preserves_backticks_inside_json():
    content = '{"message": "Use ```json fences only in documentation"}'
    assert strip_json_fences(content) == content


@pytest.mark.parametrize("text", ["not JSON", 'Here is the JSON: {"approved": true}'])
def test_invalid_json_is_rejected(text):
    with pytest.raises(json.JSONDecodeError):
        parse_json_output(text, Critique)


@pytest.mark.parametrize(
    "payload",
    [{"approved": True}, {"approved": True, "confidence": 2}, ["not an object"]],
)
def test_existing_model_constraints_are_enforced(payload):
    with pytest.raises(ValidationError):
        parse_json_output(json.dumps(payload), Critique)


def test_existing_custom_validators_still_run():
    with pytest.raises(ValidationError, match="three unique"):
        parse_json_output('{"queries": ["same", "SAME", "same"]}', ResearchPlan)


@pytest.mark.parametrize("recover", [False, True])
@pytest.mark.parametrize("first_output", ["not JSON", ""])
@pytest.mark.parametrize("budget", [None, 4096])
async def test_json_retries_keep_plain_chat_and_report_exhaustion(
    monkeypatch, recover, first_output, budget
):
    outputs = [
        first_output,
        '{"approved": true, "confidence": 2}',
        '{"approved": true, "confidence": 0.9}' if recover else "{}",
    ]
    requests = []
    settings = Settings(
        llm_timeout_seconds=123,
        llm_reasoning_budget_tokens=budget,
        llm_planning_reasoning_budget_tokens=1024 if budget else None,
        llm_reasoning_budget_message="Return JSON now." if budget else None,
    )

    def chat_completion(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.extensions["timeout"]["read"] == 123
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        assert not {"tools", "tool_choice", "response_format", "parallel_tool_calls"} & body.keys()
        if budget:
            assert body["reasoning_budget_tokens"] == (1024 if len(requests) == 1 else 4096)
            assert body["reasoning_budget_message"] == "Return JSON now."
        else:
            assert "reasoning_budget_tokens" not in body
            assert "reasoning_budget_message" not in body
        assert body["messages"][1]["content"].startswith("Review the architecture.")
        if len(requests) > 1:
            assert "previous attempt failed validation" in body["messages"][1]["content"]
        return streamed_completion(
            {
                "id": "retry-test",
                "object": "chat.completion",
                "created": 0,
                "model": "bonsai-test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": outputs[len(requests) - 1],
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(chat_completion)) as client:
        model = OpenAIChatModel(
            "bonsai-test",
            provider=OpenAIProvider(base_url="http://bonsai.test/v1", http_client=client),
        )
        monkeypatch.setattr(factory, "build_model", lambda settings: model)
        agent = factory.build_agent(
            settings=settings,
            output_type=Critique,
            instructions="Review architecture.",
            reasoning_budget_tokens=settings.llm_planning_reasoning_budget_tokens,
        )
        if recover:
            result = await run_json_agent(
                agent,
                "Review the architecture.",
                Critique,
                retry_model_settings=factory.agent_model_settings(settings),
            )
            assert result.approved is True
        else:
            with pytest.raises(AgentJSONError, match="Critique.*after 3 attempts") as error:
                await run_json_agent(
                    agent,
                    "Review the architecture.",
                    Critique,
                    retry_model_settings=factory.agent_model_settings(settings),
                )
            assert isinstance(error.value.__cause__, ValidationError)

    assert len(requests) == 3
    feedback = "Invalid JSON" if first_output else "No usable text output"
    assert feedback in requests[1]["messages"][1]["content"]
    assert "confidence" in requests[2]["messages"][1]["content"]
    assert all(r["messages"][0] == requests[0]["messages"][0] for r in requests)


async def test_transport_errors_are_not_retried_as_json_errors():
    agent = AsyncMock()
    agent.run.side_effect = httpx.ConnectError("Model offline")
    with pytest.raises(httpx.ConnectError):
        await run_json_agent(agent, "Review", Critique)
    agent.run.assert_awaited_once()


async def test_json_retries_can_be_disabled():
    agent = AsyncMock()
    agent.run.return_value = SimpleNamespace(output="not JSON")
    with pytest.raises(AgentJSONError, match="after 1 attempts"):
        await run_json_agent(agent, "Review", Critique, max_retries=0)
    agent.run.assert_awaited_once()


async def test_truncated_output_gets_shorter_output_guidance_without_replaying_history():
    agent = AsyncMock()
    agent.run.side_effect = [
        SimpleNamespace(output='{"approved":', response=SimpleNamespace(finish_reason="length")),
        SimpleNamespace(output='{"approved":false,"confidence":0.9}'),
    ]
    result = await run_json_agent(agent, "Review the architecture.", Critique)
    assert not result.approved
    retry = agent.run.await_args_list[1].args[0]
    assert "truncated at the token/context limit" in retry
    assert "Shorten scalar values" in retry
    assert len(agent.run.await_args_list[1].args) == 1
    assert agent.run.await_count == 2


def test_exhausted_json_retries_return_clear_api_error_without_saving(monkeypatch):
    message = "Critique failed to return valid JSON matching its schema after 3 attempts."
    monkeypatch.setattr(
        ArchitectureOrchestrator, "run", AsyncMock(side_effect=AgentJSONError(message))
    )
    save = AsyncMock()
    monkeypatch.setattr(routes, "save_run", save)
    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    with TestClient(app) as client:
        response = client.post(
            "/v1/architectures", json={"problem": "Build an internal issue tracker for 20 staff."}
        )
    assert response.status_code == 500
    assert response.json() == {"detail": message}
    save.assert_not_awaited()


@pytest.mark.parametrize("needs_revision", [False, True])
async def test_entire_flow_sends_only_plain_chat(monkeypatch, needs_revision):
    requirements = {
        "problem_summary": "Internal issue tracker",
        "business_goal": "Track support requests",
        "users_and_scale": "20 staff",
        "latency_expectation": "Under one second",
        "data_characteristics": "Small relational records",
        "security_and_compliance": "Internal access",
    }
    architecture = {
        "title": "Issue tracker",
        "mode": "balanced",
        "summary": "An API with persistent storage",
        "components": [
            {
                "id": component_id,
                "name": name,
                "technology": technology,
                "category": category,
                "purpose": purpose,
                "deployment": "Docker",
            }
            for component_id, name, technology, category, purpose in [
                ("api", "API", "FastAPI", "backend", "Serve requests"),
                ("db", "Database", "PostgreSQL", "storage", "Store issues"),
            ]
        ],
        "connections": [{"source": "api", "target": "db"}],
        "estimated_monthly_cost": "$0 incremental",
        "assumptions": [],
        "tradeoffs": ["Single host"],
        "implementation_steps": ["Deploy containers"],
        "source_urls": ["https://www.postgresql.org/docs/"],
    }
    outputs = [
        requirements,
        {"queries": ["FastAPI deployment", "PostgreSQL Docker", "Internal issue tracking"]},
        {"industry_baseline": "API and database", "candidates": [], "key_tradeoffs": []},
        architecture,
        review_payload(architecture),
    ]
    if needs_revision:
        # An overconfident verdict cannot bypass a failed component disappearance check.
        outputs[-1]["components"][1]["disappearance"] = {
            "status": "fail",
            "evidence": "The acknowledged issue is stored on a single host.",
            "required_change": "Document synchronous durable replicas before acknowledging writes",
        }
    schema_names = [
        "RequirementsAnalysis",
        "ResearchPlan",
        "EvaluationReport",
        "ArchitecturePlan",
        "ArchitectureReviewOutput",
    ]
    if needs_revision:
        outputs.extend(
            [
                {"title": "Issue tracker with backups"},
                review_payload(architecture),
            ]
        )
        schema_names.extend(["ArchitectureRevision", "ArchitectureReviewOutput"])
    requests = []

    def chat_completion(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests) - 1
        assert request.url.path == "/v1/chat/completions"
        assert body["reasoning_budget_tokens"] == (
            1024 if index < 3 else 2048 if index in {4, 6} else 4096
        )
        assert body["reasoning_budget_message"] == "Return JSON now."
        assert [message["role"] for message in body["messages"]] == ["system", "user"]
        assert not {"tools", "tool_choice", "response_format", "parallel_tool_calls"} & body.keys()
        system_prompt = body["messages"][0]["content"]
        assert "Return JSON only" in system_prompt
        schema = json.loads(system_prompt.split("JSON Schema:\n", 1)[1])
        assert schema["title"] == schema_names[index]
        if index > 0:
            context = json.loads(body["messages"][1]["content"].split("CONTEXT JSON:\n")[1])
            assert context["user_request"]["problem"] == (
                "Build an internal issue tracker for 20 staff."
            )
        if schema_names[index] == "ArchitectureReviewOutput":
            assert context["evidence"][0]["url"] == "https://www.postgresql.org/docs/"
            assert '"If this component completely disappears right now' in system_prompt
        if needs_revision and index == 5:
            assert context["critique"]["approved"] is False
            assert "synchronous durable replicas" in context["critique"]["required_changes"][0]
        if needs_revision and index == 6:
            # A small delta reaches the critic as a complete design, never as a patch.
            assert context["architecture"] == {
                **ArchitecturePlan.model_validate(architecture).model_dump(),
                "title": "Issue tracker with backups",
            }
        output = outputs[index]
        if schema_names[index] == "ArchitectureReviewOutput":
            output = {
                **{key: value for key, value in output.items() if key != "components"},
                "component_responsibilities": {
                    item["component_id"]: item["responsibility"] for item in output["components"]
                },
                "component_disappearances": {
                    item["component_id"]: item["disappearance"] for item in output["components"]
                },
            }
        return streamed_completion(
            {
                "id": f"chat-{index}",
                "object": "chat.completion",
                "created": 0,
                "model": "bonsai-test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": f"```json\n{json.dumps(output)}\n```",
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(chat_completion)) as client:
        model = OpenAIChatModel(
            "bonsai-test",
            provider=OpenAIProvider(base_url="http://bonsai.test/v1", http_client=client),
        )
        monkeypatch.setattr(factory, "build_model", lambda settings: model)
        search = AsyncMock()
        search.search_many.return_value = [
            SearchSource(
                title="PostgreSQL docs",
                url="https://www.postgresql.org/docs/",
                query="PostgreSQL Docker",
            )
        ]
        orchestrator = ArchitectureOrchestrator(
            Settings(
                llm_reasoning_budget_tokens=4096,
                llm_planning_reasoning_budget_tokens=1024,
                llm_review_reasoning_budget_tokens=2048,
                llm_reasoning_budget_message="Return JSON now.",
            ),
            search,
        )
        progress = []

        async def report(update):
            progress.append(update)

        result = await orchestrator.run(
            ArchitectureRequest(problem="Build an internal issue tracker for 20 staff."),
            run_id="tracked-run",
            progress=report,
        )

    assert result.status == "complete"
    assert result.run_id == "tracked-run"
    expected_stages = [
        "requirements",
        "research",
        "search",
        "evaluation",
        "architecture",
        "critique",
    ]
    if needs_revision:
        expected_stages.extend(["revision", "final_review"])
    assert [update.stage for update in progress] == expected_stages
    assert progress[1].requirements.problem_summary == "Internal issue tracker"
    assert result.critique.approved is True
    assert result.architecture.title == (
        "Issue tracker with backups" if needs_revision else "Issue tracker"
    )
    assert "flowchart TD" in result.mermaid
    assert len(requests) == (7 if needs_revision else 5)
    search.search_many.assert_awaited_once()
    assert any("db disappears [pass]" in note for note in result.architecture.tradeoffs)
    assert not any("[fail]" in note for note in result.architecture.tradeoffs)
    assert set(result.critique.model_dump()) == {
        "approved",
        "confidence",
        "risks",
        "required_changes",
        "unnecessary_components",
    }


def streamed_completion(payload):
    choice = payload["choices"][0]
    base = {key: payload[key] for key in ("id", "created", "model")}
    base["object"] = "chat.completion.chunk"
    chunks = [
        {**base, "choices": [{"index": 0, "delta": choice["message"], "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}]},
    ]
    content = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=content)


def review_payload(architecture):
    return {
        "approved": True,
        "confidence": 0.9,
        "components": [
            {
                "component_id": item["id"],
                "responsibility": {"status": "pass", "evidence": "Assigned role is appropriate."},
                "disappearance": {
                    "status": "pass",
                    "evidence": "Committed writes survive on durable replicas.",
                },
            }
            for item in architecture["components"]
        ],
        "planes": {
            name: {"status": "not_applicable", "evidence": "Not used in this unit-test design."}
            for name in get_args(Plane)
        },
        "messaging": {
            name: {
                "status": "not_applicable",
                "evidence": "This issue tracker has no user messaging.",
            }
            for name in get_args(MessagingConcern)
        },
    }
