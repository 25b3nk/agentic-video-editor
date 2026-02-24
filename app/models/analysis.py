import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class VideoAnalysis(Base):
    __tablename__ = "video_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), unique=True, nullable=False
    )

    # Analysis results stored as JSON blobs
    metadata_result: Mapped[dict | None] = mapped_column(JSONB)      # FFprobe output
    beat_detection: Mapped[dict | None] = mapped_column(JSONB)       # librosa beats
    scene_detection: Mapped[dict | None] = mapped_column(JSONB)      # PySceneDetect
    transcription: Mapped[dict | None] = mapped_column(JSONB)        # Whisper
    face_detection: Mapped[dict | None] = mapped_column(JSONB)       # MediaPipe
    silence_detection: Mapped[dict | None] = mapped_column(JSONB)    # FFmpeg

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship("Job", back_populates="analysis")  # noqa: F821
