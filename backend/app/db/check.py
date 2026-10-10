"""Run from backend: python -m app.db.check (exit 0 on success, 1 on failure)."""

import asyncio
import logging

from sqlalchemy import text

from app.db.session import engine, log_database_target, logger


async def check_database() -> int:
    log_database_target()
    try:
        async with asyncio.timeout(10), engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT current_database() AS database, current_user AS username, "
                        "inet_server_addr()::text AS server_address, "
                        "inet_server_port() AS server_port, version() AS server_version"
                    )
                )
            ).mappings().one()
        logger.info(
            "Database connectivity OK: database=%s username=%s server=%s:%s version=%s",
            row["database"],
            row["username"],
            row["server_address"],
            row["server_port"],
            row["server_version"],
        )
        return 0
    except Exception as exc:
        # Connection exception strings may include credentials; report only the type.
        logger.error(
            "Database connectivity FAILED (%s). Check the target above, "
            "DATABASE_URL overrides, and 'docker compose ps postgres'.",
            type(exc).__name__,
        )
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(asyncio.run(check_database()))
