import pytest
from pydantic import ValidationError

from app.schemas import ArchitectureComponent, ArchitectureConnection, ArchitecturePlan, ResearchPlan


def test_research_queries_are_deduplicated() -> None:
    plan = ResearchPlan(queries=["A query", "B query", "C query", "a QUERY"])
    assert plan.queries == ["A query", "B query", "C query"]


def test_architecture_rejects_unknown_connection_ids() -> None:
    with pytest.raises(ValidationError):
        ArchitecturePlan(
            title="Bad",
            mode="balanced",
            summary="Bad architecture",
            components=[
                ArchitectureComponent(
                    id="web",
                    name="Web",
                    technology="Next",
                    category="frontend",
                    purpose="UI",
                    deployment="Vercel",
                ),
                ArchitectureComponent(
                    id="api",
                    name="API",
                    technology="FastAPI",
                    category="backend",
                    purpose="API",
                    deployment="Local",
                ),
            ],
            connections=[ArchitectureConnection(source="web", target="missing")],
            estimated_monthly_cost="$0",
            assumptions=[],
            tradeoffs=[],
            implementation_steps=[],
            source_urls=[],
        )
