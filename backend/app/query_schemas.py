from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.progress import PipelineStage
from app.schemas import ArchitectureRequest, ArchitectureResponse, RequirementsAnalysis

RunStatus = Literal["queued", "running", "needs_clarification", "complete", "failed"]


class ProgressEvent(BaseModel):
    stage: PipelineStage
    at: datetime


class QueryRunDetail(BaseModel):
    run_id: str
    request: ArchitectureRequest
    status: RunStatus
    stage: PipelineStage
    requirements: RequirementsAnalysis | None = None
    response: ArchitectureResponse | None = None
    events: list[ProgressEvent] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class QuerySummary(BaseModel):
    query_id: str
    title: str
    problem: str
    status: RunStatus
    stage: PipelineStage
    run_count: int
    created_at: datetime
    updated_at: datetime


class QueryDetail(BaseModel):
    query_id: str
    title: str
    problem: str
    runs: list[QueryRunDetail]
    created_at: datetime
    updated_at: datetime
