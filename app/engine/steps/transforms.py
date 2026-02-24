"""Core transform step executors: trim, crop, speed_change, freeze_frame, extract_frame."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from app.engine import expressions
from app.engine.steps import ffmpeg_utils as ff
from app.engine.steps.base import BaseStep, StepResult

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext


class TrimStep(BaseStep):
    step_type = "trim"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        start = ff.timestamp_to_seconds(inputs.get("start", 0))
        output = self.tmp_path(ctx)

        if "end" in inputs:
            end = ff.timestamp_to_seconds(inputs["end"])
            await self.run_ffmpeg(ff.trim_video(ctx.current_video, output, start, end), ctx)
        elif "duration" in inputs:
            duration = float(inputs["duration"])
            await self.run_ffmpeg(ff.trim_video_duration(ctx.current_video, output, start, duration), ctx)
        else:
            raise ValueError("trim step requires 'end' or 'duration'")

        return StepResult(video_path=output)


class CropStep(BaseStep):
    step_type = "crop"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        output = self.tmp_path(ctx)

        if "aspect_ratio" in inputs:
            await self.run_ffmpeg(
                ff.apply_crop_aspect(ctx.current_video, output, inputs["aspect_ratio"]), ctx
            )
        elif all(k in inputs for k in ("x", "y", "width", "height")):
            await self.run_ffmpeg(
                ff.apply_crop(
                    ctx.current_video, output,
                    int(inputs["x"]), int(inputs["y"]),
                    int(inputs["width"]), int(inputs["height"]),
                ), ctx
            )
        else:
            raise ValueError("crop step requires 'aspect_ratio' or explicit x/y/width/height")

        return StepResult(video_path=output)


class SpeedChangeStep(BaseStep):
    step_type = "speed_change"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        factor = float(inputs.get("factor", 1.0))
        output = self.tmp_path(ctx)
        await self.run_ffmpeg(ff.apply_speed_change(ctx.current_video, output, factor), ctx)
        return StepResult(video_path=output)


class FreezeFrameStep(BaseStep):
    step_type = "freeze_frame"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        at = ff.timestamp_to_seconds(inputs["at"])
        duration = float(inputs["duration"])

        # 1. Extract the frame as a PNG
        frame_png = self.tmp_path(ctx, suffix=".png")
        await self.run_ffmpeg(
            ff.extract_frame(ctx.current_video, frame_png, at), ctx
        )

        # 2. Probe original video to get dimensions (use ffprobe)
        width, height, fps = await _probe_video_dims(ctx)

        # 3. Create a frozen video segment from the frame
        frozen_video = self.tmp_path(ctx)
        await self.run_ffmpeg(
            ff.frame_to_video(frame_png, frozen_video, duration, width, height, int(fps)), ctx
        )

        # 4. Store as append_video — the executor will concatenate it
        return StepResult(append_video=frozen_video)


class ExtractFrameStep(BaseStep):
    step_type = "extract_frame"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        at = ff.timestamp_to_seconds(inputs["at"])
        fmt = inputs.get("format", "png")
        output = self.tmp_path(ctx, suffix=f".{fmt}")
        await self.run_ffmpeg(
            ff.extract_frame(ctx.current_video, output, at, fmt), ctx
        )
        return StepResult(outputs={"image_path": str(output)})


# ── helpers ──────────────────────────────────────────────────────────────────


async def _probe_video_dims(ctx: "ExecutionContext") -> tuple[int, int, float]:
    """Return (width, height, fps) of ctx.current_video using ffprobe."""
    from app.config import settings

    cmd = [
        settings.ffprobe_bin,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(ctx.current_video),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    import json
    data = json.loads(stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            w = int(stream["width"])
            h = int(stream["height"])
            r_frame_rate = stream.get("r_frame_rate", "30/1")
            num, den = r_frame_rate.split("/")
            fps = float(num) / float(den)
            return w, h, fps
    # Fallback
    meta = ctx.analysis.get("metadata", {})
    return meta.get("width", 1920), meta.get("height", 1080), meta.get("fps", 30)
