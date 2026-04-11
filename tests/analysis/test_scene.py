"""Tests for scene detection analysis."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from app.analysis.pipeline import run_analysis
from app.analysis.scene import detect_scenes, _detect_scenes_sync


def _make_timecode(seconds: float) -> MagicMock:
    tc = MagicMock()
    tc.get_seconds.return_value = seconds
    return tc


def _make_scenedetect_modules(scene_list: list) -> tuple[ModuleType, ModuleType]:
    """Return (scenedetect_mock, scenedetect.detectors_mock) with a preset scene list."""
    mock_scenedetect = ModuleType("scenedetect")
    mock_detectors = ModuleType("scenedetect.detectors")

    mock_scene_manager = MagicMock()
    mock_scene_manager.get_scene_list.return_value = scene_list

    mock_scenedetect.open_video = MagicMock(return_value=MagicMock())
    mock_scenedetect.SceneManager = MagicMock(return_value=mock_scene_manager)
    mock_detectors.ContentDetector = MagicMock(return_value=MagicMock())

    return mock_scenedetect, mock_detectors


class TestDetectScenesAsync:
    @pytest.mark.asyncio
    async def test_returns_scene_dict(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        fake_result = {
            "scenes": [
                {"index": 0, "start": 0.0, "end": 5.0, "duration": 5.0},
                {"index": 1, "start": 5.0, "end": 10.0, "duration": 5.0},
            ],
            "scene_count": 2,
            "cut_timestamps": [5.0],
        }

        with patch("app.analysis.scene._detect_scenes_sync", return_value=fake_result):
            result = await detect_scenes(fake_video)

        assert result["scene_count"] == 2
        assert result["cut_timestamps"] == [5.0]
        assert len(result["scenes"]) == 2

    @pytest.mark.asyncio
    async def test_passes_threshold_to_sync(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        with patch("app.analysis.scene._detect_scenes_sync", return_value={
            "scenes": [], "scene_count": 0, "cut_timestamps": []
        }) as mock_sync:
            await detect_scenes(fake_video, threshold=15.0)

        args = mock_sync.call_args[0]
        assert args[1] == 15.0


class TestDetectScenesSyncUnit:
    def test_single_scene_no_cuts(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        scene_list = [(_make_timecode(0.0), _make_timecode(12.5))]
        mock_sd, mock_det = _make_scenedetect_modules(scene_list)

        with patch.dict(sys.modules, {"scenedetect": mock_sd, "scenedetect.detectors": mock_det}):
            result = _detect_scenes_sync(fake_video, threshold=27.0)

        assert result["scene_count"] == 1
        assert result["cut_timestamps"] == []
        assert result["scenes"][0]["start"] == 0.0
        assert result["scenes"][0]["end"] == 12.5
        assert result["scenes"][0]["duration"] == 12.5

    def test_multiple_scenes_correct_cuts(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        scene_list = [
            (_make_timecode(0.0), _make_timecode(3.0)),
            (_make_timecode(3.0), _make_timecode(7.5)),
            (_make_timecode(7.5), _make_timecode(12.0)),
        ]
        mock_sd, mock_det = _make_scenedetect_modules(scene_list)

        with patch.dict(sys.modules, {"scenedetect": mock_sd, "scenedetect.detectors": mock_det}):
            result = _detect_scenes_sync(fake_video, threshold=27.0)

        assert result["scene_count"] == 3
        assert result["cut_timestamps"] == [3.0, 7.5]
        assert result["scenes"][1]["index"] == 1

    def test_no_scenes_detected(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        mock_sd, mock_det = _make_scenedetect_modules([])

        with patch.dict(sys.modules, {"scenedetect": mock_sd, "scenedetect.detectors": mock_det}):
            result = _detect_scenes_sync(fake_video, threshold=27.0)

        assert result == {"scenes": [], "scene_count": 0, "cut_timestamps": []}

    def test_import_error_returns_empty(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        # Remove scenedetect from sys.modules so the import fails
        with patch.dict(sys.modules, {"scenedetect": None, "scenedetect.detectors": None}):
            result = _detect_scenes_sync(fake_video, threshold=27.0)

        assert result["scenes"] == []
        assert result["scene_count"] == 0
        assert "cut_timestamps" in result

    def test_exception_returns_error_dict(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        mock_sd, mock_det = _make_scenedetect_modules([])
        mock_sd.open_video.side_effect = RuntimeError("codec error")

        with patch.dict(sys.modules, {"scenedetect": mock_sd, "scenedetect.detectors": mock_det}):
            result = _detect_scenes_sync(fake_video, threshold=27.0)

        assert "error" in result
        assert "codec error" in result["error"]
        assert result["scene_count"] == 0

    def test_scene_duration_computed_correctly(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        scene_list = [(_make_timecode(1.5), _make_timecode(4.75))]
        mock_sd, mock_det = _make_scenedetect_modules(scene_list)

        with patch.dict(sys.modules, {"scenedetect": mock_sd, "scenedetect.detectors": mock_det}):
            result = _detect_scenes_sync(fake_video, threshold=27.0)

        assert result["scenes"][0]["duration"] == round(4.75 - 1.5, 3)


class TestPipelineSceneDetection:
    @pytest.mark.asyncio
    async def test_pipeline_dispatches_scene_detection(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        fake_scenes = {"scenes": [], "scene_count": 0, "cut_timestamps": []}

        with patch("app.analysis.pipeline.detect_scenes", return_value=fake_scenes) as mock_sd:
            result = await run_analysis(fake_video, ["scene_detection"])

        mock_sd.assert_called_once_with(fake_video)
        assert result["scene_detection"] == fake_scenes

    @pytest.mark.asyncio
    async def test_pipeline_scene_alongside_metadata(self, tmp_path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"\x00")

        with (
            patch("app.analysis.pipeline.extract_metadata", return_value={"duration": 10.0}),
            patch("app.analysis.pipeline.detect_scenes", return_value={
                "scenes": [{"index": 0, "start": 0.0, "end": 10.0, "duration": 10.0}],
                "scene_count": 1,
                "cut_timestamps": [],
            }),
        ):
            result = await run_analysis(fake_video, ["metadata", "scene_detection"])

        assert result["metadata"]["duration"] == 10.0
        assert result["scene_detection"]["scene_count"] == 1
