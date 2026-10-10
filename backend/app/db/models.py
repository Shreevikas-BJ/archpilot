import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ArchitectureRun(Base):
    __tablename__ = "architecture_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_payload: Mapped[dict] = mapped_column(JSON)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class DesignQuery(Base):
    __tablename__ = "design_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    problem: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class QueryRun(Base):
    __tablename__ = "query_runs"
    __table_args__ = (
        Index(
            "one_active_run_per_query",
            "query_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("design_queries.id"), index=True)
    request_payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    requirements_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    events: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
