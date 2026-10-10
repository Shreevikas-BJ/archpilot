"""Exercise the real local critic against a deliberately unsafe messaging design."""

import asyncio
import json
import sys
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.factory import agent_model_settings, build_agent  # noqa: E402
from app.agents.json_output import run_json_agent  # noqa: E402
from app.agents.orchestrator import ArchitectureOrchestrator  # noqa: E402
from app.agents.prompts import CRITIC_INSTRUCTIONS  # noqa: E402
from app.agents.responsibility import finalize_review  # noqa: E402
from app.agents.review_output import review_output_type, to_architecture_review  # noqa: E402
from app.config import Settings  # noqa: E402
from app.schemas import ArchitecturePlan  # noqa: E402


async def main():
    fixture = ROOT / "backend/tests/fixtures/unsafe_messaging_architecture.json"
    context = json.loads(fixture.read_text(encoding="utf-8"))
    architecture = ArchitecturePlan.model_validate(context["architecture"])
    settings = Settings()
    output_type = review_output_type(architecture)
    agent = build_agent(
        settings=settings,
        output_type=output_type,
        instructions=CRITIC_INSTRUCTIONS,
        reasoning_budget_tokens=settings.llm_review_reasoning_budget_tokens,
    )
    prompt = ArchitectureOrchestrator._json_context(
        "Review against the original requirements. Audit what is actually specified.",
        **context,
    )
    start = monotonic()
    output = await run_json_agent(
        agent, prompt, output_type, retry_model_settings=agent_model_settings(settings)
    )
    review = to_architecture_review(output)
    critique, notes = finalize_review(architecture, review)
    failed = [key for key, check in review.messaging.items() if check.status == "fail"]
    complete = {item.component_id for item in review.components} == {
        item.id for item in architecture.components
    }
    report = {
        "result": "PASS" if not critique.approved and complete and len(failed) == 9 else "FAIL",
        "elapsed_seconds": round(monotonic() - start, 1),
        "components_reviewed": len(review.components),
        "failed_messaging_checks": failed,
        "critique": critique.model_dump(mode="json"),
        "audit": review.model_dump(mode="json"),
        "saved_audit_notes": notes,
    }
    output = ROOT / ".demo/responsibility-review.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "result",
                    "elapsed_seconds",
                    "components_reviewed",
                    "failed_messaging_checks",
                )
            },
            indent=2,
        )
    )
    assert report["result"] == "PASS", f"Inspect {output} for missing negative findings"


if __name__ == "__main__":
    asyncio.run(main())
