"""Generate only changes, then validate and review the complete architecture."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from app.schemas import ArchitectureComponent, ArchitectureConnection, ArchitecturePlan


class ArchitectureRevision(BaseModel):
    """Internal text-output contract; omitted fields retain their exact previous values."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    summary: str | None = None
    component_updates: list[ArchitectureComponent] = Field(default_factory=list)
    remove_component_ids: list[str] = Field(default_factory=list)
    connections: list[ArchitectureConnection] | None = None
    estimated_monthly_cost: str | None = None
    assumptions: list[str] | None = None
    tradeoffs: list[str] | None = None
    implementation_steps: list[str] | None = None
    source_urls: list[str] | None = None

    @model_validator(mode="after")
    def validate_merged_plan(self, info: ValidationInfo) -> Self:
        previous = (info.context or {}).get("previous_architecture")
        if previous is not None:
            # Merge errors become Pydantic validation errors, so the ordinary JSON
            # retry handler can correct them before we call the final critic.
            self.apply_to(previous)
        return self

    def apply_to(self, previous: ArchitecturePlan) -> ArchitecturePlan:
        original_ids = {item.id for item in previous.components}
        updates = {item.id: item for item in self.component_updates}
        removed = set(self.remove_component_ids)
        if len(updates) != len(self.component_updates):
            raise ValueError("component_updates must contain unique component ids")
        if len(removed) != len(self.remove_component_ids):
            raise ValueError("remove_component_ids must contain unique component ids")
        if removed - original_ids:
            raise ValueError("Cannot remove an unknown component id")
        if removed & updates.keys():
            raise ValueError("Cannot update and remove the same component")
        payload = previous.model_dump(mode="json")
        payload.update(
            self.model_dump(
                mode="json",
                exclude_none=True,
                exclude={"component_updates", "remove_component_ids"},
            )
        )
        payload["components"] = [
            updates.get(item.id, item).model_dump(mode="json")
            for item in previous.components
            if item.id not in removed
        ] + [
            item.model_dump(mode="json") for key, item in updates.items() if key not in original_ids
        ]
        result = ArchitecturePlan.model_validate(payload)
        if result == previous:
            raise ValueError(
                "Revision must change the architecture to address the required changes"
            )
        return result
