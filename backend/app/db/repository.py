from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArchitectureRun
from app.schemas import ArchitectureRequest, ArchitectureResponse


async def save_run(
    session: AsyncSession,
    *,
    run_id: str,
    request: ArchitectureRequest,
    response: ArchitectureResponse,
) -> None:
    row = ArchitectureRun(
        id=run_id,
        problem=request.problem,
        mode=request.mode,
        status=response.status,
        request_payload=request.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    session.add(row)
    await session.commit()


async def list_runs(session: AsyncSession, *, limit: int) -> list[ArchitectureRun]:
    rows = await session.scalars(
        select(ArchitectureRun)
        .where(ArchitectureRun.response_payload.is_not(None))
        .order_by(ArchitectureRun.created_at.desc(), ArchitectureRun.id.desc())
        .limit(limit)
    )
    return list(rows.all())


async def get_run(session: AsyncSession, run_id: str) -> ArchitectureRun | None:
    return await session.get(ArchitectureRun, run_id)
