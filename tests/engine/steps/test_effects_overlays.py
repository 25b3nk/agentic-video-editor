"""Tests for effect and overlay step executors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.engine.steps.effects import ColorGradeStep, ParticlesStep, RotateStep, ShakeStep, TransitionStep
from app.engine.steps.overlays import AddAudioStep, AddImageStep, AddTextStep, NoopStep


# ── ShakeStep ─────────────────────────────────────────────────────────────────


class TestShakeStep:
    @pytest.mark.asyncio
    async def test_shake_basic(self, execution_ctx, mock_ffmpeg):
        step = ShakeStep()
        result = await step.execute(
            {"id": "s", "type": "shake", "inputs": {"intensity": 0.6, "frequency": 15.0}},
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_shake_with_time_range(self, execution_ctx, mock_ffmpeg):
        step = ShakeStep()
        result = await step.execute(
            {"id": "s", "type": "shake", "inputs": {"intensity": 0.5, "start": 0, "end": 1.5}},
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_shake_default_intensity(self, execution_ctx, mock_ffmpeg):
        step = ShakeStep()
        result = await step.execute({"id": "s", "type": "shake", "inputs": {}}, execution_ctx)
        assert result.video_path is not None


# ── RotateStep ────────────────────────────────────────────────────────────────


class TestRotateStep:
    @pytest.mark.asyncio
    async def test_static_rotation(self, execution_ctx, mock_ffmpeg):
        step = RotateStep()
        result = await step.execute(
            {"id": "r", "type": "rotate", "inputs": {"angle": 45.0}},
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_animated_rotation(self, execution_ctx, mock_ffmpeg):
        step = RotateStep()
        result = await step.execute(
            {
                "id": "r", "type": "rotate",
                "inputs": {"from_angle": -1.5, "to_angle": 1.5, "easing": "ease_in_out", "start": 0, "end": 3.0},
            },
            execution_ctx,
        )
        assert result.video_path is not None


# ── ColorGradeStep ────────────────────────────────────────────────────────────


class TestColorGradeStep:
    @pytest.mark.asyncio
    async def test_cinematic_red_preset(self, execution_ctx, mock_ffmpeg):
        step = ColorGradeStep()
        result = await step.execute(
            {"id": "cg", "type": "color_grade", "inputs": {"preset": "cinematic_red"}},
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_noir_preset(self, execution_ctx, mock_ffmpeg):
        step = ColorGradeStep()
        result = await step.execute(
            {"id": "cg", "type": "color_grade", "inputs": {"preset": "noir"}},
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_manual_adjustments(self, execution_ctx, mock_ffmpeg):
        step = ColorGradeStep()
        result = await step.execute(
            {
                "id": "cg", "type": "color_grade",
                "inputs": {
                    "brightness": 0.1, "contrast": 1.3,
                    "saturation": 0.8, "tint": "#FF0000", "tint_strength": 0.2,
                },
            },
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_preset_with_override(self, execution_ctx, mock_ffmpeg):
        step = ColorGradeStep()
        # Preset but with a tint override
        result = await step.execute(
            {
                "id": "cg", "type": "color_grade",
                "inputs": {"preset": "cinematic_red", "tint": "#FF2200", "tint_strength": 0.3},
            },
            execution_ctx,
        )
        assert result.video_path is not None


# ── ParticlesStep ─────────────────────────────────────────────────────────────


class TestParticlesStep:
    @pytest.mark.asyncio
    async def test_fire_effect(self, execution_ctx, mock_ffmpeg):
        step = ParticlesStep()
        result = await step.execute(
            {
                "id": "p", "type": "particles",
                "inputs": {"effect": "fire", "intensity": 0.7, "start": 0.2, "end": 3.0},
            },
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_unknown_effect_passthrough(self, execution_ctx, mock_ffmpeg, tmp_work_dir):
        """Unknown effects pass through unchanged (copy source file)."""
        step = ParticlesStep()
        result = await step.execute(
            {"id": "p", "type": "particles", "inputs": {"effect": "snow", "intensity": 0.5}},
            execution_ctx,
        )
        assert result.video_path is not None


# ── TransitionStep ────────────────────────────────────────────────────────────


class TestTransitionStep:
    @pytest.mark.asyncio
    async def test_transition_with_two_segments(self, execution_ctx, mock_ffmpeg, tmp_work_dir):
        # Set up two pending segments
        seg_a = tmp_work_dir / "seg_a.mp4"
        seg_b = tmp_work_dir / "seg_b.mp4"
        seg_a.write_bytes(b"\x00" * 100)
        seg_b.write_bytes(b"\x00" * 100)
        execution_ctx.pending_segments = [seg_a, seg_b]

        step = TransitionStep()
        result = await step.execute(
            {"id": "t", "type": "transition", "inputs": {"effect": "flash", "duration": 0.15}},
            execution_ctx,
        )
        # Two segments merged into one
        assert len(execution_ctx.pending_segments) == 1

    @pytest.mark.asyncio
    async def test_transition_stored_when_no_segments(self, execution_ctx, mock_ffmpeg):
        execution_ctx.pending_segments = []
        step = TransitionStep()
        await step.execute(
            {"id": "t", "type": "transition", "inputs": {"effect": "flash", "duration": 0.15}},
            execution_ctx,
        )
        # Pending transition recorded
        assert execution_ctx.pending_transition is not None
        assert execution_ctx.pending_transition["effect"] == "flash"


# ── AddTextStep ───────────────────────────────────────────────────────────────


class TestAddTextStep:
    @pytest.mark.asyncio
    async def test_basic_text(self, execution_ctx, mock_ffmpeg):
        step = AddTextStep()
        result = await step.execute(
            {
                "id": "at", "type": "add_text",
                "inputs": {
                    "text": "JOHN WICK",
                    "position": "bottom_center",
                    "font_size": 72,
                    "start": 0.5, "end": 3.0,
                },
            },
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_text_from_param(self, execution_ctx, mock_ffmpeg):
        step = AddTextStep()
        result = await step.execute(
            {"id": "at", "type": "add_text", "inputs": {"text": "{{name_text}}", "start": 0}},
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_text_positions(self, execution_ctx, mock_ffmpeg):
        step = AddTextStep()
        for position in ("center", "top_left", "bottom_center", "custom"):
            result = await step.execute(
                {"id": "at", "type": "add_text", "inputs": {"text": "Hi", "position": position}},
                execution_ctx,
            )
            assert result.video_path is not None


# ── AddImageStep ──────────────────────────────────────────────────────────────


class TestAddImageStep:
    @pytest.mark.asyncio
    async def test_overlay_existing_image(self, execution_ctx, mock_ffmpeg, tmp_path):
        img = tmp_path / "poster.png"
        img.write_bytes(b"\x00" * 100)

        step = AddImageStep()
        result = await step.execute(
            {
                "id": "ai", "type": "add_image",
                "inputs": {
                    "source": str(img),
                    "position": "center",
                    "opacity": 1.0,
                    "animation": "fade_in",
                    "animation_duration": 0.3,
                    "start": 0, "end": 3.0,
                },
            },
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_overlay_missing_image_raises(self, execution_ctx, mock_ffmpeg):
        step = AddImageStep()
        with pytest.raises(FileNotFoundError):
            await step.execute(
                {"id": "ai", "type": "add_image", "inputs": {"source": "/nonexistent/poster.png"}},
                execution_ctx,
            )


# ── AddAudioStep ──────────────────────────────────────────────────────────────


class TestAddAudioStep:
    @pytest.mark.asyncio
    async def test_add_existing_audio(self, execution_ctx, mock_ffmpeg, tmp_path):
        audio = tmp_path / "music.mp3"
        audio.write_bytes(b"\x00" * 100)

        step = AddAudioStep()
        result = await step.execute(
            {
                "id": "aa", "type": "add_audio",
                "inputs": {
                    "source": str(audio),
                    "volume": 0.8,
                    "duck_original": 0.3,
                    "fade_in": 0.5,
                    "fade_out": 1.0,
                },
            },
            execution_ctx,
        )
        assert result.video_path is not None

    @pytest.mark.asyncio
    async def test_null_source_is_noop(self, execution_ctx, mock_ffmpeg):
        execution_ctx.params["music_file"] = None
        step = AddAudioStep()
        result = await step.execute(
            {"id": "aa", "type": "add_audio", "inputs": {"source": "{{music_file}}"}},
            execution_ctx,
        )
        # No video modification when source is None
        assert result.video_path is None

    @pytest.mark.asyncio
    async def test_missing_audio_file_raises(self, execution_ctx, mock_ffmpeg):
        step = AddAudioStep()
        with pytest.raises(FileNotFoundError):
            await step.execute(
                {"id": "aa", "type": "add_audio", "inputs": {"source": "/nonexistent/music.mp3"}},
                execution_ctx,
            )


# ── NoopStep ──────────────────────────────────────────────────────────────────


class TestNoopStep:
    @pytest.mark.asyncio
    async def test_noop_produces_empty_result(self, execution_ctx):
        step = NoopStep()
        result = await step.execute({"id": "n", "type": "noop"}, execution_ctx)
        assert result.video_path is None
        assert result.append_video is None
        assert result.outputs == {}
