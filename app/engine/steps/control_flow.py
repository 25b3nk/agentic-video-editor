"""Control flow step executors: group, conditional, loop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.engine import expressions
from app.engine.steps.base import BaseStep, StepResult

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext


class GroupStep(BaseStep):
    """
    A group runs its sub-steps sequentially on the current video.

    If the first sub-step is a freeze_frame, it creates an independent
    frozen segment that is appended to the current video. All subsequent
    sub-steps in the group apply to that frozen segment.
    """

    step_type = "group"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        from app.engine.executor import run_steps

        sub_steps = step_def.get("steps", [])
        if not sub_steps:
            return StepResult()

        first = sub_steps[0]

        # If the group starts with a freeze_frame, build an independent sub-segment
        if first.get("type") == "freeze_frame":
            # Execute the freeze_frame to get the frozen clip
            result = await ctx.dispatch_step(first)
            if result.append_video is None:
                raise RuntimeError("freeze_frame did not produce an append_video")

            # Switch context's current_video to the frozen clip for the remaining sub-steps
            original_video = ctx.current_video
            ctx.current_video = result.append_video

            # Run the rest of the sub-steps on the frozen segment
            for sub_step in sub_steps[1:]:
                sub_result = await ctx.dispatch_step(sub_step)
                if sub_result.video_path:
                    ctx.current_video = sub_result.video_path
                # Nested step outputs are stored into the parent context
                for k, v in sub_result.outputs.items():
                    ctx.step_outputs.setdefault(sub_step["id"], {})[k] = v

            # The group produced a new segment to append
            frozen_result = ctx.current_video
            ctx.current_video = original_video
            return StepResult(append_video=frozen_result)

        # Otherwise run sub-steps normally (in-place modifications)
        for sub_step in sub_steps:
            sub_result = await ctx.dispatch_step(sub_step)
            if sub_result.video_path:
                ctx.current_video = sub_result.video_path
            if sub_result.append_video:
                ctx.pending_segments.append(sub_result.append_video)
            for k, v in sub_result.outputs.items():
                ctx.step_outputs.setdefault(sub_step["id"], {})[k] = v

        return StepResult()


class ConditionalStep(BaseStep):
    step_type = "conditional"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        condition_expr = step_def.get("condition", "false")
        result = expressions.evaluate(condition_expr, ctx)
        # Accept both boolean True and truthy comparison results
        branch_steps = step_def.get("then", []) if result else step_def.get("else", [])

        for sub_step in (branch_steps or []):
            sub_result = await ctx.dispatch_step(sub_step)
            if sub_result.video_path:
                ctx.current_video = sub_result.video_path
            if sub_result.append_video:
                ctx.pending_segments.append(sub_result.append_video)
            for k, v in sub_result.outputs.items():
                ctx.step_outputs.setdefault(sub_step["id"], {})[k] = v

        return StepResult()


class LoopStep(BaseStep):
    step_type = "loop"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        over_expr = step_def.get("over", "[]")
        items: Any = expressions.evaluate(over_expr, ctx)
        if not isinstance(items, list):
            items = list(items) if items else []

        as_var = step_def.get("as", "item")
        sub_steps = step_def.get("steps", [])

        for item in items:
            # Inject loop variable into params temporarily
            ctx.params[as_var] = item
            for sub_step in sub_steps:
                sub_result = await ctx.dispatch_step(sub_step)
                if sub_result.video_path:
                    ctx.current_video = sub_result.video_path
                if sub_result.append_video:
                    ctx.pending_segments.append(sub_result.append_video)
                for k, v in sub_result.outputs.items():
                    ctx.step_outputs.setdefault(sub_step["id"], {})[k] = v
            del ctx.params[as_var]

        return StepResult()
