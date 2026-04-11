"""
Shared fixtures for the test suite.

Design principles:
- No real FFmpeg calls — all subprocess execution is mocked
- No real DB — SQLite in-memory for API tests
- No real AI API calls — all mocked
- Fixtures build minimal valid objects (WorkflowDef, ExecutionContext, etc.)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Sample workflow YAML ──────────────────────────────────────────────────────

MINIMAL_WORKFLOW_YAML = """\
version: "1.0"

metadata:
  name: "Test Workflow"
  description: "A minimal workflow for testing"
  author: "test"

parameters:
  - name: clip_duration
    type: float
    default: 5.0
    min: 1.0
    max: 30.0

requires_analysis:
  - metadata

steps:
  - id: trim_clip
    type: trim
    inputs:
      start: 0
      duration: "{{clip_duration}}"

output:
  format: mp4
  codec: h264
  quality: high
"""

POSTER_WORKFLOW_YAML = """\
version: "1.0"

metadata:
  name: "Action Poster Reveal"
  description: "Creates the action poster effect"
  author: "system"

parameters:
  - name: name_text
    type: string
    required: true
  - name: beat_index
    type: integer
    default: 0
    min: 0
    max: 5
  - name: poster_duration
    type: float
    default: 3.0
    min: 1.0
    max: 10.0
  - name: enable_particles
    type: boolean
    default: true

requires_analysis:
  - metadata
  - beat_detection

steps:
  - id: trim_intro
    type: trim
    inputs:
      start: 0
      end: 2.5

  - id: poster_segment
    type: group
    steps:
      - id: poster_freeze
        type: freeze_frame
        inputs:
          at: 2.5
          duration: "{{poster_duration}}"

      - id: red_atmosphere
        type: color_grade
        inputs:
          preset: cinematic_red

      - id: name_overlay
        type: add_text
        inputs:
          text: "{{name_text}}"
          position: bottom_center
          font_size: 72
          start: 0.5
          end: "{{poster_duration}}"

output:
  format: mp4
  codec: h264
  quality: high
"""


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_workflow_yaml() -> str:
    return MINIMAL_WORKFLOW_YAML


@pytest.fixture
def poster_workflow_yaml() -> str:
    return POSTER_WORKFLOW_YAML


@pytest.fixture
def sample_analysis() -> dict:
    return {
        "metadata": {
            "duration": 10.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "h264",
            "total_frames": 300,
        },
        "beat_detection": {
            "bpm": 128.0,
            "beats": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            "onsets": [0.3, 0.8, 1.3, 1.8, 2.3],
        },
        "face_detection": {
            "face_timestamps": [
                {"time": 1.0, "faces": [{"x": 400, "y": 100, "width": 200, "height": 250, "confidence": 0.95}]},
                {"time": 2.0, "faces": [{"x": 420, "y": 110, "width": 195, "height": 245, "confidence": 0.92}]},
            ],
            "dominant_face_timestamp": 1.0,
        },
    }


@pytest.fixture
def tmp_work_dir(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    return work


@pytest.fixture
def fake_video(tmp_path: Path) -> Path:
    """A placeholder file that pretends to be a video."""
    v = tmp_path / "input.mp4"
    v.write_bytes(b"\x00" * 100)
    return v


@pytest.fixture
def execution_ctx(fake_video: Path, tmp_work_dir: Path, sample_analysis: dict):
    """A pre-built ExecutionContext for step tests."""
    from app.engine.executor import ExecutionContext

    ctx = ExecutionContext(
        input_video=fake_video,
        params={"name_text": "JOHN WICK", "poster_duration": 3.0, "enable_particles": True},
        analysis=sample_analysis,
        work_dir=tmp_work_dir,
    )
    # current_video starts as the input video
    return ctx


@pytest.fixture
def mock_ffmpeg():
    """Patch BaseStep.run_ffmpeg to be a no-op that also creates the output file."""
    async def _fake_run_ffmpeg(self, args, ctx):
        # The output file is always the last argument
        out = Path(args[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x00" * 100)

    with patch("app.engine.steps.base.BaseStep.run_ffmpeg", new=_fake_run_ffmpeg):
        yield


@pytest.fixture
def mock_ffmpeg_direct():
    """Patch the module-level _run_ffmpeg_direct in executor."""
    async def _fake(*args, **kwargs):
        pass

    with patch("app.engine.executor._run_ffmpeg_direct", new=_fake):
        yield
