"""Opt-in PostgreSQL tests in disposable schemas, never in the user's live tables."""

import asyncio
import os
import re
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.json_output import AgentJSONError
from app.agents.progress import PipelineProgress
from app.api.queries import router
from app.config import Settings
from app.db.base import Base
from app.db.models import ArchitectureRun, QueryRun
from app.db.queries import create_query_run, import_legacy_runs, mark_interrupted_runs
from app.db.session import get_session
from app.schemas import ArchitectureRequest, ArchitectureResponse, RequirementsAnalysis
from app.services import design_jobs

pytestmark = pytest.mark.skipif(
    os.environ.get("ARCHPILOT_DATABASE_TESTS") != "1",
    reason="Set ARCHPILOT_DATABASE_TESTS=1 to test isolated schemas in local PostgreSQL",
)
BRIEF = "Build a small internal employee directory."
REQUIREMENTS = RequirementsAnalysis(
    problem_summary="Employee directory",
    business_goal="Find coworkers",
    users_and_scale="Five staff",
    latency_expectation="One second",
    data_characteristics="Contact records",
    security_and_compliance="VPN only",
    hard_constraints=["No extra hosting cost"],
    clarifying_questions=["What is your budget?"],
)


def response_for(run_id, complete=False):
    payload = {
        "run_id": run_id,
        "status": "complete" if complete else "needs_clarification",
        "requirements": REQUIREMENTS.model_dump(),
        "clarifying_questions": [] if complete else ["What is your budget?"],
    }
    if complete:
        payload.update(
            architecture={
                "title": "Employee directory",
                "mode": "balanced",
                "summary": "API and database",
                "components": [
                    {
                        "id": name,
                        "name": name,
                        "technology": tech,
                        "category": name,
                        "purpose": "Serve the directory",
                        "deployment": "Docker",
                    }
                    for name, tech in [("api", "FastAPI"), ("db", "PostgreSQL")]
                ],
                "connections": [{"source": "api", "target": "db"}],
                "estimated_monthly_cost": "$0",
                "assumptions": [],
                "tradeoffs": [],
                "implementation_steps": ["Deploy"],
            },
            critique={"approved": True, "confidence": 0.9},
            mermaid="flowchart TD\napi-->db",
        )
    return ArchitectureResponse.model_validate(payload)


@pytest.fixture
async def database_client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings()
    schema = "archpilot_test_" + uuid4().hex
    assert re.fullmatch(r"archpilot_test_[0-9a-f]{32}", schema)
    admin = create_async_engine(settings.database_url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        settings.database_url,
        connect_args={
            "server_settings": {"search_path": schema},
        },
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    jobs = design_jobs.DesignJobs(settings, factory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        app.state.design_jobs = jobs

        async def session():
            async with factory() as value:
                yield value

        app.dependency_overrides[get_session] = session
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, factory, jobs
    finally:
        await jobs.close()
        await engine.dispose()
        # The exact random schema created by this fixture is the only deletion target.
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def wait_state(client, query_id, predicate):
    for _ in range(100):
        detail = (await client.get(f"/v1/queries/{query_id}")).json()
        if predicate(detail["runs"][-1]):
            return detail
        await asyncio.sleep(0.02)
    raise AssertionError("Worker did not publish the expected saved state")


def use_fake(monkeypatch, run):
    monkeypatch.setattr(
        design_jobs, "ArchitectureOrchestrator", lambda **_: SimpleNamespace(run=run)
    )


async def test_progress_is_persisted_before_completion_and_duplicate_runs_are_rejected(
    database_client, monkeypatch
):
    client, factory, _ = database_client
    release = asyncio.Event()

    async def run(request, *, run_id, progress):
        await progress(PipelineProgress(stage="requirements"))
        await progress(PipelineProgress(stage="research", requirements=REQUIREMENTS))
        await release.wait()
        await progress(PipelineProgress(stage="architecture"))
        return response_for(run_id, complete=True)

    use_fake(monkeypatch, run)
    created = await client.post("/v1/queries", json={"problem": BRIEF})
    assert created.status_code == 202
    query_id = created.json()["query_id"]
    detail = await wait_state(client, query_id, lambda run: run["stage"] == "research")
    assert detail["runs"][0]["requirements"]["hard_constraints"] == ["No extra hosting cost"]
    assert detail["runs"][0]["response"] is None
    duplicate = await client.post(f"/v1/queries/{query_id}/runs", json={"problem": BRIEF})
    assert duplicate.status_code == 409
    release.set()
    done = await wait_state(client, query_id, lambda run: run["status"] == "complete")
    async with factory() as session:
        archived = await session.get(ArchitectureRun, done["runs"][0]["run_id"])
        assert archived.response_payload == done["runs"][0]["response"]
    assert (await client.get("/v1/queries")).json()[0]["run_count"] == 1


async def test_clarifications_and_full_design_versions_stay_under_original_query(
    database_client, monkeypatch
):
    client, _, _ = database_client

    async def run(request, *, run_id, progress):
        await progress(PipelineProgress(stage="requirements", requirements=REQUIREMENTS))
        return response_for(run_id, complete=bool(request.clarifications))

    use_fake(monkeypatch, run)
    created = (await client.post("/v1/queries", json={"problem": BRIEF})).json()
    query_id = created["query_id"]
    first = await wait_state(client, query_id, lambda run: run["status"] == "needs_clarification")
    initial_run = first["runs"][0]
    for answers in [{"What is your budget?": "$0"}, {"Recovery target?": "One day"}]:
        continued = await client.post(
            f"/v1/queries/{query_id}/runs", json={"problem": BRIEF, "clarifications": answers}
        )
        assert continued.status_code == 202
        done = await wait_state(client, query_id, lambda run: run["status"] == "complete")
    assert done["query_id"] == query_id and done["problem"] == BRIEF
    assert len(done["runs"]) == 3 and done["runs"][0] == initial_run
    assert done["runs"][2]["request"]["clarifications"] == {
        "What is your budget?": "$0",
        "Recovery target?": "One day",
    }
    assert all(run["requirements"] for run in done["runs"])
    assert all(run["response"]["architecture"] for run in done["runs"][1:])
    assert len((await client.get("/v1/queries")).json()) == 1
    changed = await client.post(
        f"/v1/queries/{query_id}/runs",
        json={"problem": "Build an entirely different public social network."},
    )
    assert changed.status_code == 422


async def test_failure_keeps_classification_and_allows_retry_in_same_query(
    database_client, monkeypatch
):
    client, _, _ = database_client

    async def fail(request, *, run_id, progress):
        await progress(PipelineProgress(stage="evaluation", requirements=REQUIREMENTS))
        raise AgentJSONError("Evaluation failed after three JSON attempts")

    use_fake(monkeypatch, fail)
    query_id = (await client.post("/v1/queries", json={"problem": BRIEF})).json()["query_id"]
    failed = await wait_state(client, query_id, lambda run: run["status"] == "failed")
    assert failed["runs"][0]["requirements"] is not None
    assert "three JSON attempts" in failed["runs"][0]["error"]

    async def recover(request, *, run_id, progress):
        return response_for(run_id, complete=True)

    use_fake(monkeypatch, recover)
    assert (
        await client.post(f"/v1/queries/{query_id}/runs", json={"problem": BRIEF})
    ).status_code == 202
    recovered = await wait_state(client, query_id, lambda run: run["status"] == "complete")
    assert len(recovered["runs"]) == 2
    assert recovered["runs"][0] == failed["runs"][0]


async def test_legacy_import_is_idempotent_and_preserves_archives(database_client):
    client, factory, _ = database_client
    run_id = str(uuid4())
    payload = response_for(run_id, complete=True).model_dump(mode="json")
    async with factory() as session:
        session.add(
            ArchitectureRun(
                id=run_id,
                problem=BRIEF,
                mode="balanced",
                status="complete",
                request_payload={"problem": BRIEF},
                response_payload=payload,
            )
        )
        await session.commit()
        await import_legacy_runs(session)
        await import_legacy_runs(session)
    saved = (await client.get(f"/v1/queries/{run_id}")).json()
    assert len(saved["runs"]) == 1 and saved["runs"][0]["response"] == payload


async def test_legacy_clarification_rounds_are_grouped_with_working_old_links(database_client):
    client, factory, _ = database_client
    ids = [str(uuid4()), str(uuid4())]
    async with factory() as session:
        for index, run_id in enumerate(ids):
            payload = response_for(run_id, complete=bool(index)).model_dump(mode="json")
            session.add(
                ArchitectureRun(
                    id=run_id,
                    problem=BRIEF,
                    mode="balanced",
                    status=payload["status"],
                    request_payload={
                        "problem": BRIEF,
                        "clarifications": {"Budget?": "$0"} if index else {},
                    },
                    response_payload=payload,
                )
            )
            await session.commit()
        await import_legacy_runs(session)
        await import_legacy_runs(session)
    listing = (await client.get("/v1/queries?limit=1")).json()
    assert len(listing) == 1 and listing[0]["run_count"] == 2
    canonical = listing[0]["query_id"]
    assert canonical == ids[0]
    for old_id in ids:
        saved = (await client.get(f"/v1/queries/{old_id}")).json()
        assert saved["query_id"] == canonical
        assert [run["run_id"] for run in saved["runs"]] == ids
        assert saved["runs"][1]["request"]["clarifications"] == {"Budget?": "$0"}
    async with factory() as session:
        parent_id, _ = await create_query_run(
            session, ArchitectureRequest(problem=BRIEF), query_id=ids[1]
        )
        assert parent_id == canonical


async def test_restart_marks_interrupted_jobs_without_losing_classifications(database_client):
    client, factory, jobs = database_client
    jobs.start = lambda _: None  # Simulate a queued run when the server stops.
    query_id = (await client.post("/v1/queries", json={"problem": BRIEF})).json()["query_id"]
    async with factory() as session:
        run = await session.scalar(select(QueryRun).where(QueryRun.query_id == query_id))
        run.requirements_payload = REQUIREMENTS.model_dump(mode="json")
        await session.commit()
        await mark_interrupted_runs(session)
    saved = (await client.get(f"/v1/queries/{query_id}")).json()
    assert saved["runs"][0]["status"] == "failed"
    assert saved["runs"][0]["requirements"]["business_goal"] == "Find coworkers"
    assert "restarted" in saved["runs"][0]["error"]
