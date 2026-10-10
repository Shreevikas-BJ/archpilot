import json
import uuid

from app.agents.context import evaluation_context, evidence_context
from app.agents.factory import agent_model_settings, build_agent
from app.agents.json_output import run_json_agent
from app.agents.progress import PipelineProgress, ProgressCallback
from app.agents.prompts import (
    ARCHITECT_INSTRUCTIONS,
    CRITIC_INSTRUCTIONS,
    EVALUATOR_INSTRUCTIONS,
    REQUIREMENTS_INSTRUCTIONS,
    RESEARCH_PLANNER_INSTRUCTIONS,
    REVISION_INSTRUCTIONS,
)
from app.agents.responsibility import finalize_review
from app.agents.review_output import review_output_type, to_architecture_review
from app.agents.revision import ArchitectureRevision
from app.config import Settings
from app.schemas import (
    ArchitecturePlan,
    ArchitectureRequest,
    ArchitectureResponse,
    EvaluationReport,
    RequirementsAnalysis,
    ResearchPlan,
)
from app.services.mermaid import architecture_to_mermaid
from app.services.search import SearxNGSearchService


class ArchitectureOrchestrator:
    def __init__(self, settings: Settings, search_service: SearxNGSearchService) -> None:
        self.settings = settings
        self.search_service = search_service

        self.requirements_agent = build_agent(
            settings=settings,
            output_type=RequirementsAnalysis,
            instructions=REQUIREMENTS_INSTRUCTIONS,
            reasoning_budget_tokens=settings.llm_planning_reasoning_budget_tokens,
        )
        self.research_planner = build_agent(
            settings=settings,
            output_type=ResearchPlan,
            instructions=RESEARCH_PLANNER_INSTRUCTIONS,
            reasoning_budget_tokens=settings.llm_planning_reasoning_budget_tokens,
        )
        self.evaluator = build_agent(
            settings=settings,
            output_type=EvaluationReport,
            instructions=EVALUATOR_INSTRUCTIONS,
            reasoning_budget_tokens=settings.llm_planning_reasoning_budget_tokens,
        )
        self.architect = build_agent(
            settings=settings,
            output_type=ArchitecturePlan,
            instructions=ARCHITECT_INSTRUCTIONS,
        )
        self.reviser = build_agent(
            settings=settings,
            output_type=ArchitectureRevision,
            instructions=REVISION_INSTRUCTIONS,
        )

    async def run(
        self,
        request: ArchitectureRequest,
        *,
        run_id: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> ArchitectureResponse:
        run_id = run_id or str(uuid.uuid4())

        async def report(stage, requirements=None):
            if progress:
                await progress(PipelineProgress(stage=stage, requirements=requirements))

        async def generate(agent, prompt, output_type, stage, **kwargs):
            return await run_json_agent(
                agent,
                prompt,
                output_type,
                run_id=run_id,
                stage=stage,
                retry_model_settings=agent_model_settings(self.settings),
                **kwargs,
            )

        async def audit(plan, prompt, stage):
            output_type = review_output_type(plan)
            critic = build_agent(
                settings=self.settings,
                output_type=output_type,
                instructions=CRITIC_INSTRUCTIONS,
                reasoning_budget_tokens=self.settings.llm_review_reasoning_budget_tokens,
            )
            output = await generate(critic, prompt, output_type, stage)
            return to_architecture_review(output)

        await report("requirements")
        clarification_context = "\n".join(
            f"- {question}: {answer}" for question, answer in request.clarifications.items()
        )
        requirements_prompt = (
            f"Business problem:\n{request.problem}\n\n"
            f"Optimization mode: {request.mode}\n\n"
            f"User-provided clarifications:\n{clarification_context or 'None'}"
        )
        requirements = await generate(
            self.requirements_agent, requirements_prompt, RequirementsAnalysis, "requirements"
        )

        unanswered = [
            question
            for question in requirements.clarifying_questions
            if question not in request.clarifications
        ]
        if unanswered:
            await report("needs_clarification", requirements)
            return ArchitectureResponse(
                run_id=run_id,
                status="needs_clarification",
                requirements=requirements,
                clarifying_questions=unanswered,
            )

        await report("research", requirements)
        planner_prompt = self._json_context(
            "Create a focused research plan for these requirements.",
            user_request=request.model_dump(mode="json"),
            requirements=requirements.model_dump(mode="json"),
            mode=request.mode,
        )
        research_plan = await generate(
            self.research_planner, planner_prompt, ResearchPlan, "research"
        )
        queries = research_plan.queries[: self.settings.max_search_queries]
        await report("search")
        sources = await self.search_service.search_many(queries)

        await report("evaluation")
        evidence = evidence_context(sources)
        evaluation_prompt = self._json_context(
            "Evaluate technology choices using only the supplied evidence.",
            user_request=request.model_dump(mode="json"),
            requirements=requirements.model_dump(mode="json"),
            optimization_mode=request.mode,
            evidence=evidence,
        )
        evaluation = await generate(
            self.evaluator, evaluation_prompt, EvaluationReport, "evaluation"
        )
        decisions = evaluation_context(evaluation)

        await report("architecture")
        architecture_prompt = self._json_context(
            "Produce the architecture plan.",
            user_request=request.model_dump(mode="json"),
            requirements=requirements.model_dump(mode="json"),
            optimization_mode=request.mode,
            evaluation=decisions,
            evidence=evidence,
        )
        architecture = await generate(
            self.architect, architecture_prompt, ArchitecturePlan, "architecture"
        )

        await report("critique")
        critique_prompt = self._json_context(
            "Review this architecture against the requirements and evidence.",
            user_request=request.model_dump(mode="json"),
            requirements=requirements.model_dump(mode="json"),
            optimization_mode=request.mode,
            evaluation=decisions,
            evidence=evidence,
            architecture=architecture.model_dump(mode="json"),
        )
        review = await audit(architecture, critique_prompt, "critique")
        critique, audit_notes = finalize_review(architecture, review)

        if not critique.approved and critique.required_changes:
            await report("revision")
            revision_prompt = self._json_context(
                "Revise the architecture once. Address every required change "
                "without adding unnecessary complexity.",
                user_request=request.model_dump(mode="json"),
                requirements=requirements.model_dump(mode="json"),
                optimization_mode=request.mode,
                evaluation=decisions,
                previous_architecture=architecture.model_dump(mode="json"),
                critique=critique.model_dump(mode="json"),
                evidence=evidence,
            )
            revision = await generate(
                self.reviser,
                revision_prompt,
                ArchitectureRevision,
                "revision",
                validation_context={"previous_architecture": architecture},
            )
            architecture = revision.apply_to(architecture)

            await report("final_review")
            final_critique_prompt = self._json_context(
                "Perform a final review of the revised architecture.",
                user_request=request.model_dump(mode="json"),
                requirements=requirements.model_dump(mode="json"),
                optimization_mode=request.mode,
                evaluation=decisions,
                evidence=evidence,
                architecture=architecture.model_dump(mode="json"),
            )
            review = await audit(architecture, final_critique_prompt, "final_review")
            critique, audit_notes = finalize_review(architecture, review)

        # Persist the final audit in an existing field, visible in Decisions and JSON exports.
        # Earlier verdicts must not be carried forward as evidence for a revised architecture.
        architecture = architecture.model_copy(
            update={"tradeoffs": [*architecture.tradeoffs, *audit_notes]}
        )

        return ArchitectureResponse(
            run_id=run_id,
            status="complete",
            requirements=requirements,
            research_sources=sources,
            evaluation=evaluation,
            architecture=architecture,
            critique=critique,
            mermaid=architecture_to_mermaid(architecture),
        )

    @staticmethod
    def _json_context(instruction: str, **context: object) -> str:
        context_json = json.dumps(context, separators=(",", ":"), ensure_ascii=False)
        return f"{instruction}\n\nCONTEXT JSON:\n{context_json}"
