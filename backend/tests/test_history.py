from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import routes
from app.db.session import get_session
from app.schemas import ArchitectureResponse, RequirementsAnalysis


@pytest.fixture
def history_client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    with TestClient(app) as client:
        yield client


def saved_row():
    run_id = str(uuid4())
    response = ArchitectureResponse(
        run_id=run_id,
        status="needs_clarification",
        requirements=RequirementsAnalysis(
            problem_summary="Staff directory",
            business_goal="Find colleagues",
            users_and_scale="Five staff",
            latency_expectation="One second",
            data_characteristics="Contact records",
            security_and_compliance="VPN",
        ),
        clarifying_questions=["What is your budget?"],
    )
    return SimpleNamespace(
        id=run_id,
        problem="Build an internal staff directory",
        mode="balanced",
        status=response.status,
        created_at=datetime.now(UTC),
        request_payload={
            "problem": "Build an internal staff directory",
            "mode": "balanced",
            "clarifications": {},
        },
        response_payload=response.model_dump(mode="json"),
    )


def test_history_returns_summaries_without_full_payload(history_client, monkeypatch):
    row = saved_row()
    listing = AsyncMock(return_value=[row])
    monkeypatch.setattr(routes, "list_runs", listing)
    response = history_client.get("/v1/architectures?limit=5")
    assert response.status_code == 200
    assert response.json() == [
        {
            "run_id": row.id,
            "title": "Staff directory",
            "mode": "balanced",
            "status": "needs_clarification",
            "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
        }
    ]
    assert listing.await_args.kwargs == {"limit": 5}


def test_saved_run_preserves_request_and_response(history_client, monkeypatch):
    row = saved_row()
    reading = AsyncMock(return_value=row)
    monkeypatch.setattr(routes, "get_run", reading)
    response = history_client.get(f"/v1/architectures/{row.id}")
    assert response.status_code == 200
    assert response.json()["response"] == row.response_payload
    assert response.json()["request"] == row.request_payload
    assert reading.await_args.args[1] == row.id


def test_missing_saved_run_is_404(history_client, monkeypatch):
    monkeypatch.setattr(routes, "get_run", AsyncMock(return_value=None))
    response = history_client.get(f"/v1/architectures/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Saved architecture not found"}


@pytest.mark.parametrize("path", ["?limit=0", "?limit=51", "/invalid-id"])
def test_invalid_history_input_is_rejected(history_client, path):
    assert history_client.get("/v1/architectures" + path).status_code == 422


@pytest.mark.parametrize("endpoint,method", [("", "list_runs"), (f"/{uuid4()}", "get_run")])
def test_history_database_errors_are_safe(history_client, monkeypatch, endpoint, method):
    monkeypatch.setattr(
        routes,
        method,
        AsyncMock(side_effect=OperationalError(None, None, Exception("private connection detail"))),
    )
    response = history_client.get("/v1/architectures" + endpoint)
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
