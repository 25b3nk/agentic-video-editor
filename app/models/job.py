import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class JobStatus(StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default=JobStatus.PENDING, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSONB)
    input_video_path: Mapped[str | None] = mapped_column(Text)
    output_video_path: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    step_logs: Mapped[list | None] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="jobs")  # noqa: F821
    analysis: Mapped["VideoAnalysis | None"] = relationship(  # noqa: F821
        "VideoAnalysis", back_populates="job", uselist=False
    )
