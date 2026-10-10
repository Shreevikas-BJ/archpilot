from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.queries import QueryBusyError, create_query_run, get_query, list_queries
from app.db.session import get_session
from app.query_schemas import QueryDetail, QuerySummary
from app.schemas import ArchitectureRequest

router = APIRouter(prefix="/queries", tags=["Saved queries"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[QuerySummary])
async def history(session: Session, limit: Annotated[int, Query(ge=1, le=50)] = 30):
    return await list_queries(session, limit=limit)


@router.get("/{query_id}", response_model=QueryDetail)
async def read_query(query_id: UUID, session: Session):
    result = await get_query(session, str(query_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Saved query not found")
    return result


async def enqueue(request: Request, body: ArchitectureRequest, session, query_id=None):
    jobs = getattr(request.app.state, "design_jobs", None)
    if jobs is None:
        raise HTTPException(status_code=503, detail="Design worker is not ready")
    try:
        parent_id, run_id = await create_query_run(session, body, query_id=query_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (QueryBusyError, IntegrityError) as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="This query already has a design running"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    jobs.start(run_id)
    return await get_query(session, parent_id)


@router.post("", response_model=QueryDetail, status_code=202)
async def new_query(request: Request, body: ArchitectureRequest, session: Session):
    return await enqueue(request, body, session)


@router.post("/{query_id}/runs", response_model=QueryDetail, status_code=202)
async def continue_query(
    query_id: UUID, request: Request, body: ArchitectureRequest, session: Session
):
    return await enqueue(request, body, session, str(query_id))
