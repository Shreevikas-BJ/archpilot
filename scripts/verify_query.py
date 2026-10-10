"""Verify a saved query through the frontend proxy and its exact PostgreSQL records."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.request import urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.models import ArchitectureRun, DesignQuery, QueryRun  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.query_schemas import ProgressEvent, QueryDetail  # noqa: E402


def get_json(path: str):
    with urlopen("http://127.0.0.1:3000" + path, timeout=15) as response:
        return json.load(response)


async def verify(query_id: str, accepted_path: Path | None) -> dict:
    assert get_json("/api/health") == {"status": "ok", "database": "ok"}
    query = QueryDetail.model_validate(get_json("/api/queries/" + query_id))
    latest = query.runs[-1]
    assert latest.status == "complete", f"Latest round is {latest.status}: {latest.stage}"
    assert latest.response and latest.response.architecture and latest.response.mermaid
    assert any(item["query_id"] == query.query_id for item in get_json("/api/queries"))
    if accepted_path:
        capture = json.loads(accepted_path.read_text(encoding="utf-8-sig"))
        accepted = capture["accepted"]
        assert accepted["status"] == 202
        assert accepted["payload"]["query_id"] == query.query_id
        assert accepted["payload"]["runs"][0]["run_id"] == query.runs[0].run_id
        assert accepted["request"] == query.runs[0].request.model_dump(mode="json")
    try:
        async with SessionFactory() as session:
            parent = await session.get(DesignQuery, query.query_id)
            assert parent is not None and parent.problem == query.problem
            assert parent.title == query.title
            for run in query.runs:
                row = await session.get(QueryRun, run.run_id)
                assert row is not None and row.query_id == query.query_id
                assert row.request_payload == run.request.model_dump(mode="json")
                assert row.status == run.status and row.stage == run.stage
                assert row.error == run.error
                assert [ProgressEvent.model_validate(event) for event in row.events] == run.events
                assert row.requirements_payload == (
                    run.requirements.model_dump(mode="json") if run.requirements else None
                )
                if run.response:
                    archive = await session.get(ArchitectureRun, run.run_id)
                    assert archive is not None
                    assert archive.request_payload == row.request_payload
                    assert archive.response_payload == run.response.model_dump(mode="json")
    finally:
        await engine.dispose()
    return {
        "result": "PASS",
        "query_id": query.query_id,
        "latest_run_id": latest.run_id,
        "rounds": len(query.runs),
        "classified_rounds": sum(run.requirements is not None for run in query.runs),
        "clarification_answers": len(latest.request.clarifications),
        "title": latest.response.architecture.title,
        "stages": [event.stage for event in latest.events],
        "critic_approved": latest.response.critique.approved if latest.response.critique else None,
        "duration_seconds": round((latest.updated_at - latest.created_at).total_seconds(), 1),
        "frontend_api_database_match": True,
        "browser_submission_matches": True if accepted_path else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_id", type=UUID)
    parser.add_argument("--accepted", type=Path, help="Captured real browser HTTP 202 response")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(str(args.query_id), args.accepted)), indent=2))
