from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.proxy_auth import ProxyTokenMiddleware


def make_client(token: str | None) -> TestClient:
    app = FastAPI()
    app.add_middleware(ProxyTokenMiddleware, token=token, api_prefix="/v1")

    @app.get("/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/docs-check")
    async def docs_check():
        return {"status": "ok"}

    return TestClient(app)


def test_proxy_token_protects_api_routes():
    with make_client("demo-secret") as client:
        assert client.get("/v1/health").status_code == 401
        assert (
            client.get(
                "/v1/health", headers={"X-ArchPilot-Proxy-Token": "wrong"}
            ).status_code
            == 401
        )
        response = client.get(
            "/v1/health", headers={"X-ArchPilot-Proxy-Token": "demo-secret"}
        )
        assert response.status_code == 200


def test_proxy_token_is_optional_and_only_applies_to_api_prefix():
    with make_client(None) as client:
        assert client.get("/v1/health").status_code == 200
    with make_client("demo-secret") as client:
        assert client.get("/docs-check").status_code == 200
