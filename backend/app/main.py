from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.queries import router as query_router
from app.api.routes import router
from app.config import get_settings
from app.db.base import Base
from app.db.queries import import_legacy_runs, mark_interrupted_runs
from app.db.session import SessionFactory, engine, log_database_target, logger
from app.services.design_jobs import DesignJobs

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    log_database_target()
    jobs = DesignJobs(settings, SessionFactory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("Database connection successful; schema ready.")
        async with SessionFactory() as session:
            await mark_interrupted_runs(session)
            await import_legacy_runs(session)
        application.state.design_jobs = jobs
        yield
    finally:
        await jobs.close()
        await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(query_router, prefix=settings.api_prefix)
