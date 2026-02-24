"""Overlay step executors: add_text, add_image, add_audio, particles (re-exported)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.engine import expressions
from app.engine.steps import ffmpeg_utils as ff
from app.engine.steps.base import BaseStep, StepResult

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext


class AddTextStep(BaseStep):
    step_type = "add_text"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        text = str(inputs.get("text", ""))
        # Escape single quotes for FFmpeg drawtext
        text = text.replace("'", "\\'")

        font_size = int(inputs.get("font_size", 48))
        font_color = inputs.get("font_color", "white").lstrip("#")
        stroke_color = inputs.get("stroke_color", "black").lstrip("#")
        stroke_width = int(inputs.get("stroke_width", 2))
        start = ff.timestamp_to_seconds(inputs.get("start", 0))
        end = ff.timestamp_to_seconds(inputs["end"]) if "end" in inputs else None

        position = inputs.get("position", "bottom_center")
        x, y = _position_to_xy(position, inputs)

        output = self.tmp_path(ctx)
        await self.run_ffmpeg(
            ff.add_text_overlay(
                ctx.current_video, output, text, font_size,
                font_color, stroke_color, stroke_width, x, y, start, end,
            ), ctx
        )
        return StepResult(video_path=output)


class AddImageStep(BaseStep):
    step_type = "add_image"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        source = Path(str(inputs["source"]))
        if not source.exists():
            raise FileNotFoundError(f"Image overlay source not found: {source}")

        opacity = float(inputs.get("opacity", 1.0))
        animation = inputs.get("animation", "none")
        anim_duration = float(inputs.get("animation_duration", 0.3))
        start = ff.timestamp_to_seconds(inputs.get("start", 0))
        end = ff.timestamp_to_seconds(inputs["end"]) if "end" in inputs else None

        fade_in = anim_duration if animation == "fade_in" else 0.0
        output = self.tmp_path(ctx)
        await self.run_ffmpeg(
            ff.overlay_image(
                ctx.current_video, source, output,
                start=start, end=end,
                opacity=opacity,
                fade_in_duration=fade_in,
            ), ctx
        )
        return StepResult(video_path=output)


class AddAudioStep(BaseStep):
    step_type = "add_audio"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        source = inputs.get("source")
        if not source:
            return StepResult()  # No audio provided, skip

        audio_path = Path(str(source))
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio source not found: {audio_path}")

        volume = float(inputs.get("volume", 0.8))
        duck_original = float(inputs.get("duck_original", 1.0))
        fade_in = float(inputs.get("fade_in", 0.0))
        fade_out = float(inputs.get("fade_out", 0.0))

        output = self.tmp_path(ctx)
        await self.run_ffmpeg(
            ff.add_audio_overlay(
                ctx.current_video, audio_path, output,
                video_volume=duck_original,
                audio_volume=volume,
                fade_in=fade_in, fade_out=fade_out,
            ), ctx
        )
        return StepResult(video_path=output)


class NoopStep(BaseStep):
    step_type = "noop"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        return StepResult()  # Do nothing


# ── helpers ──────────────────────────────────────────────────────────────────

def _position_to_xy(position: str, inputs: dict) -> tuple[str, str]:
    """Convert position keyword to FFmpeg x/y expressions."""
    if position == "center":
        return "(w-text_w)/2", "(h-text_h)/2"
    if position == "bottom_center":
        return "(w-text_w)/2", "h-th-30"
    if position == "top_left":
        return "20", "20"
    if position == "custom":
        return str(inputs.get("x", 0)), str(inputs.get("y", 0))
    return "(w-text_w)/2", "h-th-30"
