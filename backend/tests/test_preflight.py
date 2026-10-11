import json

import httpx

from app.config import Settings
from app.preflight import check_llm, check_search


def settings(**overrides) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user@database/archpilot",
        llm_base_url="https://models.internal.example/v1/",
        llm_api_key="private-test-value",
        searxng_url="https://search.internal.example/",
        _env_file=None,
        **overrides,
    )


async def test_preflight_accepts_remote_openai_compatible_model_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://models.internal.example/v1/models"
        assert request.headers["Authorization"] == "Bearer private-test-value"
        return httpx.Response(200, json={"data": [{"id": "bonsai"}]})

    result = await check_llm(settings(), transport=httpx.MockTransport(handler))
    assert result.ok
    assert "OpenAI-compatible" in result.detail


async def test_preflight_accepts_remote_searxng_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.url.params["format"] == "json"
        return httpx.Response(200, content=json.dumps({"results": []}))

    result = await check_search(settings(), transport=httpx.MockTransport(handler))
    assert result.ok


async def test_preflight_reports_safe_error_types_without_endpoint_or_secret():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="private-test-value")

    result = await check_llm(settings(), transport=httpx.MockTransport(handler))
    assert not result.ok
    assert result.detail == "HTTPStatusError"
    assert "private-test-value" not in result.detail
    assert "models.internal.example" not in result.detail
