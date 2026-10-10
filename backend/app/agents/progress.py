from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from app.schemas import RequirementsAnalysis

PipelineStage = Literal[
    "queued",
    "requirements",
    "research",
    "search",
    "evaluation",
    "architecture",
    "critique",
    "revision",
    "final_review",
    "saving",
    "needs_clarification",
    "complete",
    "failed",
]


class PipelineProgress(BaseModel):
    stage: PipelineStage
    requirements: RequirementsAnalysis | None = None


ProgressCallback = Callable[[PipelineProgress], Awaitable[None]]
