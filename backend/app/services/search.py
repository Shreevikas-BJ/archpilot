import asyncio

import httpx

from app.config import Settings
from app.schemas import SearchSource


class SearchServiceError(RuntimeError):
    pass


class SearxNGSearchService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def search(self, query: str) -> list[SearchSource]:
        params = {
            "q": query,
            "format": "json",
            "language": "en",
            "safesearch": 1,
        }
        timeout = httpx.Timeout(self._settings.search_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self._settings.searxng_url.rstrip('/')}/search", params=params
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchServiceError(f"SearXNG request failed: {exc}") from exc

        payload = response.json()
        results = payload.get("results", [])[: self._settings.search_results_per_query]
        return [
            SearchSource(
                title=str(item.get("title") or "Untitled"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or ""),
                engine=str(item.get("engine")) if item.get("engine") else None,
                query=query,
            )
            for item in results
            if item.get("url")
        ]

    async def search_many(self, queries: list[str]) -> list[SearchSource]:
        batches = await asyncio.gather(*(self.search(query) for query in queries))
        deduped: list[SearchSource] = []
        seen_urls: set[str] = set()
        for batch in batches:
            for source in batch:
                normalized = source.url.rstrip("/")
                if normalized not in seen_urls:
                    seen_urls.add(normalized)
                    deduped.append(source)
        return deduped
