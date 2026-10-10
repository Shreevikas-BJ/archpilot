from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "ArchPilot API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/v1"

    # Required configuration: never silently fall back to another server or password.
    database_url: str = Field(repr=False)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            url = make_url(value)
            valid = (
                url.drivername == "postgresql+asyncpg"
                and url.host
                and url.database
                and url.username
                and (url.port is None or 1 <= url.port <= 65535)
            )
        except (ArgumentError, ValueError):
            valid = False
        if not valid:
            raise ValueError(
                "DATABASE_URL must be a postgresql+asyncpg URL with a host, "
                "database, username, and valid port"
            )
        return value

    llm_provider: Literal["ollama", "openai_compatible"] = "openai_compatible"
    llm_model: str = "bonsai2-27b"
    llm_base_url: str = "http://localhost:8080/v1"
    llm_api_key: str = "local"
    llm_temperature: float = Field(default=0.15, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=1800.0, gt=0)
    # Optional llama.cpp extension; leave unset for other OpenAI-compatible servers.
    llm_reasoning_budget_tokens: int | None = Field(default=None, ge=-1)
    llm_planning_reasoning_budget_tokens: int | None = Field(default=None, ge=-1)
    llm_review_reasoning_budget_tokens: int | None = Field(default=None, ge=-1)
    llm_reasoning_budget_message: str | None = None

    searxng_url: str = "http://localhost:8081"
    search_results_per_query: int = Field(default=5, ge=1, le=10)
    max_search_queries: int = Field(default=6, ge=1, le=10)
    search_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
