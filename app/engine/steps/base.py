"""Base class for all step executors."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Outcome of a step execution."""

    outputs: dict[str, Any] = field(default_factory=dict)
    # If the step produced a new video, it goes here.
    # None means "keep the current_video unchanged".
    video_path: Path | None = None
    # If the step produced a video that should be *appended* to current_video.
    append_video: Path | None = None


class BaseStep:
    """All step executors inherit from this."""

    step_type: str = ""

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        raise NotImplementedError

    # ------------------------------------------------------------------ helpers

    async def run_ffmpeg(self, args: list[str], ctx: "ExecutionContext") -> None:
        """Run an FFmpeg command and raise on failure."""
        from app.config import settings

        cmd = [settings.ffmpeg_bin, "-y", *args]
        logger.debug("FFmpeg: %s", " ".join(str(a) for a in cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed (exit {proc.returncode}):\n"
                + stderr.decode(errors="replace")[-2000:]
            )

    def tmp_path(self, ctx: "ExecutionContext", suffix: str = ".mp4") -> Path:
        """Return a unique temp file path in the job's work directory."""
        ctx.step_counter += 1
        return ctx.work_dir / f"step_{ctx.step_counter:04d}{suffix}"

    def log_step(
        self, ctx: "ExecutionContext", step_id: str, step_type: str, status: str,
        message: str | None = None, duration_ms: int | None = None,
    ) -> None:
        entry = {
            "step_id": step_id,
            "step_type": step_type,
            "status": status,
        }
        if message:
            entry["message"] = message
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        ctx.step_logs.append(entry)

    async def timed_execute(
        self, step_def: dict, ctx: "ExecutionContext"
    ) -> StepResult:
        """Wrap execute() with timing and logging."""
        step_id = step_def.get("id", "unknown")
        step_type = step_def.get("type", "unknown")
        self.log_step(ctx, step_id, step_type, "started")
        t0 = time.monotonic()
        try:
            result = await self.execute(step_def, ctx)
            elapsed = int((time.monotonic() - t0) * 1000)
            self.log_step(ctx, step_id, step_type, "completed", duration_ms=elapsed)
            return result
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            self.log_step(ctx, step_id, step_type, "failed", message=str(exc), duration_ms=elapsed)
            raise
