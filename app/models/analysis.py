import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class VideoAnalysis(Base):
    __tablename__ = "video_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), unique=True, nullable=False
    )

    # Analysis results stored as JSON blobs
    metadata_result: Mapped[dict | None] = mapped_column(JSON)      # FFprobe output
    beat_detection: Mapped[dict | None] = mapped_column(JSON)       # librosa beats
    scene_detection: Mapped[dict | None] = mapped_column(JSON)      # PySceneDetect
    transcription: Mapped[dict | None] = mapped_column(JSON)        # Whisper
    face_detection: Mapped[dict | None] = mapped_column(JSON)       # MediaPipe
    silence_detection: Mapped[dict | None] = mapped_column(JSON)    # FFmpeg

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship("Job", back_populates="analysis")  # noqa: F821
