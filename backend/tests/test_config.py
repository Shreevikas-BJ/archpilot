import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import URL, make_url

from app.config import ENV_FILE, Settings
from app.db import session as db_session


@pytest.fixture(autouse=True)
def isolated_database_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("database_url", raising=False)
    env_file = tmp_path / "backend.env"
    env_file.write_text("DATABASE_URL=postgresql+asyncpg://test-user@test-host/test-db\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)


def test_env_file_is_independent_of_working_directory(tmp_path, monkeypatch):
    # A stray .env in the launch directory must not override backend/.env.
    assert Path(__file__).resolve().parents[1] / ".env" == ENV_FILE
    expected = Settings().database_url
    (tmp_path / ".env").write_text("DATABASE_URL=wrong-working-directory\n")
    monkeypatch.chdir(tmp_path)
    assert Settings().database_url == expected


def test_process_environment_takes_precedence(monkeypatch):
    override = URL.create("postgresql+asyncpg", username="override", host="db", database="db")
    monkeypatch.setenv("DATABASE_URL", override.render_as_string())
    assert make_url(Settings().database_url) == override


def test_database_url_is_required():
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "value",
    ["not-a-url", "sqlite:///db", "postgresql+asyncpg://user@host:70000/db"],
)
def test_invalid_database_url_is_rejected_without_echoing_input(value):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=value)
    assert "DATABASE_URL must be" in str(error.value)
    assert value not in str(error.value)


def test_settings_repr_hides_database_url():
    settings = Settings()
    assert "database_url=" not in repr(settings)


def test_public_runtime_contains_only_safe_display_metadata():
    settings = Settings(
        deployment_mode="cloud",
        deployment_label="AWS ECS us-west-2",
        llm_display_name="Private Bonsai endpoint",
    )
    assert settings.public_runtime == {
        "mode": "cloud",
        "label": "AWS ECS us-west-2",
        "llm": "Private Bonsai endpoint",
    }
    assert "database_url" not in settings.public_runtime
    assert "llm_base_url" not in settings.public_runtime


def test_target_logs_safe_fields_and_environment_override(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", db_session.settings.database_url)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        db_session.log_database_target()
    url = db_session.engine.url
    assert f"host={url.host} port={url.port or 5432}" in caplog.text
    assert f"database={url.database} username={url.username}" in caplog.text
    assert "process environment" in caplog.text
    assert "postgresql+asyncpg://" not in caplog.text


def test_target_log_omits_password_and_query_parameters(monkeypatch, caplog):
    url = URL.create(
        "postgresql+asyncpg",
        username="test-user",
        password="never-log-this-test-value",
        host="test-host",
        database="test-db",
        query={"secret": "never-log-this-query"},
    )
    monkeypatch.setattr(db_session, "engine", SimpleNamespace(url=url))
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        db_session.log_database_target()
    assert url.password not in caplog.text
    assert url.query["secret"] not in caplog.text
    assert str(ENV_FILE) in caplog.text
