import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArchitectureRun, DesignQuery, QueryRun
from app.query_schemas import QueryDetail, QueryRunDetail, QuerySummary
from app.schemas import ArchitectureRequest

ACTIVE_STATUSES = ("queued", "running")


class QueryBusyError(ValueError):
    pass


async def import_legacy_runs(session: AsyncSession, run_id: str | None = None) -> None:
    """Add parents for existing archives without altering or replacing any archive."""
    statement = select(ArchitectureRun).where(~exists().where(QueryRun.id == ArchitectureRun.id))
    if run_id:
        statement = statement.where(ArchitectureRun.id == run_id)
    for row in await session.scalars(statement):
        if not row.response_payload:
            continue
        payload = row.response_payload
        requirements = payload.get("requirements")
        title = (payload.get("architecture") or {}).get("title")
        title = title or (requirements or {}).get("problem_summary") or row.problem[:100]
        await session.execute(
            insert(DesignQuery)
            .values(
                id=row.id,
                problem=row.problem,
                title=title,
                created_at=row.created_at,
                updated_at=row.created_at,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await session.execute(
            insert(QueryRun)
            .values(
                id=row.id,
                query_id=row.id,
                request_payload=row.request_payload,
                status=row.status,
                stage=row.status,
                requirements_payload=requirements,
                events=[{"stage": row.status, "at": row.created_at.isoformat()}],
                created_at=row.created_at,
                updated_at=row.created_at,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    await _group_legacy_queries(session)
    await session.commit()


async def _group_legacy_queries(session: AsyncSession) -> None:
    # Legacy roots have the archive's ID. New explicit queries always have their own ID.
    parents = await session.scalars(
        select(DesignQuery)
        .join(ArchitectureRun, ArchitectureRun.id == DesignQuery.id)
        .order_by(DesignQuery.created_at, DesignQuery.id)
    )
    groups: dict[str, list[DesignQuery]] = {}
    for parent in parents:
        groups.setdefault(parent.problem, []).append(parent)
    for matching in groups.values():
        if len(matching) < 2:
            continue
        runs = list(
            await session.scalars(
                select(QueryRun)
                .where(QueryRun.query_id.in_([parent.id for parent in matching]))
                .order_by(QueryRun.created_at, QueryRun.id)
            )
        )
        if not runs or any(run.status in ACTIVE_STATUSES for run in runs):
            continue
        canonical = matching[0]
        for run in runs:
            run.query_id = canonical.id
        canonical.updated_at = runs[-1].updated_at
        archive = await session.get(ArchitectureRun, runs[-1].id)
        if archive and archive.response_payload:
            payload = archive.response_payload
            canonical.title = (payload.get("architecture") or {}).get("title") or payload[
                "requirements"
            ]["problem_summary"]
        # Keep empty alias parents so old saved links can resolve to the canonical query.
    await session.flush()


async def list_queries(session: AsyncSession, *, limit: int = 30) -> list[QuerySummary]:
    parents = list(
        await session.scalars(
            select(DesignQuery)
            .where(exists().where(QueryRun.query_id == DesignQuery.id))
            .order_by(DesignQuery.updated_at.desc(), DesignQuery.id.desc())
            .limit(limit)
        )
    )
    if not parents:
        return []
    rows = await session.execute(
        select(QueryRun.query_id, QueryRun.status, QueryRun.stage)
        .where(QueryRun.query_id.in_([parent.id for parent in parents]))
        .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
    )
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.query_id, []).append(row)
    return [
        QuerySummary(
            query_id=parent.id,
            title=parent.title,
            problem=parent.problem,
            status=grouped[parent.id][0].status,
            stage=grouped[parent.id][0].stage,
            run_count=len(grouped[parent.id]),
            created_at=parent.created_at,
            updated_at=parent.updated_at,
        )
        for parent in parents
        if parent.id in grouped
    ]


async def get_query(session: AsyncSession, query_id: str) -> QueryDetail | None:
    parent = await session.get(DesignQuery, query_id)
    if parent is None:
        return None
    alias = await session.get(QueryRun, query_id)
    if alias and alias.query_id != query_id:
        return await get_query(session, alias.query_id)
    rows = await session.execute(
        select(QueryRun, ArchitectureRun)
        .outerjoin(ArchitectureRun, ArchitectureRun.id == QueryRun.id)
        .where(QueryRun.query_id == query_id)
        .order_by(QueryRun.created_at, QueryRun.id)
    )
    return QueryDetail(
        query_id=parent.id,
        title=parent.title,
        problem=parent.problem,
        created_at=parent.created_at,
        updated_at=parent.updated_at,
        runs=[
            QueryRunDetail(
                run_id=run.id,
                request=run.request_payload,
                status=run.status,
                stage=run.stage,
                requirements=run.requirements_payload,
                response=archive.response_payload if archive else None,
                events=run.events,
                error=run.error,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            for run, archive in rows
        ],
    )


async def create_query_run(
    session: AsyncSession,
    request: ArchitectureRequest,
    *,
    query_id: str | None = None,
) -> tuple[str, str]:
    now = datetime.now(UTC)
    if query_id:
        alias = await session.get(QueryRun, query_id)
        if alias and alias.query_id != query_id:
            query_id = alias.query_id
        parent = await session.scalar(
            select(DesignQuery).where(DesignQuery.id == query_id).with_for_update()
        )
        if parent is None:
            raise LookupError("Saved query not found")
        if request.problem != parent.problem:
            raise ValueError(
                "The original query cannot change. Start a new query for a different brief."
            )
        previous = await session.scalar(
            select(QueryRun)
            .where(QueryRun.query_id == query_id)
            .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
            .limit(1)
        )
        if previous and previous.status in ACTIVE_STATUSES:
            raise QueryBusyError("This query already has a design running")
        if previous:
            # Keep earlier answers in every new round, even after reopening the query.
            request = request.model_copy(
                update={
                    "clarifications": {
                        **previous.request_payload.get("clarifications", {}),
                        **request.clarifications,
                    }
                }
            )
    else:
        query_id = str(uuid.uuid4())
        parent = DesignQuery(
            id=query_id,
            problem=request.problem,
            title=request.problem[:100],
            created_at=now,
            updated_at=now,
        )
        session.add(parent)
        await session.flush()
    parent.updated_at = now
    run_id = str(uuid.uuid4())
    session.add(
        QueryRun(
            id=run_id,
            query_id=query_id,
            request_payload=request.model_dump(mode="json"),
            status="queued",
            stage="queued",
            events=[{"stage": "queued", "at": now.isoformat()}],
            created_at=now,
            updated_at=now,
        )
    )
    await session.commit()
    return query_id, run_id


async def mark_interrupted_runs(session: AsyncSession) -> None:
    """A server restart must never leave a saved query displaying stale progress."""
    now = datetime.now(UTC)
    for run in await session.scalars(select(QueryRun).where(QueryRun.status.in_(ACTIVE_STATUSES))):
        run.status = "failed"
        run.stage = "failed"
        run.error = "The backend restarted during this run. Retry within this query to continue."
        run.updated_at = now
        run.events = [*run.events, {"stage": "failed", "at": now.isoformat()}]
    await session.commit()
