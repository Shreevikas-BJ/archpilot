import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import ENV_FILE, get_settings

logger = logging.getLogger("uvicorn.error")
settings = get_settings()
engine = create_async_engine(
    settings.database_url, pool_pre_ping=True, connect_args={"timeout": 10}
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def log_database_target() -> None:
    # Log individual safe fields, never the URL, password, or query parameters.
    url = engine.url
    logger.info(
        "Database target: host=%s port=%s database=%s username=%s",
        url.host,
        url.port or 5432,
        url.database,
        url.username,
    )
    if any(key.lower() == "database_url" for key in os.environ):
        logger.warning(
            "DATABASE_URL source: process environment (takes precedence over %s). "
            "Unset it to use backend/.env.",
            ENV_FILE,
        )
    else:
        logger.info("DATABASE_URL source: %s", ENV_FILE)


async def get_session():
    async with SessionFactory() as session:
        yield session
