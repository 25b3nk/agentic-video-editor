"""Workflow CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.engine.parser import WorkflowParseError, parse_workflow
from app.models import Workflow
from app.schemas.workflow import WorkflowCreate, WorkflowDetail, WorkflowResponse

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowDetail, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
) -> WorkflowDetail:
    """Create a workflow from a YAML definition."""
    try:
        wf_def = parse_workflow(payload.yaml_content)
    except WorkflowParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    meta = wf_def.get("metadata", {})
    workflow = Workflow(
        name=meta.get("name", "Unnamed Workflow"),
        description=meta.get("description"),
        author=meta.get("author"),
        tags=meta.get("tags"),
        yaml_content=payload.yaml_content,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return WorkflowDetail.model_validate(workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowResponse]:
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    workflows = result.scalars().all()
    return [WorkflowResponse.model_validate(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WorkflowDetail:
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowDetail.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(workflow)
    await db.commit()
