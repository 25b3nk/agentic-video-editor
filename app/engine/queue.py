"""
Simple in-process async job queue.

For MVP: runs jobs sequentially with configurable concurrency.
Production upgrade path: replace with Redis + Celery.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
_running_jobs: set[uuid.UUID] = set()
_worker_task: asyncio.Task | None = None


async def enqueue_job(job_id: uuid.UUID) -> None:
    """Add a job to the processing queue."""
    await _queue.put(job_id)
    logger.info("Enqueued job %s (queue size: %d)", job_id, _queue.qsize())


async def start_worker() -> None:
    """Start the background worker (call once on app startup)."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
        logger.info("Job queue worker started (max_concurrent=%d)", settings.max_concurrent_jobs)


async def stop_worker() -> None:
    """Gracefully stop the background worker."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass


async def _worker_loop() -> None:
    """Process jobs from the queue."""
    semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    while True:
        job_id = await _queue.get()
        asyncio.create_task(_process_with_semaphore(job_id, semaphore))
        _queue.task_done()


async def _process_with_semaphore(
    job_id: uuid.UUID, semaphore: asyncio.Semaphore
) -> None:
    async with semaphore:
        _running_jobs.add(job_id)
        try:
            await _run_job(job_id)
        except Exception as e:
            logger.exception("Unhandled error in job %s: %s", job_id, e)
        finally:
            _running_jobs.discard(job_id)


async def _run_job(job_id: uuid.UUID) -> None:
    """Load job from DB and execute it."""
    from app.db.session import AsyncSessionLocal
    from app.engine.executor import WorkflowExecutor
    from app.engine.parser import parse_workflow, validate_params
    from app.models import Job, JobStatus, VideoAnalysis

    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            logger.error("Job %s not found in database", job_id)
            return

        if job.status != JobStatus.PENDING:
            logger.warning("Job %s has unexpected status %s, skipping", job_id, job.status)
            return

        logger.info("Starting job %s (workflow %s)", job_id, job.workflow_id)

        # Update status
        job.status = JobStatus.ANALYZING
        job.started_at = datetime.utcnow()
        await db.commit()

        try:
            from app.models import Workflow
            workflow = await db.get(Workflow, job.workflow_id)
            if not workflow:
                raise RuntimeError(f"Workflow {job.workflow_id} not found")

            # Parse and validate
            workflow_def = parse_workflow(workflow.yaml_content)
            params = validate_params(workflow_def, job.params or {})

            input_video = Path(job.input_video_path)
            if not input_video.exists():
                raise FileNotFoundError(f"Input video not found: {input_video}")

            work_dir = settings.work_dir / str(job_id)

            # Update status to running
            job.status = JobStatus.RUNNING
            await db.commit()

            # Execute
            executor = WorkflowExecutor()
            output_video = await executor.execute(
                job_id=job_id,
                workflow_def=workflow_def,
                params=params,
                input_video=input_video,
                work_dir=work_dir,
            )

            # Copy output to final location
            output_dir = settings.output_dir / str(job_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            final_output = output_dir / output_video.name
            import shutil
            shutil.copy2(output_video, final_output)

            # Mark completed
            job.status = JobStatus.COMPLETED
            job.output_video_path = str(final_output)
            job.completed_at = datetime.utcnow()
            # step_logs are collected inside the executor's context but returned via output_video
            # For now we leave step_logs empty (populated in a future iteration)
            await db.commit()
            logger.info("Job %s completed: %s", job_id, final_output)

        except Exception as e:
            logger.exception("Job %s failed: %s", job_id, e)
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
