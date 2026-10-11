import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.json_output import AgentJSONError
from app.agents.orchestrator import ArchitectureOrchestrator
from app.config import Settings, get_settings
from app.db.queries import import_legacy_runs
from app.db.repository import get_run, list_runs, save_run
from app.db.session import get_session
from app.schemas import (
    ArchitectureRequest,
    ArchitectureResponse,
    ArchitectureRunSummary,
    SavedArchitectureRun,
)
from app.services.search import SearchServiceError, SearxNGSearchService

router = APIRouter()


@router.get("/health")
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    try:
        async with asyncio.timeout(5):
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError):
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {
        "status": "ok",
        "database": "ok",
        "runtime": settings.public_runtime,
    }


@router.get("/architectures", response_model=list[ArchitectureRunSummary])
async def architecture_history(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[ArchitectureRunSummary]:
    try:
        rows = await list_runs(session, limit=limit)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    summaries = []
    for row in rows:
        payload = row.response_payload or {}
        title = (payload.get("architecture") or {}).get("title")
        title = title or (payload.get("requirements") or {}).get("problem_summary")
        summaries.append(
            ArchitectureRunSummary(
                run_id=row.id,
                title=title or row.problem[:100],
                mode=row.mode,
                status=row.status,
                created_at=row.created_at,
            )
        )
    return summaries


@router.get("/architectures/{run_id}", response_model=SavedArchitectureRun)
async def saved_architecture(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SavedArchitectureRun:
    try:
        row = await get_run(session, str(run_id))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    if row is None or row.response_payload is None:
        raise HTTPException(status_code=404, detail="Saved architecture not found")
    return SavedArchitectureRun(
        request=ArchitectureRequest.model_validate(row.request_payload),
        response=ArchitectureResponse.model_validate(row.response_payload),
        created_at=row.created_at,
    )


@router.post("/architectures", response_model=ArchitectureResponse)
async def create_architecture(
    request: ArchitectureRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ArchitectureResponse:
    orchestrator = ArchitectureOrchestrator(
        settings=settings,
        search_service=SearxNGSearchService(settings),
    )
    try:
        response = await orchestrator.run(request)
    except SearchServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentJSONError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ModelHTTPError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ModelHTTPError",
                "status_code": exc.status_code,
                "body": exc.body,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Architecture generation failed: {type(exc).__name__}",
        ) from exc

    await save_run(session, run_id=response.run_id, request=request, response=response)
    await import_legacy_runs(session, run_id=response.run_id)
    return response
