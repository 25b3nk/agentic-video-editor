import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    yaml_content: str = Field(..., description="Full workflow YAML definition")


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    author: str | None
    tags: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowDetail(WorkflowResponse):
    yaml_content: str
    updated_at: datetime
