import json

from app.agents.context import evidence_context
from app.schemas import SearchSource


def test_large_research_results_are_bounded_and_cover_each_query_without_mutating_sources():
    sources = [
        SearchSource(
            title=f"Topic {topic} result {result}",
            url=f"https://official.example/topic-{topic}/result-{result}",
            snippet="evidence " * 2000,
            query=f"Topic {topic}",
        )
        for topic in range(6) for result in range(5)
    ]
    before = [item.model_dump() for item in sources]
    context = evidence_context(sources)
    assert len(json.dumps(context)) < 8000
    assert all(any(f"topic-{topic}/" in item["url"] for item in context) for topic in range(6))
    assert [item.model_dump() for item in sources] == before
    assert len(sources) == 30


def test_evidence_never_invents_or_truncates_a_citation_url():
    sources = [
        SearchSource(title="long", url="https://example.com/" + "x" * 2000, query="a"),
        SearchSource(title="short", url="https://example.com/real-source", query="a"),
    ]
    context = evidence_context(sources)
    assert [item["url"] for item in context] == ["https://example.com/real-source"]
    assert len(sources[0].url) > 2000
    assert evidence_context([]) == []
