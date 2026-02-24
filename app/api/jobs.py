"""Job submission and status endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.engine.queue import enqueue_job
from app.models import Job, JobStatus, Workflow
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def submit_job(
    workflow_id: uuid.UUID = Form(...),
    params: str = Form(default="{}"),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Submit a video for processing with a workflow."""
    import json

    # Validate workflow exists
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Parse params JSON
    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="params must be valid JSON")

    # Validate params against workflow definition
    from app.engine.parser import WorkflowParseError, parse_workflow, validate_params
    try:
        wf_def = parse_workflow(workflow.yaml_content)
        resolved_params = validate_params(wf_def, params_dict)
    except WorkflowParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Save uploaded video
    settings.ensure_dirs()
    job_id = uuid.uuid4()
    upload_path = settings.upload_dir / str(job_id)
    upload_path.mkdir(parents=True, exist_ok=True)

    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    video_path = upload_path / f"input{suffix}"

    content = await video.read()
    video_path.write_bytes(content)

    # Create job record
    job = Job(
        id=job_id,
        workflow_id=workflow_id,
        status=JobStatus.PENDING,
        params=resolved_params,
        input_video_path=str(video_path),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue for processing
    await enqueue_job(job_id)

    return JobResponse.model_validate(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
) -> list[JobResponse]:
    result = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(50))
    jobs = result.scalars().all()
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(status_code=409, detail=f"Job already {job.status}")
    job.status = JobStatus.FAILED
    job.error_message = "Cancelled by user"
    await db.commit()
