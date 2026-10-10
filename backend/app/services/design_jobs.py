import asyncio
import logging
from datetime import UTC, datetime

from app.agents.json_output import AgentJSONError
from app.agents.orchestrator import ArchitectureOrchestrator
from app.agents.progress import PipelineProgress
from app.db.models import ArchitectureRun, DesignQuery, QueryRun
from app.schemas import ArchitectureRequest
from app.services.search import SearchServiceError, SearxNGSearchService

logger = logging.getLogger(__name__)


class DesignJobs:
    """Local background worker; durable snapshots let browsers reconnect safely."""

    def __init__(self, settings, session_factory):
        self.settings = settings
        self.session_factory = session_factory
        self.tasks: set[asyncio.Task] = set()
        self.slot = asyncio.Semaphore(1)

    def start(self, run_id: str) -> None:
        task = asyncio.create_task(self._run(run_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _progress(self, run_id: str, update: PipelineProgress) -> None:
        async with self.session_factory() as session:
            run = await session.get(QueryRun, run_id)
            now = datetime.now(UTC)
            run.status = "running"
            run.stage = update.stage
            run.updated_at = now
            if update.requirements:
                run.requirements_payload = update.requirements.model_dump(mode="json")
            run.events = [*run.events, {"stage": update.stage, "at": now.isoformat()}]
            parent = await session.get(DesignQuery, run.query_id)
            parent.updated_at = now
            await session.commit()

    async def _fail(self, run_id: str, message: str) -> None:
        try:
            async with self.session_factory() as session:
                run = await session.get(QueryRun, run_id)
                if run is None or run.status in {"complete", "needs_clarification"}:
                    return
                now = datetime.now(UTC)
                run.status = run.stage = "failed"
                run.error = message
                run.updated_at = now
                run.events = [*run.events, {"stage": "failed", "at": now.isoformat()}]
                parent = await session.get(DesignQuery, run.query_id)
                parent.updated_at = now
                await session.commit()
        except Exception:
            logger.exception("Could not record failed design run %s", run_id)

    async def _run(self, run_id: str) -> None:
        try:
            async with self.slot:
                async with self.session_factory() as session:
                    run = await session.get(QueryRun, run_id)
                    request = ArchitectureRequest.model_validate(run.request_payload)
                orchestrator = ArchitectureOrchestrator(
                    settings=self.settings,
                    search_service=SearxNGSearchService(self.settings),
                )

                async def report(update: PipelineProgress):
                    await self._progress(run_id, update)

                response = await orchestrator.run(request, run_id=run_id, progress=report)
                await report(PipelineProgress(stage="saving", requirements=response.requirements))
                # Archive and terminal state commit together, so "saved" always means persisted.
                async with self.session_factory() as session:
                    run = await session.get(QueryRun, run_id)
                    parent = await session.get(DesignQuery, run.query_id)
                    now = datetime.now(UTC)
                    session.add(
                        ArchitectureRun(
                            id=run_id,
                            problem=request.problem,
                            mode=request.mode,
                            status=response.status,
                            request_payload=request.model_dump(mode="json"),
                            response_payload=response.model_dump(mode="json"),
                        )
                    )
                    run.status = run.stage = response.status
                    run.updated_at = parent.updated_at = now
                    run.events = [*run.events, {"stage": response.status, "at": now.isoformat()}]
                    parent.title = (
                        response.architecture.title
                        if response.architecture
                        else response.requirements.problem_summary
                    )
                    await session.commit()
        except asyncio.CancelledError:
            await self._fail(run_id, "The backend stopped during this run. Retry this saved query.")
            raise
        except (AgentJSONError, SearchServiceError) as exc:
            await self._fail(run_id, str(exc))
        except Exception:
            logger.exception("Design generation failed for run %s", run_id)
            await self._fail(
                run_id, "Design generation failed. Check the local services and retry this query."
            )
