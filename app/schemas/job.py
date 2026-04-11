import uuid
from datetime import datetime

from pydantic import BaseModel


class JobSubmit(BaseModel):
    workflow_id: uuid.UUID
    params: dict = {}


class StepLog(BaseModel):
    step_id: str
    step_type: str
    status: str  # started | completed | failed
    message: str | None = None
    duration_ms: int | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    params: dict | None
    input_video_path: str | None
    output_video_path: str | None
    error_message: str | None
    step_logs: list | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    metadata_result: dict | None
    beat_detection: dict | None
    scene_detection: dict | None
    face_detection: dict | None
    silence_detection: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
