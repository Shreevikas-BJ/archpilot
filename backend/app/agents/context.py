"""Keep research excerpts bounded without changing the saved source records."""

from collections import defaultdict
from itertools import zip_longest

from app.schemas import EvaluationReport, SearchSource


def evidence_context(sources: list[SearchSource], *, limit: int = 12) -> list[dict[str, str]]:
    groups: dict[str, list[SearchSource]] = defaultdict(list)
    for source in sources:
        groups[source.query].append(source)
    result = []
    seen = set()
    for row in zip_longest(*groups.values()):
        for source in row:
            if source is None or source.url in seen:
                continue
            # Never truncate a citation into a different URL; retain it in the saved sources.
            if len(source.url) > 1024:
                continue
            seen.add(source.url)
            result.append(
                {
                    "title": source.title[:160],
                    "url": source.url,
                    "snippet": source.snippet[:400],
                }
            )
            if len(result) == limit:
                return result
    return result


def evaluation_context(evaluation: EvaluationReport) -> dict:
    """The full evaluation is saved; downstream agents need role decisions, not duplicate prose."""
    return {
        "industry_baseline": evaluation.industry_baseline[:800],
        "candidates": [
            {
                "name": item.name,
                "role": item.role,
                "fit": item.fit,
                "rationale": item.rationale[:500],
                "evidence_urls": item.evidence_urls,
            }
            for item in evaluation.candidates
        ],
        "key_tradeoffs": evaluation.key_tradeoffs,
        "avoid_list": evaluation.avoid_list,
    }
