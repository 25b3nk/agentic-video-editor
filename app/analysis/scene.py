"""Scene detection using PySceneDetect."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def detect_scenes(video_path: Path, threshold: float = 27.0) -> dict:
    """
    Detect scene cuts in a video using PySceneDetect's ContentDetector.

    Args:
        video_path: Path to the video file.
        threshold: ContentDetector sensitivity (lower = more sensitive). Default 27.0.

    Returns a dict with:
        - scenes: list of {start, end, duration} dicts (timestamps in seconds)
        - scene_count: total number of detected scenes
        - cut_timestamps: list of cut-point timestamps (start of each scene after the first)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _detect_scenes_sync, video_path, threshold)


def _detect_scenes_sync(video_path: Path, threshold: float) -> dict:
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        logger.warning("scenedetect not installed; returning empty scene detection")
        return {"scenes": [], "scene_count": 0, "cut_timestamps": []}

    try:
        video = open_video(str(video_path))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video)

        scene_list = scene_manager.get_scene_list()

        scenes = []
        cut_timestamps = []

        for i, (start, end) in enumerate(scene_list):
            start_sec = round(start.get_seconds(), 3)
            end_sec = round(end.get_seconds(), 3)
            scenes.append({
                "index": i,
                "start": start_sec,
                "end": end_sec,
                "duration": round(end_sec - start_sec, 3),
            })
            if i > 0:
                cut_timestamps.append(start_sec)

        return {
            "scenes": scenes,
            "scene_count": len(scenes),
            "cut_timestamps": cut_timestamps,
        }

    except Exception as e:
        logger.error("Scene detection failed: %s", e)
        return {"scenes": [], "scene_count": 0, "cut_timestamps": [], "error": str(e)}
