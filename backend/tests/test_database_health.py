from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.routes import router
from app.db.session import get_session


@pytest.fixture
def health_client():
    # The endpoint is tested independently; real startup is checked against Docker.
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    session = AsyncMock()

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, session


def test_health_checks_database(health_client):
    client, session = health_client
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    session.execute.assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [OperationalError(None, None, Exception("sensitive-detail")), OSError(), TimeoutError()],
)
def test_unavailable_database_returns_safe_503(health_client, error):
    client, session = health_client
    session.execute.side_effect = error
    response = client.get("/v1/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
