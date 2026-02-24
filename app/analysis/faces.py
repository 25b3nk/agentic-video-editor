"""Face detection using MediaPipe (optional dependency)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def detect_faces(video_path: Path, sample_fps: float = 2.0) -> dict:
    """
    Sample the video at sample_fps and detect faces in each frame.
    Returns a dict with 'face_timestamps' (list of {time, faces: [{x, y, w, h}]}).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _detect_faces_sync, video_path, sample_fps)


def _detect_faces_sync(video_path: Path, sample_fps: float) -> dict:
    try:
        import cv2
        import mediapipe as mp
    except ImportError:
        logger.warning("mediapipe/opencv not installed; skipping face detection")
        return {"face_timestamps": [], "dominant_face_timestamp": None}

    try:
        mp_face = mp.solutions.face_detection
        cap = cv2.VideoCapture(str(video_path))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_interval = max(1, int(video_fps / sample_fps))

        results = []
        frame_idx = 0

        with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_interval == 0:
                    timestamp = frame_idx / video_fps
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    detection_result = detector.process(rgb_frame)
                    h, w = frame.shape[:2]

                    faces = []
                    if detection_result.detections:
                        for det in detection_result.detections:
                            bbox = det.location_data.relative_bounding_box
                            faces.append({
                                "x": round(bbox.xmin * w),
                                "y": round(bbox.ymin * h),
                                "width": round(bbox.width * w),
                                "height": round(bbox.height * h),
                                "confidence": round(det.score[0], 3),
                            })

                    if faces:
                        results.append({"time": round(timestamp, 3), "faces": faces})

                frame_idx += 1

        cap.release()

        # Find the timestamp where the face is most centered and confident
        dominant = _find_dominant_face_timestamp(results)

        return {
            "face_timestamps": results,
            "dominant_face_timestamp": dominant,
        }

    except Exception as e:
        logger.error("Face detection failed: %s", e)
        return {"face_timestamps": [], "dominant_face_timestamp": None, "error": str(e)}


def _find_dominant_face_timestamp(face_timestamps: list) -> float | None:
    """Find the timestamp where the face is most prominent (large + centered)."""
    if not face_timestamps:
        return None

    best_ts = None
    best_score = -1.0

    for entry in face_timestamps:
        for face in entry.get("faces", []):
            # Score: larger face area × confidence × how centered it is
            area = face["width"] * face["height"]
            confidence = face.get("confidence", 1.0)
            score = area * confidence
            if score > best_score:
                best_score = score
                best_ts = entry["time"]

    return best_ts
