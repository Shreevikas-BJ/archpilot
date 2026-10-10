"""Profile the critic on an existing design without repeating the earlier pipeline.

Raw responses are saved only by this explicit diagnostic command in .demo/.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.context import evaluation_context, evidence_context  # noqa: E402
from app.agents.factory import agent_model_settings, build_agent  # noqa: E402
from app.agents.json_output import parse_json_output, run_json_agent  # noqa: E402
from app.agents.orchestrator import ArchitectureOrchestrator  # noqa: E402
from app.agents.prompts import CRITIC_INSTRUCTIONS  # noqa: E402
from app.agents.responsibility import finalize_review  # noqa: E402
from app.agents.review_output import review_output_type, to_architecture_review  # noqa: E402
from app.config import Settings  # noqa: E402
from app.query_schemas import QueryDetail  # noqa: E402


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reasoning-budget", type=int)
    parser.add_argument("--budget-message")
    args = parser.parse_args()
    settings = Settings()
    if args.reasoning_budget is not None and args.reasoning_budget < -1:
        parser.error("--reasoning-budget must be -1 or greater")
    budget = (
        args.reasoning_budget
        if args.reasoning_budget is not None
        else settings.llm_review_reasoning_budget_tokens
    )
    request_settings = agent_model_settings(settings, reasoning_budget_tokens=budget)
    if args.budget_message:
        request_settings.setdefault("extra_body", {})["reasoning_budget_message"] = (
            args.budget_message
        )
    extra = request_settings.get("extra_body", {})
    saved = QueryDetail.model_validate_json(
        (ROOT / ".demo/messaging-revision-result.json").read_text(encoding="utf-8-sig")
    ).runs[-1]
    response = saved.response
    architecture = response.architecture.model_copy(
        update={
            "tradeoffs": [
                note
                for note in response.architecture.tradeoffs
                if not note.startswith("Responsibility audit - ")
            ]
        }
    )
    prompt = ArchitectureOrchestrator._json_context(
        "Review this architecture against the requirements and evidence.",
        user_request=saved.request.model_dump(mode="json"),
        requirements=response.requirements.model_dump(mode="json"),
        optimization_mode=saved.request.mode,
        evaluation=evaluation_context(response.evaluation),
        evidence=evidence_context(response.research_sources),
        architecture=architecture.model_dump(mode="json"),
    )
    output_type = review_output_type(architecture)
    agent = build_agent(
        settings=settings,
        output_type=output_type,
        instructions=CRITIC_INSTRUCTIONS,
        reasoning_budget_tokens=budget,
    )
    directory = ROOT / ".demo/critic-profile"
    if args.reasoning_budget is not None or args.budget_message:
        directory /= (
            f"budget-{extra.get('reasoning_budget_tokens')}-"
            f"guided-{bool(extra.get('reasoning_budget_message'))}"
        )
    directory.mkdir(parents=True, exist_ok=True)
    usage = {}

    class Capture:
        async def run(self, prompt, **kwargs):
            try:
                result = await agent.run(prompt, model_settings=request_settings, **kwargs)
            except Exception:
                (directory / "response.txt").write_text(
                    kwargs["event_stream_handler"].text, encoding="utf-8"
                )
                raise
            (directory / "response.txt").write_text(result.output, encoding="utf-8")
            usage.update(
                input_tokens=result.response.usage.input_tokens,
                output_tokens=result.response.usage.output_tokens,
            )
            try:
                parse_json_output(result.output, output_type)
            except json.JSONDecodeError as error:
                print(
                    json.dumps(
                        {
                            "json_error": error.msg,
                            "line": error.lineno,
                            "column": error.colno,
                            "position": error.pos,
                        }
                    ),
                    flush=True,
                )
            return result

    started = perf_counter()
    output = await run_json_agent(Capture(), prompt, output_type, max_retries=0)
    review = to_architecture_review(output)
    critique, notes = finalize_review(architecture, review)
    report = {
        "seconds": round(perf_counter() - started, 2),
        "reasoning_budget": extra.get("reasoning_budget_tokens"),
        "budget_message": extra.get("reasoning_budget_message"),
        "usage": usage,
        "critique": critique.model_dump(mode="json"),
        "notes": notes,
    }
    (directory / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "seconds": report["seconds"],
                "findings": len(notes),
                "approved": critique.approved,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
