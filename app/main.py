"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import jobs, workflows
from app.config import settings
from app.engine.queue import start_worker, stop_worker

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agentic Video Editor",
    description="AI-powered parameterized video editing workflows",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflows.router)
app.include_router(jobs.router)


@app.on_event("startup")
async def on_startup() -> None:
    settings.ensure_dirs()
    await start_worker()
    logger.info("Agentic Video Editor started")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await stop_worker()
    logger.info("Agentic Video Editor stopped")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
