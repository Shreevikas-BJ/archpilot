"""An exact audit shape prevents repeated/missing reviews before verdict synthesis."""

from typing import get_args

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.agents.responsibility import (
    ArchitectureReview,
    MessagingConcern,
    Plane,
    ResponsibilityCheck,
)
from app.schemas import ArchitecturePlan, Critique


def _required_map(name: str, keys, value_type: type[BaseModel]) -> type[BaseModel]:
    # Aliases support any valid component id, including names reserved by BaseModel.
    return create_model(
        name,
        __config__=ConfigDict(extra="forbid"),
        **{f"item_{index}": (value_type, Field(alias=key)) for index, key in enumerate(keys)},
    )


PlaneChecks = _required_map("PlaneChecks", get_args(Plane), ResponsibilityCheck)
MessagingChecks = _required_map("MessagingChecks", get_args(MessagingConcern), ResponsibilityCheck)


def review_output_type(architecture: ArchitecturePlan) -> type[BaseModel]:
    ids = [component.id for component in architecture.components]
    if len(ids) != len(set(ids)):
        raise ValueError("Architecture component ids must be unique before review")
    components = _required_map("ExactComponentChecks", ids, ResponsibilityCheck)
    return create_model(
        "ArchitectureReviewOutput",
        __base__=Critique,
        __config__=ConfigDict(extra="forbid"),
        component_responsibilities=(components, ...),
        component_disappearances=(components, ...),
        planes=(PlaneChecks, ...),
        messaging=(MessagingChecks, ...),
    )


def to_architecture_review(output: BaseModel) -> ArchitectureReview:
    payload = output.model_dump(mode="json", by_alias=True)
    responsibilities = payload.pop("component_responsibilities")
    disappearances = payload.pop("component_disappearances")
    payload["components"] = [
        {
            "component_id": component_id,
            "responsibility": check,
            "disappearance": disappearances[component_id],
        }
        for component_id, check in responsibilities.items()
    ]
    return ArchitectureReview.model_validate(payload)
