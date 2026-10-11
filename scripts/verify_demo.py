"""Check the live frontend/API/database round trip without generating another design."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.models import ArchitectureRun  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.schemas import SavedArchitectureRun  # noqa: E402


def get_json(path: str):
    with urlopen("http://127.0.0.1:3000" + path, timeout=15) as response:
        return json.load(response)


async def verify(capture_path: Path | None) -> dict:
    health = get_json("/api/health")
    assert health.get("status") == "ok" and health.get("database") == "ok", (
        "Frontend/API/database health failed"
    )
    history = get_json("/api/architect")
    capture = None
    if capture_path:
        capture = json.loads(capture_path.read_text(encoding="utf-8-sig"))
        assert capture["state"] == "complete" and capture["httpStatus"] == 200
        run_id = capture["payload"]["run_id"]
    else:
        completed = [run for run in history if run["status"] == "complete"]
        assert completed, "No completed design is available; run the demo brief first"
        run_id = completed[0]["run_id"]
    assert any(run["run_id"] == run_id for run in history), "Run is absent from saved history"
    saved = SavedArchitectureRun.model_validate(get_json("/api/architect/" + run_id))
    assert saved.response.run_id == run_id and saved.response.status == "complete"
    assert saved.response.architecture is not None, "Completed run is missing its architecture"
    assert saved.response.critique is not None, "Completed run is missing its critique"
    assert saved.response.mermaid, "Completed run is missing its diagram"
    payload = saved.response.model_dump(mode="json")
    request = saved.request.model_dump(mode="json")
    if capture:
        assert payload == capture["payload"], "Reloaded response differs from the browser POST"
        assert request == capture["request"], "Reloaded brief differs from the submitted brief"
    try:
        async with SessionFactory() as session:
            row = await session.get(ArchitectureRun, run_id)
            assert row is not None, "Run was not persisted in PostgreSQL"
            assert row.response_payload == payload, (
                "Stored response differs from the frontend response"
            )
            assert row.request_payload == request, (
                "Stored request differs from the frontend request"
            )
    finally:
        await engine.dispose()
    return {
        "result": "PASS",
        "run_id": run_id,
        "title": saved.response.architecture.title,
        "sources": len(saved.response.research_sources),
        "critic_approved": saved.response.critique.approved,
        "frontend_api_database_health": True,
        "pydantic_validation": True,
        "database_request_and_response_match": True,
        "browser_post_matches_saved_response": True if capture else None,
        "elapsed_seconds": capture.get("elapsedSeconds") if capture else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture", type=Path, help="Recorded real browser POST request/response JSON"
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.capture)), indent=2))
