import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agents.json_output import AgentJSONError, run_json_agent
from app.agents.revision import ArchitectureRevision
from app.schemas import ArchitecturePlan


@pytest.fixture
def previous():
    payload = json.loads(
        (Path(__file__).parent / "fixtures/unsafe_messaging_architecture.json").read_text()
    )
    return ArchitecturePlan.model_validate(payload["architecture"])


def validate(payload, previous):
    return ArchitectureRevision.model_validate(
        payload, context={"previous_architecture": previous}
    ).apply_to(previous)


def test_revision_preserves_every_untouched_field_and_input(previous):
    before = previous.model_dump()
    changed = {
        **before["components"][0],
        "purpose": "Client encrypts messages and wraps media keys",
    }
    result = validate({"component_updates": [changed]}, previous)
    expected = previous.model_dump()
    expected["components"][0] = changed
    assert result.model_dump() == expected
    assert previous.model_dump() == before


def test_revision_can_add_components_and_replace_complete_connection_list(previous):
    new = previous.components[0].model_copy(update={"id": "extra_store"}).model_dump()
    connections = [item.model_dump() for item in previous.connections]
    connections.append({"source": previous.components[0].id, "target": "extra_store"})
    result = validate({"component_updates": [new], "connections": connections}, previous)
    assert result.components[:-1] == previous.components
    assert result.components[-1].id == "extra_store"
    assert result.connections[-1].target == "extra_store"


def test_removal_requires_valid_remaining_connections(previous):
    removed = previous.connections[0].source
    with pytest.raises(ValidationError, match="unknown component"):
        validate({"remove_component_ids": [removed]}, previous)
    edges = [e.model_dump() for e in previous.connections if removed not in (e.source, e.target)]
    result = validate({"remove_component_ids": [removed], "connections": edges}, previous)
    assert removed not in {c.id for c in result.components}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"summary": None},
        {"summary": "", "mode": "cost_effective"},
        {"connections": []},
        {"connections": [{"source": "missing", "target": "missing"}]},
        {"remove_component_ids": ["unknown"]},
        {"component_updatess": []},
    ],
)
def test_invalid_or_noop_revisions_are_rejected(previous, payload):
    with pytest.raises(ValidationError):
        validate(payload, previous)


def test_duplicate_or_conflicting_component_edits_are_rejected(previous):
    component = previous.components[0].model_dump()
    for payload in [
        {"component_updates": [component, component]},
        {"remove_component_ids": [component["id"], component["id"]]},
        {"component_updates": [component], "remove_component_ids": [component["id"]]},
    ]:
        with pytest.raises(ValidationError):
            validate(payload, previous)


def test_null_preserves_list_but_empty_list_explicitly_clears_it(previous):
    result = validate({"title": "Revised", "tradeoffs": None, "assumptions": []}, previous)
    assert result.tradeoffs == previous.tradeoffs
    assert result.assumptions == []


@pytest.mark.parametrize("recover", [True, False])
async def test_merge_failures_retry_before_final_review(previous, recover):
    agent = AsyncMock()
    agent.run.side_effect = [
        SimpleNamespace(output='{"connections":[{"source":"unknown","target":"missing"}]}'),
        SimpleNamespace(output='{"title":"Revised"}' if recover else "{}"),
    ]
    if recover:
        revision = await run_json_agent(
            agent,
            "Fix the design",
            ArchitectureRevision,
            max_retries=1,
            validation_context={"previous_architecture": previous},
        )
        assert revision.apply_to(previous).title == "Revised"
    else:
        with pytest.raises(AgentJSONError, match="after 2 attempts"):
            await run_json_agent(
                agent,
                "Fix the design",
                ArchitectureRevision,
                max_retries=1,
                validation_context={"previous_architecture": previous},
            )
    assert "unknown component" in agent.run.await_args_list[1].args[0]


async def test_attempt_metrics_do_not_log_private_content(caplog):
    caplog.set_level("INFO", logger="uvicorn.error.agents")
    agent = AsyncMock()
    agent.run.return_value = SimpleNamespace(
        output='{"title":"private title"}',
        response=SimpleNamespace(
            finish_reason="stop", usage=SimpleNamespace(input_tokens=300, output_tokens=12)
        ),
    )
    await run_json_agent(
        agent, "private user request", ArchitectureRevision, run_id="timing-run", stage="revision"
    )
    assert "run=timing-run stage=revision" in caplog.text
    assert "input_tokens=300 output_tokens=12" in caplog.text
    assert "outcome=valid" in caplog.text
    assert "private" not in caplog.text
