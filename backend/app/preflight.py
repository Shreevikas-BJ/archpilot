"""Validate the configured database, model, and search integrations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings


@dataclass(frozen=True)
class CheckResult:
    service: str
    ok: bool
    detail: str


async def check_database(settings: Settings) -> CheckResult:
    engine = create_async_engine(
        settings.database_url, pool_pre_ping=True, connect_args={"timeout": 10}
    )
    try:
        async with asyncio.timeout(15), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return CheckResult("PostgreSQL", True, "connection and query succeeded")
    except Exception as exc:
        return CheckResult("PostgreSQL", False, type(exc).__name__)
    finally:
        await engine.dispose()


async def check_llm(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> CheckResult:
    url = settings.llm_base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        async with httpx.AsyncClient(transport=transport, timeout=20) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("model endpoint did not return a JSON object")
        return CheckResult("LLM", True, "OpenAI-compatible /models succeeded")
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult("LLM", False, type(exc).__name__)


async def check_search(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> CheckResult:
    url = settings.searxng_url.rstrip("/") + "/search"
    try:
        async with httpx.AsyncClient(transport=transport, timeout=20) as client:
            response = await client.get(
                url, params={"q": "ArchPilot connectivity", "format": "json"}
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("search endpoint did not return SearXNG JSON")
        return CheckResult("SearXNG", True, "JSON search succeeded")
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult("SearXNG", False, type(exc).__name__)


async def run_preflight(settings: Settings) -> list[CheckResult]:
    return list(
        await asyncio.gather(
            check_database(settings),
            check_llm(settings),
            check_search(settings),
        )
    )


async def main() -> int:
    settings = Settings()
    print(
        f"ArchPilot preflight: {settings.deployment_label} "
        f"({settings.deployment_mode})"
    )
    results = await run_preflight(settings)
    for result in results:
        state = "PASS" if result.ok else "FAIL"
        print(f"[{state}] {result.service}: {result.detail}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    raise SystemExit(asyncio.run(main()))
