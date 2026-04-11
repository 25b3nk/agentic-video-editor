"""Tests for control flow step executors (group, conditional, loop)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.steps.control_flow import ConditionalStep, GroupStep, LoopStep
from app.engine.steps.base import StepResult


# ── ConditionalStep ───────────────────────────────────────────────────────────


class TestConditionalStep:
    @pytest.mark.asyncio
    async def test_then_branch_runs_when_true(self, execution_ctx, mock_ffmpeg):
        visited = []

        async def fake_dispatch(step_def):
            visited.append(step_def["id"])
            out = execution_ctx.work_dir / f"{step_def['id']}.mp4"
            out.write_bytes(b"\x00")
            return StepResult(video_path=out)

        execution_ctx.dispatch_step = fake_dispatch

        step = ConditionalStep()
        await step.execute(
            {
                "id": "cond",
                "type": "conditional",
                "condition": "{{analysis.metadata.width}} > {{analysis.metadata.height}}",
                "then": [{"id": "crop_it", "type": "crop", "inputs": {"aspect_ratio": "9:16"}}],
                "else": [{"id": "skip", "type": "noop"}],
            },
            execution_ctx,
        )
        assert "crop_it" in visited
        assert "skip" not in visited

    @pytest.mark.asyncio
    async def test_else_branch_runs_when_false(self, execution_ctx, mock_ffmpeg):
        visited = []

        async def fake_dispatch(step_def):
            visited.append(step_def["id"])
            return StepResult()

        execution_ctx.dispatch_step = fake_dispatch
        # Make condition false: portrait video
        execution_ctx.analysis["metadata"]["width"] = 1080
        execution_ctx.analysis["metadata"]["height"] = 1920

        step = ConditionalStep()
        await step.execute(
            {
                "id": "cond",
                "type": "conditional",
                "condition": "{{analysis.metadata.width}} > {{analysis.metadata.height}}",
                "then": [{"id": "do_crop", "type": "crop", "inputs": {}}],
                "else": [{"id": "do_skip", "type": "noop"}],
            },
            execution_ctx,
        )
        assert "do_skip" in visited
        assert "do_crop" not in visited

    @pytest.mark.asyncio
    async def test_empty_else_branch(self, execution_ctx, mock_ffmpeg):
        execution_ctx.analysis["metadata"]["width"] = 100
        execution_ctx.analysis["metadata"]["height"] = 200  # portrait → condition false

        step = ConditionalStep()
        # No else key → should not error
        result = await step.execute(
            {
                "id": "cond",
                "type": "conditional",
                "condition": "{{analysis.metadata.width}} > {{analysis.metadata.height}}",
                "then": [{"id": "crop", "type": "crop", "inputs": {}}],
            },
            execution_ctx,
        )
        assert result.video_path is None

    @pytest.mark.asyncio
    async def test_boolean_param_condition(self, execution_ctx, mock_ffmpeg):
        execution_ctx.params["enable_particles"] = True
        visited = []

        async def fake_dispatch(step_def):
            visited.append(step_def["id"])
            return StepResult()

        execution_ctx.dispatch_step = fake_dispatch
        step = ConditionalStep()
        await step.execute(
            {
                "id": "cond",
                "type": "conditional",
                "condition": "{{enable_particles}} == True",
                "then": [{"id": "add_fire", "type": "particles", "inputs": {}}],
                "else": [],
            },
            execution_ctx,
        )
        assert "add_fire" in visited

    @pytest.mark.asyncio
    async def test_null_check_condition(self, execution_ctx, mock_ffmpeg):
        execution_ctx.params["music_file"] = None
        visited = []

        async def fake_dispatch(step_def):
            visited.append(step_def["id"])
            return StepResult()

        execution_ctx.dispatch_step = fake_dispatch
        step = ConditionalStep()
        await step.execute(
            {
                "id": "cond",
                "type": "conditional",
                "condition": "{{music_file}} != null",
                "then": [{"id": "add_music", "type": "add_audio", "inputs": {}}],
                "else": [],
            },
            execution_ctx,
        )
        # music_file is None → condition is False → then not executed
        assert "add_music" not in visited


# ── LoopStep ──────────────────────────────────────────────────────────────────


class TestLoopStep:
    @pytest.mark.asyncio
    async def test_loop_iterates_over_list(self, execution_ctx, mock_ffmpeg):
        calls = []

        async def fake_dispatch(step_def):
            calls.append(dict(execution_ctx.params))  # snapshot params at each iteration
            return StepResult()

        execution_ctx.dispatch_step = fake_dispatch
        execution_ctx.analysis["silence_detection"] = [
            {"start": 0.0, "end": 0.5},
            {"start": 2.0, "end": 2.3},
        ]

        step = LoopStep()
        await step.execute(
            {
                "id": "loop_silences",
                "type": "loop",
                "over": "{{analysis.silence_detection}}",
                "as": "silence",
                "steps": [{"id": "speed_up", "type": "speed_change", "inputs": {"factor": 4.0}}],
            },
            execution_ctx,
        )
        assert len(calls) == 2
        assert calls[0]["silence"] == {"start": 0.0, "end": 0.5}
        assert calls[1]["silence"] == {"start": 2.0, "end": 2.3}

    @pytest.mark.asyncio
    async def test_loop_variable_cleaned_up(self, execution_ctx, mock_ffmpeg):
        async def fake_dispatch(step_def):
            return StepResult()

        execution_ctx.dispatch_step = fake_dispatch
        step = LoopStep()
        await step.execute(
            {
                "id": "loop",
                "type": "loop",
                "over": "{{analysis.beat_detection.beats}}",
                "as": "beat",
                "steps": [{"id": "s", "type": "noop"}],
            },
            execution_ctx,
        )
        # Loop variable should be removed after loop
        assert "beat" not in execution_ctx.params

    @pytest.mark.asyncio
    async def test_loop_empty_list(self, execution_ctx, mock_ffmpeg):
        calls = []

        async def fake_dispatch(step_def):
            calls.append(step_def["id"])
            return StepResult()

        execution_ctx.dispatch_step = fake_dispatch
        step = LoopStep()
        await step.execute(
            {
                "id": "loop",
                "type": "loop",
                "over": "[]",
                "as": "item",
                "steps": [{"id": "s", "type": "noop"}],
            },
            execution_ctx,
        )
        assert calls == []


# ── GroupStep ─────────────────────────────────────────────────────────────────


class TestGroupStep:
    @pytest.mark.asyncio
    async def test_group_with_freeze_frame_creates_append(self, execution_ctx, mock_ffmpeg):
        frozen_path = execution_ctx.work_dir / "frozen.mp4"
        frozen_path.write_bytes(b"\x00")
        effect_path = execution_ctx.work_dir / "effected.mp4"
        effect_path.write_bytes(b"\x00")

        call_order = []

        async def fake_dispatch(step_def):
            call_order.append(step_def["id"])
            if step_def["type"] == "freeze_frame":
                return StepResult(append_video=frozen_path)
            return StepResult(video_path=effect_path)

        execution_ctx.dispatch_step = fake_dispatch

        step = GroupStep()
        result = await step.execute(
            {
                "id": "poster_group",
                "type": "group",
                "steps": [
                    {"id": "poster_freeze", "type": "freeze_frame", "inputs": {"at": 2.5, "duration": 3.0}},
                    {"id": "red_grade", "type": "color_grade", "inputs": {"preset": "cinematic_red"}},
                    {"id": "name_text", "type": "add_text", "inputs": {"text": "JOHN"}},
                ],
            },
            execution_ctx,
        )
        # Group with freeze_frame as first step produces an append_video
        assert result.append_video is not None
        assert call_order == ["poster_freeze", "red_grade", "name_text"]

    @pytest.mark.asyncio
    async def test_group_without_freeze_modifies_in_place(self, execution_ctx, mock_ffmpeg):
        modified_path = execution_ctx.work_dir / "modified.mp4"
        modified_path.write_bytes(b"\x00")

        async def fake_dispatch(step_def):
            return StepResult(video_path=modified_path)

        execution_ctx.dispatch_step = fake_dispatch

        step = GroupStep()
        result = await step.execute(
            {
                "id": "effect_group",
                "type": "group",
                "steps": [
                    {"id": "shake", "type": "shake", "inputs": {"intensity": 0.5}},
                    {"id": "rotate", "type": "rotate", "inputs": {"angle": 5.0}},
                ],
            },
            execution_ctx,
        )
        # No freeze_frame → no append_video
        assert result.append_video is None

    @pytest.mark.asyncio
    async def test_empty_group(self, execution_ctx):
        step = GroupStep()
        result = await step.execute({"id": "g", "type": "group", "steps": []}, execution_ctx)
        assert result.video_path is None
        assert result.append_video is None
