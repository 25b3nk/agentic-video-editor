"""Tests for the analysis pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.analysis.pipeline import run_analysis


class TestRunAnalysis:
    @pytest.mark.asyncio
    async def test_runs_metadata_analysis(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        fake_meta = {"duration": 10.0, "width": 1920, "height": 1080, "fps": 30.0}

        with patch("app.analysis.pipeline.extract_metadata", return_value=fake_meta) as mock_meta:
            result = await run_analysis(fake_video, ["metadata"])

        mock_meta.assert_called_once_with(fake_video)
        assert result["metadata"] == fake_meta

    @pytest.mark.asyncio
    async def test_runs_beat_detection(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        fake_beats = {"bpm": 128.0, "beats": [0.5, 1.0]}

        with patch("app.analysis.pipeline.detect_beats", return_value=fake_beats) as mock_beats:
            result = await run_analysis(fake_video, ["beat_detection"])

        mock_beats.assert_called_once_with(fake_video)
        assert result["beat_detection"]["bpm"] == 128.0

    @pytest.mark.asyncio
    async def test_runs_multiple_analyses_in_parallel(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        with (
            patch("app.analysis.pipeline.extract_metadata", return_value={"duration": 5.0}),
            patch("app.analysis.pipeline.detect_beats", return_value={"bpm": 100.0, "beats": []}),
            patch("app.analysis.pipeline.detect_faces", return_value={"face_timestamps": []}),
        ):
            result = await run_analysis(fake_video, ["metadata", "beat_detection", "face_detection"])

        assert "metadata" in result
        assert "beat_detection" in result
        assert "face_detection" in result

    @pytest.mark.asyncio
    async def test_empty_requirements_returns_empty(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")
        result = await run_analysis(fake_video, [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_analysis_failure_stored_as_error(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        with patch(
            "app.analysis.pipeline.extract_metadata",
            side_effect=RuntimeError("FFprobe not found"),
        ):
            result = await run_analysis(fake_video, ["metadata"])

        assert "error" in result["metadata"]
        assert "FFprobe not found" in result["metadata"]["error"]

    @pytest.mark.asyncio
    async def test_unknown_analysis_type_skipped(self, tmp_path, caplog):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        import logging
        with caplog.at_level(logging.WARNING):
            result = await run_analysis(fake_video, ["not_yet_implemented"])

        assert "not_yet_implemented" not in result
        assert "not yet implemented" in caplog.text
