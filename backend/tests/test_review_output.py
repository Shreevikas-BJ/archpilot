import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.agents.json_output import parse_json_output
from app.agents.responsibility import MessagingConcern, Plane, finalize_review
from app.agents.review_output import review_output_type, to_architecture_review
from app.schemas import ArchitecturePlan, Critique


@pytest.fixture
def review_case():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/unsafe_messaging_architecture.json").read_text()
    )
    plan = ArchitecturePlan.model_validate(fixture["architecture"])
    check = {
        "status": "fail",
        "evidence": "The requirement is not implemented.",
        "required_change": "Specify the missing implementation.",
    }
    payload = {
        "approved": True,
        "confidence": 0.8,
        "component_responsibilities": {
            c.id: {**check, "evidence": f"{c.id} has an incorrect responsibility."}
            for c in plan.components
        },
        "component_disappearances": {
            c.id: {**check, "evidence": f"{c.id} loses acknowledged data."} for c in plan.components
        },
        "planes": {key: check for key in get_args(Plane)},
        "messaging": {key: check for key in get_args(MessagingConcern)},
    }
    return plan, payload


def test_exact_audit_shape_preserves_all_findings_and_fails_closed(review_case):
    plan, payload = review_case
    output = parse_json_output(json.dumps(payload), review_output_type(plan))
    review = to_architecture_review(output)
    assert [c.component_id for c in review.components] == [c.id for c in plan.components]
    for item in review.components:
        assert (
            item.responsibility.model_dump()
            == payload["component_responsibilities"][item.component_id]
        )
        assert (
            item.disappearance.model_dump()
            == payload["component_disappearances"][item.component_id]
        )
    assert review.model_dump()["planes"] == payload["planes"]
    assert review.model_dump()["messaging"] == payload["messaging"]
    critique, notes = finalize_review(plan, review)
    assert not critique.approved
    assert len(notes) == len(plan.components) * 2 + 15


@pytest.mark.parametrize("missing", ["component", "disappearance", "plane", "messaging"])
def test_incomplete_audit_is_a_retryable_validation_error(review_case, missing):
    plan, payload = review_case
    if missing == "component":
        del payload["component_responsibilities"][plan.components[0].id]
    elif missing == "disappearance":
        del payload["component_disappearances"][plan.components[0].id]
    elif missing == "plane":
        del payload["planes"]["event"]
    else:
        del payload["messaging"]["idempotency"]
    with pytest.raises(ValidationError):
        parse_json_output(json.dumps(payload), review_output_type(plan))


@pytest.mark.parametrize("field", ["component_responsibilities", "component_disappearances"])
def test_unknown_component_cannot_replace_a_required_component(review_case, field):
    plan, payload = review_case
    payload[field]["made_up"] = payload[field].pop(plan.components[0].id)
    with pytest.raises(ValidationError):
        parse_json_output(json.dumps(payload), review_output_type(plan))


@pytest.mark.parametrize(
    "text",
    [
        '{"approved":false,"approved":true,"confidence":0.9}',
        '{"approved":true,"confidence":0.9,"extra":{"x":1,"x":2}}',
    ],
)
def test_duplicate_keys_are_never_silently_overwritten(text):
    with pytest.raises(json.JSONDecodeError, match="Duplicate JSON object key"):
        parse_json_output(text, Critique)


def test_reserved_component_names_use_aliases_without_losing_identity(review_case):
    plan, payload = review_case
    original = plan.components[0].id
    plan.components[0].id = "model_dump"
    for field in ("component_responsibilities", "component_disappearances"):
        payload[field]["model_dump"] = payload[field].pop(original)
    review = to_architecture_review(review_output_type(plan).model_validate(payload))
    assert review.components[0].component_id == "model_dump"
