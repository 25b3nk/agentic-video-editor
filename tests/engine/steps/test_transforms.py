"""Tests for transform step executors (trim, crop, speed_change, freeze_frame, extract_frame)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.steps.transforms import (
    CropStep,
    ExtractFrameStep,
    FreezeFrameStep,
    SpeedChangeStep,
    TrimStep,
)


# ── TrimStep ──────────────────────────────────────────────────────────────────


class TestTrimStep:
    @pytest.mark.asyncio
    async def test_trim_with_end(self, execution_ctx, mock_ffmpeg):
        step = TrimStep()
        step_def = {"id": "t1", "type": "trim", "inputs": {"start": 0, "end": 5.0}}
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None
        assert result.video_path.suffix == ".mp4"

    @pytest.mark.asyncio
    async def test_trim_with_duration(self, execution_ctx, mock_ffmpeg):
        step = TrimStep()
        step_def = {"id": "t1", "type": "trim", "inputs": {"start": 1.0, "duration": 3.0}}
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_trim_missing_end_and_duration_raises(self, execution_ctx, mock_ffmpeg):
        step = TrimStep()
        step_def = {"id": "t1", "type": "trim", "inputs": {"start": 0}}
        with pytest.raises(ValueError, match="end.*duration"):
            await step.execute(step_def, execution_ctx)

    @pytest.mark.asyncio
    async def test_trim_resolves_expression(self, execution_ctx, mock_ffmpeg):
        execution_ctx.params["clip_end"] = 4.5
        step = TrimStep()
        step_def = {"id": "t1", "type": "trim", "inputs": {"start": 0, "end": "{{clip_end}}"}}
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_trim_output_is_unique(self, execution_ctx, mock_ffmpeg):
        step = TrimStep()
        step_def = {"id": "t1", "type": "trim", "inputs": {"start": 0, "end": 5.0}}
        result1 = await step.execute(step_def, execution_ctx)
        result2 = await step.execute(step_def, execution_ctx)
        assert result1.video_path != result2.video_path


# ── CropStep ──────────────────────────────────────────────────────────────────


class TestCropStep:
    @pytest.mark.asyncio
    async def test_crop_aspect_ratio(self, execution_ctx, mock_ffmpeg):
        step = CropStep()
        step_def = {"id": "c1", "type": "crop", "inputs": {"aspect_ratio": "9:16"}}
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_crop_explicit_coords(self, execution_ctx, mock_ffmpeg):
        step = CropStep()
        step_def = {
            "id": "c1", "type": "crop",
            "inputs": {"x": 100, "y": 50, "width": 720, "height": 1280},
        }
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_crop_missing_inputs_raises(self, execution_ctx, mock_ffmpeg):
        step = CropStep()
        step_def = {"id": "c1", "type": "crop", "inputs": {}}
        with pytest.raises(ValueError):
            await step.execute(step_def, execution_ctx)


# ── SpeedChangeStep ───────────────────────────────────────────────────────────


class TestSpeedChangeStep:
    @pytest.mark.asyncio
    async def test_speed_change(self, execution_ctx, mock_ffmpeg):
        step = SpeedChangeStep()
        step_def = {"id": "s1", "type": "speed_change", "inputs": {"factor": 0.5}}
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_default_factor(self, execution_ctx, mock_ffmpeg):
        step = SpeedChangeStep()
        step_def = {"id": "s1", "type": "speed_change", "inputs": {}}
        result = await step.execute(step_def, execution_ctx)
        assert result.video_path is not None


# ── FreezeFrameStep ───────────────────────────────────────────────────────────


class TestFreezeFrameStep:
    @pytest.mark.asyncio
    async def test_freeze_produces_append_video(self, execution_ctx, mock_ffmpeg):
        step = FreezeFrameStep()
        step_def = {
            "id": "f1", "type": "freeze_frame",
            "inputs": {"at": 2.5, "duration": 3.0},
        }

        # Mock _probe_video_dims to avoid calling ffprobe
        with patch(
            "app.engine.steps.transforms._probe_video_dims",
            return_value=(1920, 1080, 30.0)
        ):
            result = await step.execute(step_def, execution_ctx)

        assert result.append_video is not None
        assert result.video_path is None  # freeze produces append, not replace

    @pytest.mark.asyncio
    async def test_freeze_uses_expression(self, execution_ctx, mock_ffmpeg):
        execution_ctx.step_outputs["agent"] = {"freeze_ts": 3.14}
        step = FreezeFrameStep()
        step_def = {
            "id": "f1", "type": "freeze_frame",
            "inputs": {"at": "{{steps.agent.freeze_ts}}", "duration": 2.0},
        }
        with patch(
            "app.engine.steps.transforms._probe_video_dims",
            return_value=(1920, 1080, 30.0)
        ):
            result = await step.execute(step_def, execution_ctx)
        assert result.append_video is not None


# ── ExtractFrameStep ──────────────────────────────────────────────────────────


class TestExtractFrameStep:
    @pytest.mark.asyncio
    async def test_extract_frame_png(self, execution_ctx, mock_ffmpeg):
        step = ExtractFrameStep()
        step_def = {
            "id": "e1", "type": "extract_frame",
            "inputs": {"at": 1.5, "format": "png"},
        }
        result = await step.execute(step_def, execution_ctx)
        assert "image_path" in result.outputs
        assert result.outputs["image_path"].endswith(".png")
        assert result.video_path is None

    @pytest.mark.asyncio
    async def test_extract_frame_jpg(self, execution_ctx, mock_ffmpeg):
        step = ExtractFrameStep()
        step_def = {
            "id": "e1", "type": "extract_frame",
            "inputs": {"at": 0.0, "format": "jpg"},
        }
        result = await step.execute(step_def, execution_ctx)
        assert result.outputs["image_path"].endswith(".jpg")

    @pytest.mark.asyncio
    async def test_extract_frame_default_format(self, execution_ctx, mock_ffmpeg):
        step = ExtractFrameStep()
        step_def = {"id": "e1", "type": "extract_frame", "inputs": {"at": 0.0}}
        result = await step.execute(step_def, execution_ctx)
        assert result.outputs["image_path"].endswith(".png")
