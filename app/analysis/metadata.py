"""Video metadata extraction via FFprobe."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import settings


async def extract_metadata(video_path: Path) -> dict:
    """Run FFprobe and return normalized video metadata."""
    cmd = [
        settings.ffprobe_bin,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(video_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFprobe failed: {stderr.decode(errors='replace')[:1000]}"
        )

    data = json.loads(stdout)
    return _parse_probe_output(data)


def _parse_probe_output(data: dict) -> dict:
    meta: dict = {}

    fmt = data.get("format", {})
    meta["duration"] = float(fmt.get("duration", 0))
    meta["size_bytes"] = int(fmt.get("size", 0))
    meta["format_name"] = fmt.get("format_name", "")
    meta["bit_rate"] = int(fmt.get("bit_rate", 0))

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and "width" not in meta:
            meta["width"] = int(stream.get("width", 0))
            meta["height"] = int(stream.get("height", 0))
            meta["codec"] = stream.get("codec_name", "")
            meta["pix_fmt"] = stream.get("pix_fmt", "")

            r_frame_rate = stream.get("r_frame_rate", "30/1")
            try:
                num, den = r_frame_rate.split("/")
                meta["fps"] = round(float(num) / float(den), 3)
            except Exception:
                meta["fps"] = 30.0

            meta["video_bit_rate"] = int(stream.get("bit_rate", 0))
            nb_frames = stream.get("nb_frames")
            if nb_frames:
                meta["total_frames"] = int(nb_frames)

        elif codec_type == "audio" and "audio_codec" not in meta:
            meta["audio_codec"] = stream.get("codec_name", "")
            meta["audio_channels"] = int(stream.get("channels", 0))
            meta["sample_rate"] = int(stream.get("sample_rate", 0))

    # Compute total_frames from duration and fps if not set
    if "total_frames" not in meta and meta.get("fps") and meta.get("duration"):
        meta["total_frames"] = int(meta["duration"] * meta["fps"])

    return meta
