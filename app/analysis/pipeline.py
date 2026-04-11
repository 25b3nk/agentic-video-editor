"""
Analysis pipeline orchestrator.

Runs the required analyses in parallel and returns combined results.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.analysis.beats import detect_beats
from app.analysis.faces import detect_faces
from app.analysis.metadata import extract_metadata

logger = logging.getLogger(__name__)

# Analysis types that are currently implemented
IMPLEMENTED = {"metadata", "beat_detection", "face_detection"}


async def run_analysis(
    video_path: Path,
    required: list[str],
) -> dict:
    """
    Run all required analyses and return a merged results dict.

    Keys match the `requires_analysis` names from the workflow schema:
      metadata, beat_detection, face_detection, ...
    """
    tasks: dict[str, asyncio.Task] = {}

    for analysis_type in required:
        if analysis_type == "metadata":
            tasks["metadata"] = asyncio.create_task(extract_metadata(video_path))
        elif analysis_type == "beat_detection":
            tasks["beat_detection"] = asyncio.create_task(detect_beats(video_path))
        elif analysis_type == "face_detection":
            tasks["face_detection"] = asyncio.create_task(detect_faces(video_path))
        elif analysis_type not in IMPLEMENTED:
            logger.warning("Analysis type '%s' not yet implemented, skipping", analysis_type)

    if not tasks:
        return {}

    # Run all in parallel
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    analysis: dict = {}

    for key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.error("Analysis '%s' failed: %s", key, result)
            analysis[key] = {"error": str(result)}
        else:
            analysis[key] = result

    logger.info(
        "Analysis complete for %s: %s",
        video_path.name,
        {k: "ok" if "error" not in v else "error" for k, v in analysis.items()},
    )
    return analysis
