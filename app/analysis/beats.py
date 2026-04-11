"""Beat detection using librosa."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def detect_beats(video_path: Path) -> dict:
    """
    Extract audio from video then detect beats using librosa.
    Returns a dict with 'bpm', 'beats' (list of timestamps in seconds),
    and 'beat_frames'.
    """
    # Run in executor to avoid blocking the event loop (librosa is CPU-intensive)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _detect_beats_sync, video_path)


def _detect_beats_sync(video_path: Path) -> dict:
    try:
        import librosa
        import numpy as np
    except ImportError:
        logger.warning("librosa not installed; returning empty beat detection")
        return {"bpm": 0.0, "beats": [], "beat_frames": []}

    try:
        # Load audio from video (librosa can handle video files via ffmpeg backend)
        y, sr = librosa.load(str(video_path), mono=True)

        # Detect tempo and beats
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        # Also get onset strength for finding "beat drops"
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_times = librosa.frames_to_time(
            librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr),
            sr=sr,
        ).tolist()

        bpm = float(tempo) if np.isscalar(tempo) else float(tempo[0])

        return {
            "bpm": round(bpm, 2),
            "beats": [round(t, 3) for t in beat_times],
            "beat_frames": beat_frames.tolist(),
            "onsets": [round(t, 3) for t in onset_times],
        }
    except Exception as e:
        logger.error("Beat detection failed: %s", e)
        return {"bpm": 0.0, "beats": [], "beat_frames": [], "onsets": [], "error": str(e)}
