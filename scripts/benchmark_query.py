"""Rerun a saved request and compare elapsed stages without relaxing its review.

Creates one new round under the same query, using exactly the latest completed
round's request. No cached model answers or skipped stages are used.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3000/api/queries/"


def request_json(url: str, payload=None):
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def metrics(run: dict) -> dict:
    events = run["events"]
    stages = {
        event["stage"]: round(
            (timestamp(next_event["at"]) - timestamp(event["at"])).total_seconds(), 2
        )
        for event, next_event in zip(events, events[1:], strict=False)
    }
    response = run.get("response") or {}
    architecture = response.get("architecture") or {}
    notes = [
        item
        for item in architecture.get("tradeoffs", [])
        if item.startswith("Responsibility audit - ")
    ]
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "total_seconds": round(
            (timestamp(run["updated_at"]) - timestamp(run["created_at"])).total_seconds(), 2
        ),
        "stage_seconds": stages,
        "components": len(architecture.get("components", [])),
        "research_sources": len(response.get("research_sources", [])),
        "audit_findings": len(notes),
        "failed_findings": [note for note in notes if "[fail]" in note],
        "critic_approved": (response.get("critique") or {}).get("approved"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_id", type=UUID)
    parser.add_argument("--baseline-run", type=UUID, help="Compare an explicit completed round")
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    url = BASE + str(args.query_id)
    before = request_json(url)
    if before["runs"][-1]["status"] in {"queued", "running"}:
        raise RuntimeError("Wait for the active round before benchmarking")
    baseline = next(
        run
        for run in reversed(before["runs"])
        if run["status"] == "complete"
        and (args.baseline_run is None or run["run_id"] == str(args.baseline_run))
    )
    output = ROOT / ".demo" / "performance"
    output.mkdir(parents=True, exist_ok=True)
    accepted = request_json(url + "/runs", baseline["request"])
    run_id = accepted["runs"][-1]["run_id"]
    print(f"Benchmark query={args.query_id} run={run_id}", flush=True)
    (output / f"{run_id}-accepted.json").write_text(json.dumps(accepted), encoding="utf-8")
    deadline = time.monotonic() + args.timeout
    previous_stage = None
    while time.monotonic() < deadline:
        query = request_json(url)
        run = next(item for item in query["runs"] if item["run_id"] == run_id)
        if run["stage"] != previous_stage:
            print(f"Stage: {run['stage']}", flush=True)
            previous_stage = run["stage"]
        if run["status"] not in {"queued", "running"}:
            (output / f"{run_id}-result.json").write_text(json.dumps(query), encoding="utf-8")
            assert run["request"] == baseline["request"], "Benchmark request changed"
            summary = {"baseline": metrics(baseline), "current": metrics(run)}
            if run["status"] == "complete":
                summary["elapsed_reduction_percent"] = round(
                    100
                    * (
                        1
                        - summary["current"]["total_seconds"] / summary["baseline"]["total_seconds"]
                    ),
                    1,
                )
            (output / f"{run_id}-summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            print(json.dumps(summary, indent=2), flush=True)
            if run["status"] != "complete":
                raise RuntimeError(
                    f"Benchmark did not complete: {run['status']} {run.get('error')}"
                )
            return
        time.sleep(10)
    raise TimeoutError(f"Monitoring timed out; saved run {run_id} may still be processing")


if __name__ == "__main__":
    main()
