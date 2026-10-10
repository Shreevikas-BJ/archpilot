from app.schemas import ArchitectureComponent, ArchitectureConnection, ArchitecturePlan
from app.services.mermaid import architecture_to_mermaid


def test_architecture_to_mermaid() -> None:
    plan = ArchitecturePlan(
        title="Example",
        mode="balanced",
        summary="Example architecture",
        components=[
            ArchitectureComponent(
                id="web",
                name="Web UI",
                technology="Next.js",
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
        connections=[ArchitectureConnection(source="web", target="api", label="HTTPS")],
        estimated_monthly_cost="$0",
        assumptions=[],
        tradeoffs=[],
        implementation_steps=[],
        source_urls=[],
    )

    mermaid = architecture_to_mermaid(plan)
    assert "flowchart TD" in mermaid
    assert 'web["Web UI<br/>Next.js"]' in mermaid
    assert "web -->|HTTPS| api" in mermaid
