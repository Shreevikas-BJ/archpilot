from copy import deepcopy
from typing import get_args

import pytest
from pydantic import ValidationError

from app.agents.responsibility import (
    ArchitectureReview,
    MessagingConcern,
    Plane,
    ResponsibilityCheck,
    finalize_review,
)
from app.schemas import ArchitecturePlan


@pytest.fixture
def architecture():
    return ArchitecturePlan.model_validate(
        {
            "title": "Test service",
            "mode": "balanced",
            "summary": "Replicated service",
            "components": [
                {
                    "id": name,
                    "name": name,
                    "technology": tech,
                    "category": plane,
                    "purpose": purpose,
                    "deployment": "Independent replicated failure domains",
                }
                for name, tech, plane, purpose in [
                    ("api", "FastAPI", "control", "Authorize writes"),
                    ("history", "ScyllaDB", "durable_data", "Persist ciphertext history"),
                ]
            ],
            "connections": [{"source": "api", "target": "history", "label": "Commit before ACK"}],
            "estimated_monthly_cost": "Test fixture",
            "assumptions": [],
            "tradeoffs": [],
            "implementation_steps": [],
        }
    )


@pytest.fixture
def review(architecture):
    passed = {"status": "pass", "evidence": "The design specifies the required guarantee."}
    return ArchitectureReview.model_validate(
        {
            "approved": True,
            "confidence": 0.9,
            "components": [
                {"component_id": item.id, "responsibility": passed, "disappearance": passed}
                for item in architecture.components
            ],
            "planes": {name: passed for name in get_args(Plane)},
            "messaging": {name: passed for name in get_args(MessagingConcern)},
        }
    )


@pytest.mark.parametrize("concern", get_args(MessagingConcern))
def test_failed_messaging_guarantee_overrides_positive_verdict(architecture, review, concern):
    review.messaging[concern] = ResponsibilityCheck(
        status="fail",
        evidence="The architecture omits this required guarantee.",
        required_change=f"Specify {concern} before acceptance.",
    )
    critique, notes = finalize_review(architecture, review)
    assert not critique.approved
    assert f"Specify {concern} before acceptance." in critique.required_changes
    assert any("[fail]" in note for note in notes)


@pytest.mark.parametrize("field", ["responsibility", "disappearance"])
def test_component_misuse_or_acknowledged_data_loss_blocks_approval(architecture, review, field):
    setattr(
        review.components[1],
        field,
        ResponsibilityCheck(
            status="fail", evidence="Redis cannot be the authoritative acknowledged history here."
        ),
    )
    critique, _ = finalize_review(architecture, review)
    assert not critique.approved
    assert "Redis" in critique.required_changes[0]


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "na"])
def test_every_real_component_requires_one_actual_review(architecture, review, change):
    if change == "missing":
        review.components.pop()
    elif change == "duplicate":
        review.components.append(deepcopy(review.components[0]))
    elif change == "unknown":
        review.components[1].component_id = "imaginary-replica"
    else:
        review.components[1].disappearance.status = "not_applicable"
    critique, _ = finalize_review(architecture, review)
    assert not critique.approved
    assert critique.required_changes


@pytest.mark.parametrize("group,name", [("planes", "durable_data"), ("messaging", "client_e2ee")])
def test_omitted_plane_or_contract_blocks_approval(architecture, review, group, name):
    getattr(review, group).pop(name)
    critique, _ = finalize_review(architecture, review)
    assert not critique.approved
    assert name.replace("_", " ") in critique.required_changes[0]


def test_passing_label_cannot_hide_required_change(architecture, review):
    review.planes["encryption"].required_change = "Move private keys and wrapping to clients."
    critique, _ = finalize_review(architecture, review)
    assert not critique.approved


def test_review_can_explain_absent_planes_without_forcing_a_messaging_stack(architecture, review):
    for check in [*review.messaging.values(), review.planes["event"], review.planes["media"]]:
        check.status = "not_applicable"
        check.evidence = "This application is an internal CRUD service without messaging or media."
    critique, notes = finalize_review(architecture, review)
    assert critique.approved
    assert not critique.required_changes
    assert len(notes) == 2 * len(architecture.components) + 6 + 9
    assert set(critique.model_dump()) == {
        "approved",
        "confidence",
        "risks",
        "required_changes",
        "unnecessary_components",
    }


def test_empty_evidence_is_not_a_valid_review():
    with pytest.raises(ValidationError):
        ResponsibilityCheck(status="pass", evidence="   ")
