from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ArchitectureMode = Literal["cost_effective", "balanced", "high_performance"]


class ArchitectureRequest(BaseModel):
    problem: str = Field(min_length=20, max_length=8000)
    mode: ArchitectureMode = "balanced"
    clarifications: dict[str, str] = Field(default_factory=dict)


class RequirementsAnalysis(BaseModel):
    problem_summary: str
    business_goal: str
    users_and_scale: str
    latency_expectation: str
    data_characteristics: str
    security_and_compliance: str
    existing_stack: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list, max_length=5)


class ResearchPlan(BaseModel):
    queries: list[str] = Field(min_length=3, max_length=8)
    focus_areas: list[str] = Field(default_factory=list)

    @field_validator("queries")
    @classmethod
    def deduplicate_queries(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for query in value:
            query = query.strip()
            key = query.casefold()
            if query and key not in seen:
                seen.add(key)
                deduped.append(query)
        if len(deduped) < 3:
            raise ValueError("At least three unique research queries are required")
        return deduped


class SearchSource(BaseModel):
    title: str
    url: str
    snippet: str = ""
    engine: str | None = None
    query: str


class ToolEvaluation(BaseModel):
    name: str
    role: str
    maturity: Literal["emerging", "growing", "established"]
    cost_profile: str
    performance_profile: str
    operational_complexity: Literal["low", "medium", "high"]
    scalability: str
    strengths: list[str]
    weaknesses: list[str]
    evidence_urls: list[str] = Field(default_factory=list)
    fit: Literal["poor", "conditional", "good", "excellent"]
    rationale: str


class EvaluationReport(BaseModel):
    industry_baseline: str
    candidates: list[ToolEvaluation]
    key_tradeoffs: list[str]
    avoid_list: list[str] = Field(default_factory=list)


class ArchitectureComponent(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,40}$")
    name: str
    technology: str
    category: str
    purpose: str
    deployment: str


class ArchitectureConnection(BaseModel):
    source: str
    target: str
    label: str = ""


class ArchitecturePlan(BaseModel):
    title: str
    mode: ArchitectureMode
    summary: str
    components: list[ArchitectureComponent] = Field(min_length=2, max_length=30)
    connections: list[ArchitectureConnection] = Field(min_length=1, max_length=60)
    estimated_monthly_cost: str
    assumptions: list[str]
    tradeoffs: list[str]
    implementation_steps: list[str]
    source_urls: list[str] = Field(default_factory=list)

    @field_validator("connections")
    @classmethod
    def validate_connections(
        cls, value: list[ArchitectureConnection], info
    ) -> list[ArchitectureConnection]:
        data = info.data
        components = data.get("components", [])
        ids = {component.id for component in components}
        missing = [
            f"{edge.source}->{edge.target}"
            for edge in value
            if edge.source not in ids or edge.target not in ids
        ]
        if missing:
            raise ValueError(f"Connections reference unknown component ids: {', '.join(missing)}")
        return value


class Critique(BaseModel):
    approved: bool
    confidence: float = Field(ge=0, le=1)
    risks: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    unnecessary_components: list[str] = Field(default_factory=list)


class ArchitectureResponse(BaseModel):
    run_id: str
    status: Literal["needs_clarification", "complete"]
    requirements: RequirementsAnalysis
    clarifying_questions: list[str] = Field(default_factory=list)
    research_sources: list[SearchSource] = Field(default_factory=list)
    evaluation: EvaluationReport | None = None
    architecture: ArchitecturePlan | None = None
    critique: Critique | None = None
    mermaid: str | None = None


class ArchitectureRunSummary(BaseModel):
    run_id: str
    title: str
    mode: ArchitectureMode
    status: Literal["needs_clarification", "complete"]
    created_at: datetime


class SavedArchitectureRun(BaseModel):
    request: ArchitectureRequest
    response: ArchitectureResponse
    created_at: datetime
