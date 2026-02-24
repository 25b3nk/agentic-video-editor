"""Effect step executors: shake, rotate, color_grade, transition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine import expressions
from app.engine.steps import ffmpeg_utils as ff
from app.engine.steps.base import BaseStep, StepResult

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext


class ShakeStep(BaseStep):
    step_type = "shake"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        intensity = float(inputs.get("intensity", 0.5))
        frequency = float(inputs.get("frequency", 15.0))
        start = ff.timestamp_to_seconds(inputs.get("start", 0))
        end = ff.timestamp_to_seconds(inputs["end"]) if "end" in inputs else None
        output = self.tmp_path(ctx)
        await self.run_ffmpeg(
            ff.apply_shake(ctx.current_video, output, intensity, frequency, start, end), ctx
        )
        return StepResult(video_path=output)


class RotateStep(BaseStep):
    step_type = "rotate"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        from_angle = float(inputs.get("from_angle", inputs.get("angle", 0.0)))
        to_angle = float(inputs.get("to_angle", from_angle))
        easing = inputs.get("easing", "linear")
        start = ff.timestamp_to_seconds(inputs.get("start", 0))
        end = ff.timestamp_to_seconds(inputs["end"]) if "end" in inputs else None
        output = self.tmp_path(ctx)
        await self.run_ffmpeg(
            ff.apply_rotation(ctx.current_video, output, from_angle, to_angle, easing, start, end),
            ctx,
        )
        return StepResult(video_path=output)


class ColorGradeStep(BaseStep):
    step_type = "color_grade"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        output = self.tmp_path(ctx)

        preset = inputs.get("preset")
        if preset and preset in ff.COLOR_GRADE_PRESETS:
            kwargs = ff.COLOR_GRADE_PRESETS[preset].copy()
            # Allow overrides from inputs
            for k in ("brightness", "contrast", "saturation", "tint_strength"):
                if k in inputs:
                    kwargs[k] = float(inputs[k])
            if "tint" in inputs:
                kwargs["tint_hex"] = inputs["tint"]
        else:
            kwargs = {
                "brightness": float(inputs.get("brightness", 0.0)),
                "contrast": float(inputs.get("contrast", 1.0)),
                "saturation": float(inputs.get("saturation", 1.0)),
                "tint_hex": inputs.get("tint"),
                "tint_strength": float(inputs.get("tint_strength", 0.0)),
            }

        await self.run_ffmpeg(
            ff.apply_color_grade(ctx.current_video, output, **kwargs), ctx
        )
        return StepResult(video_path=output)


class TransitionStep(BaseStep):
    step_type = "transition"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        """
        A transition step pairs the accumulated video segments together.
        For 'flash' effect: applies a white flash fade between ctx.pending_segments[-2:]
        if multiple segments exist; otherwise records the transition config for later.
        """
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        effect = inputs.get("effect", "fade")
        duration = float(inputs.get("duration", 0.3))

        # If we have at least 2 pending segments, apply the transition now
        if len(ctx.pending_segments) >= 2:
            seg_a = ctx.pending_segments[-2]
            seg_b = ctx.pending_segments[-1]
            output = self.tmp_path(ctx)

            if effect == "flash":
                await self.run_ffmpeg(ff.flash_transition(seg_a, seg_b, output, duration), ctx)
            else:
                # Default: simple concatenate (fade handled in flash_transition)
                await self.run_ffmpeg(ff.flash_transition(seg_a, seg_b, output, duration), ctx)

            # Replace last two segments with the merged result
            ctx.pending_segments[-2:] = [output]
        else:
            # Record for later (transition will happen when next segment is added)
            ctx.pending_transition = {"effect": effect, "duration": duration}

        return StepResult()


class ParticlesStep(BaseStep):
    step_type = "particles"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        """
        Fire/spark particle overlay.
        For MVP we simulate fire with a color glow filter at the bottom of the frame.
        Production would use a pre-rendered particle overlay video.
        """
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        effect = inputs.get("effect", "fire")
        intensity = float(inputs.get("intensity", 0.7))
        start = ff.timestamp_to_seconds(inputs.get("start", 0))
        end = ff.timestamp_to_seconds(inputs["end"]) if "end" in inputs else None
        output = self.tmp_path(ctx)

        if effect == "fire":
            # Simulate fire: amplify red channel in the bottom portion of the frame
            strength = intensity * 0.4
            end_expr = f",{end}" if end is not None else ""
            enable = f"between(t,{start},{end})" if end is not None else f"gte(t,{start})"
            fire_filter = (
                f"geq="
                f"r='min(255,r(X,Y)+{int(strength*200)}*(1-Y/H)*0.5)':"
                f"g='max(0,g(X,Y)-{int(strength*50)}*(1-Y/H)*0.5)':"
                f"b='max(0,b(X,Y)-{int(strength*80)}*(1-Y/H)*0.5)'"
                f":enable='{enable}'"
            )
            await self.run_ffmpeg([
                "-i", str(ctx.current_video),
                "-vf", fire_filter,
                "-c:v", "libx264", "-c:a", "copy",
                str(output),
            ], ctx)
        else:
            # For other effects, pass through for now
            import shutil
            shutil.copy2(ctx.current_video, output)

        return StepResult(video_path=output)
