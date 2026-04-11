"""Tests for video metadata extraction (FFprobe)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.metadata import _parse_probe_output, extract_metadata


# ── _parse_probe_output (pure function, no mocking needed) ───────────────────


class TestParseProbeOutput:
    def _make_probe_data(self, **overrides):
        base = {
            "format": {
                "duration": "10.5",
                "size": "5242880",
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "bit_rate": "4000000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                    "pix_fmt": "yuv420p",
                    "bit_rate": "3500000",
                    "nb_frames": "315",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                    "sample_rate": "44100",
                },
            ],
        }
        base.update(overrides)
        return base

    def test_duration_parsed(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["duration"] == pytest.approx(10.5)

    def test_video_dimensions(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["width"] == 1920
        assert result["height"] == 1080

    def test_fps_parsed(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["fps"] == pytest.approx(30.0)

    def test_fps_fractional(self):
        data = self._make_probe_data()
        data["streams"][0]["r_frame_rate"] = "24000/1001"
        result = _parse_probe_output(data)
        assert result["fps"] == pytest.approx(23.976, rel=1e-3)

    def test_codec_captured(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["codec"] == "h264"

    def test_audio_codec(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["audio_codec"] == "aac"
        assert result["audio_channels"] == 2

    def test_total_frames_from_stream(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["total_frames"] == 315

    def test_total_frames_computed_when_missing(self):
        data = self._make_probe_data()
        del data["streams"][0]["nb_frames"]
        result = _parse_probe_output(data)
        # 10.5s * 30fps = 315
        assert result["total_frames"] == 315

    def test_size_and_bitrate(self):
        result = _parse_probe_output(self._make_probe_data())
        assert result["size_bytes"] == 5242880
        assert result["bit_rate"] == 4000000

    def test_no_audio_stream(self):
        data = self._make_probe_data()
        data["streams"] = [s for s in data["streams"] if s["codec_type"] != "audio"]
        result = _parse_probe_output(data)
        assert "audio_codec" not in result

    def test_empty_streams(self):
        data = {"format": {"duration": "5.0", "size": "100", "format_name": "mp4", "bit_rate": "0"}, "streams": []}
        result = _parse_probe_output(data)
        assert result["duration"] == 5.0
        assert "width" not in result


# ── extract_metadata (subprocess mocked) ─────────────────────────────────────


class TestExtractMetadata:
    @pytest.mark.asyncio
    async def test_calls_ffprobe_and_returns_metadata(self, tmp_path):
        fake_video = tmp_path / "input.mp4"
        fake_video.write_bytes(b"\x00")

        probe_output = {
            "format": {"duration": "8.0", "size": "1000000", "format_name": "mp4", "bit_rate": "1000000"},
            "streams": [
                {
                    "codec_type": "video", "codec_name": "h264",
                    "width": 1280, "height": 720, "r_frame_rate": "25/1",
                    "pix_fmt": "yuv420p", "bit_rate": "900000", "nb_frames": "200",
                },
            ],
        }

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(probe_output).encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extract_metadata(fake_video)

        assert result["duration"] == 8.0
        assert result["width"] == 1280
        assert result["height"] == 720
        assert result["fps"] == 25.0

    @pytest.mark.asyncio
    async def test_ffprobe_failure_raises(self, tmp_path):
        fake_video = tmp_path / "input.mp4"
        fake_video.write_bytes(b"\x00")

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"No such file"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="FFprobe failed"):
                await extract_metadata(fake_video)
