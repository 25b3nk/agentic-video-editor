"""
Main workflow execution engine.

ExecutionContext holds all state for a single job run.
WorkflowExecutor orchestrates analysis → step execution → output assembly.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.engine.steps import ffmpeg_utils as ff
from app.engine.steps.base import StepResult
from app.engine.steps.registry import get_step_executor

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """All mutable state for one job execution."""

    # Inputs
    input_video: Path
    params: dict[str, Any]
    analysis: dict[str, Any]
    work_dir: Path

    # State
    current_video: Path = field(init=False)
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_segments: list[Path] = field(default_factory=list)
    pending_transition: dict | None = None
    step_counter: int = 0
    step_logs: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Start with the original input as the current video
        self.current_video = self.input_video

    async def dispatch_step(self, step_def: dict) -> StepResult:
        """Dispatch a single step to its executor."""
        step_type = step_def.get("type", "")
        executor = get_step_executor(step_type)
        return await executor.timed_execute(step_def, self)


class WorkflowExecutor:
    """Executes a parsed workflow definition against a video file."""

    async def execute(
        self,
        job_id: uuid.UUID,
        workflow_def: dict,
        params: dict,
        input_video: Path,
        work_dir: Path,
    ) -> Path:
        """
        Run the workflow and return the path to the final output video.

        Raises on any step failure.
        """
        from app.analysis.pipeline import run_analysis

        work_dir.mkdir(parents=True, exist_ok=True)

        # ── 1. Copy input video into work dir ────────────────────────────
        local_input = work_dir / f"input{input_video.suffix}"
        shutil.copy2(input_video, local_input)

        # ── 2. Run required analysis ─────────────────────────────────────
        required = workflow_def.get("requires_analysis", [])
        logger.info("[job %s] Running analysis: %s", job_id, required)
        analysis = await run_analysis(local_input, required)

        # ── 3. Build execution context ───────────────────────────────────
        ctx = ExecutionContext(
            input_video=local_input,
            params=params,
            analysis=analysis,
            work_dir=work_dir,
        )

        # ── 4. Execute top-level steps ───────────────────────────────────
        steps = workflow_def.get("steps", [])
        logger.info("[job %s] Executing %d steps", job_id, len(steps))

        for step in steps:
            step_id = step.get("id", "unknown")
            step_type = step.get("type", "unknown")
            logger.info("[job %s] Step: %s (%s)", job_id, step_id, step_type)

            result = await ctx.dispatch_step(step)

            # Store step outputs for downstream expression resolution
            if result.outputs:
                ctx.step_outputs[step_id] = result.outputs

            # Update current video or add segment
            if result.video_path:
                ctx.current_video = result.video_path
                # If we had pending segments, the current video is one of them
                if ctx.pending_segments:
                    # Replace or update last segment
                    ctx.pending_segments[-1] = result.video_path
                else:
                    ctx.pending_segments.append(result.video_path)

            elif result.append_video:
                # Need to append this video to whatever we have so far
                await self._append_segment(result.append_video, ctx)

        # ── 5. Assemble final output ─────────────────────────────────────
        final_video = await self._assemble_output(workflow_def, ctx)
        logger.info("[job %s] Final output: %s", job_id, final_video)
        return final_video

    async def _append_segment(self, new_segment: Path, ctx: ExecutionContext) -> None:
        """Append new_segment to the accumulated video."""
        if not ctx.pending_segments:
            # First segment — just record it
            ctx.pending_segments.append(ctx.current_video)
            ctx.pending_segments.append(new_segment)
            ctx.current_video = new_segment
            return

        # Apply pending transition if any
        if ctx.pending_transition:
            effect = ctx.pending_transition.get("effect", "flash")
            duration = ctx.pending_transition.get("duration", 0.15)
            merged = ctx.work_dir / f"transition_{ctx.step_counter:04d}.mp4"
            ctx.step_counter += 1
            if effect == "flash":
                await _run_ffmpeg_direct(
                    ff.flash_transition(ctx.pending_segments[-1], new_segment, merged, duration)
                )
                ctx.pending_segments[-1] = merged
            ctx.pending_transition = None
        else:
            ctx.pending_segments.append(new_segment)

        ctx.current_video = new_segment

    async def _assemble_output(
        self, workflow_def: dict, ctx: ExecutionContext
    ) -> Path:
        """Concatenate all pending segments into the final output."""
        output_cfg = workflow_def.get("output", {})
        fmt = output_cfg.get("format", "mp4")
        output_path = ctx.work_dir / f"output.{fmt}"

        segments = ctx.pending_segments
        if not segments:
            # No explicit segments — current_video IS the output
            shutil.copy2(ctx.current_video, output_path)
            return output_path

        if len(segments) == 1:
            shutil.copy2(segments[0], output_path)
            return output_path

        # Concatenate all segments
        tmp_concat = ctx.work_dir / "final_concat.mp4"
        await _run_ffmpeg_direct(ff.concat_videos(segments, tmp_concat))

        # Apply output quality settings
        codec = output_cfg.get("codec", "h264")
        quality = output_cfg.get("quality", "high")
        resolution = output_cfg.get("resolution", "original")
        fps = output_cfg.get("fps", "original")

        encode_args = _build_encode_args(tmp_concat, output_path, codec, quality, resolution, fps)
        await _run_ffmpeg_direct(encode_args)
        return output_path


def _build_encode_args(
    input_path: Path, output_path: Path,
    codec: str, quality: str, resolution: str, fps: str | int,
) -> list[str]:
    """Build FFmpeg re-encode args for final output."""
    crf_map = {"low": 32, "medium": 23, "high": 18, "lossless": 0}
    crf = crf_map.get(quality, 23)
    codec_map = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9"}
    vcodec = codec_map.get(codec, "libx264")

    vf_parts = []
    if resolution not in ("original", None):
        res_map = {"720p": "1280:720", "1080p": "1920:1080", "4k": "3840:2160"}
        if resolution in res_map:
            vf_parts.append(f"scale={res_map[resolution]}:force_original_aspect_ratio=decrease")

    args = ["-i", str(input_path)]
    if vf_parts:
        args += ["-vf", ",".join(vf_parts)]
    args += [
        "-c:v", vcodec,
        "-crf", str(crf),
        "-c:a", "aac",
        str(output_path),
    ]
    if fps not in ("original", None):
        args += ["-r", str(fps)]

    return args


async def _run_ffmpeg_direct(args: list[str]) -> None:
    """Run FFmpeg without a step context."""
    import asyncio
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
