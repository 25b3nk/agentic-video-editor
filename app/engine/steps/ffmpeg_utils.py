"""
FFmpeg command builder helpers.

All functions return a list of string arguments to be passed to ffmpeg
(WITHOUT the leading 'ffmpeg -y' — that's added by BaseStep.run_ffmpeg).
"""

from __future__ import annotations

from pathlib import Path


def timestamp_to_seconds(ts: float | str | int) -> float:
    """Convert HH:MM:SS.mmm or numeric seconds to float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    ts = str(ts).strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def trim_video(input_path: Path, output_path: Path, start: float, end: float) -> list[str]:
    return [
        "-i", str(input_path),
        "-ss", str(start), "-to", str(end),
        "-c:v", "libx264", "-c:a", "aac",
        str(output_path),
    ]


def trim_video_duration(
    input_path: Path, output_path: Path, start: float, duration: float
) -> list[str]:
    return [
        "-i", str(input_path),
        "-ss", str(start), "-t", str(duration),
        "-c:v", "libx264", "-c:a", "aac",
        str(output_path),
    ]


def extract_frame(input_path: Path, output_path: Path, at: float, fmt: str = "png") -> list[str]:
    return [
        "-i", str(input_path),
        "-ss", str(at), "-vframes", "1",
        str(output_path),
    ]


def frame_to_video(
    frame_path: Path, output_path: Path, duration: float, width: int, height: int, fps: int = 30
) -> list[str]:
    """Create a video from a single still image."""
    return [
        "-loop", "1",
        "-i", str(frame_path),
        "-t", str(duration),
        "-vf", f"scale={width}:{height},fps={fps}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]


def concat_videos(input_paths: list[Path], output_path: Path) -> list[str]:
    """Concatenate multiple videos using the concat demuxer."""
    list_file = output_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in input_paths)
    )
    return [
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]


def apply_crop(
    input_path: Path, output_path: Path,
    x: int, y: int, width: int, height: int,
) -> list[str]:
    return [
        "-i", str(input_path),
        "-vf", f"crop={width}:{height}:{x}:{y}",
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def apply_crop_aspect(
    input_path: Path, output_path: Path, aspect: str
) -> list[str]:
    """Crop video to a given aspect ratio (e.g. '9:16'), center-crop."""
    num, den = (int(x) for x in aspect.split(":"))
    crop_filter = (
        f"crop=if(gt(iw/ih\\,{num}/{den})\\,ih*{num}/{den}\\,iw):"
        f"if(gt(iw/ih\\,{num}/{den})\\,ih\\,iw*{den}/{num})"
    )
    return [
        "-i", str(input_path),
        "-vf", crop_filter,
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def apply_speed_change(
    input_path: Path, output_path: Path, factor: float
) -> list[str]:
    """Change speed using setpts for video and atempo for audio."""
    video_pts = 1.0 / factor
    audio_tempo = max(0.5, min(2.0, factor))  # atempo only supports 0.5–2.0
    vf = f"setpts={video_pts:.4f}*PTS"
    af = f"atempo={audio_tempo:.4f}"
    return [
        "-i", str(input_path),
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-c:a", "aac",
        str(output_path),
    ]


def apply_color_grade(
    input_path: Path, output_path: Path,
    brightness: float = 0.0, contrast: float = 1.0, saturation: float = 1.0,
    tint_hex: str | None = None, tint_strength: float = 0.0,
) -> list[str]:
    filters = [f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}"]
    if tint_hex and tint_strength > 0:
        r = int(tint_hex[1:3], 16)
        g = int(tint_hex[3:5], 16)
        b = int(tint_hex[5:7], 16)
        s = tint_strength
        filters.append(
            f"colorchannelmixer="
            f"rr={1-s+s*r/255:.3f}:rg={s*g/255:.3f}:rb={s*b/255:.3f}:"
            f"gr={s*r/255:.3f}:gg={1-s+s*g/255:.3f}:gb={s*b/255:.3f}:"
            f"br={s*r/255:.3f}:bg={s*g/255:.3f}:bb={1-s+s*b/255:.3f}"
        )
    return [
        "-i", str(input_path),
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def apply_shake(
    input_path: Path, output_path: Path,
    intensity: float = 0.5, frequency: float = 15.0,
    start: float = 0.0, end: float | None = None,
    video_duration: float | None = None,
) -> list[str]:
    """Simulate camera shake with a crop displacement filter."""
    amplitude = int(intensity * 20)  # max 20px displacement
    freq = frequency
    # Use crop to create shake: oscillate x/y within the frame
    shake_filter = (
        f"crop=iw-{amplitude*2}:ih-{amplitude*2}:"
        f"{amplitude}+{amplitude}*sin(n*{freq}/30):"
        f"{amplitude}+{amplitude}*cos(n*{freq}/30)"
    )
    if end is not None:
        shake_filter = (
            f"crop='if(between(t,{start},{end}),"
            f"iw-{amplitude*2},{amplitude}+{amplitude}*sin(n*{freq}/30),"
            f"iw)':"
            f"'if(between(t,{start},{end}),"
            f"ih-{amplitude*2},{amplitude}+{amplitude}*cos(n*{freq}/30),"
            f"ih)':"
            # Simplified: always crop by amplitude to keep constant size
        )
        # Simpler alternative
        shake_filter = (
            f"crop=iw-{amplitude*2}:ih-{amplitude*2}:"
            f"'if(between(t\\,{start}\\,{end})\\,"
            f"{amplitude}+{amplitude}*sin(t*{freq})\\,{amplitude})':"
            f"'if(between(t\\,{start}\\,{end})\\,"
            f"{amplitude}+{amplitude}*cos(t*{freq})\\,{amplitude})'"
        )
    return [
        "-i", str(input_path),
        "-vf", shake_filter,
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def apply_rotation(
    input_path: Path, output_path: Path,
    from_angle: float = 0.0, to_angle: float = 0.0,
    easing: str = "linear",
    start: float = 0.0, end: float | None = None,
) -> list[str]:
    duration = (end - start) if end else 1.0
    if abs(from_angle - to_angle) < 0.001:
        angle_expr = f"{from_angle}*PI/180"
    else:
        # Linear interpolation between angles
        angle_expr = (
            f"({from_angle}+({to_angle}-{from_angle})"
            f"*min(max((t-{start})/{duration},0),1))*PI/180"
        )
    return [
        "-i", str(input_path),
        "-vf", f"rotate={angle_expr}:fillcolor=black@0:bilinear=1",
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def overlay_image(
    video_path: Path, image_path: Path, output_path: Path,
    start: float = 0.0, end: float | None = None,
    x: str = "(W-w)/2", y: str = "(H-h)/2",
    opacity: float = 1.0,
    fade_in_duration: float = 0.0,
) -> list[str]:
    # Scale image to fit video
    scale_filter = "[1:v]scale=iw:ih[img]"
    if fade_in_duration > 0:
        scale_filter = (
            f"[1:v]scale=iw:ih,"
            f"fade=in:st={start}:d={fade_in_duration}[img]"
        )
    time_filter = ""
    if end is not None:
        time_filter = f":enable='between(t,{start},{end})'"

    filter_complex = (
        f"{scale_filter};"
        f"[0:v][img]overlay={x}:{y}{time_filter}"
    )
    return [
        "-i", str(video_path),
        "-i", str(image_path),
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def add_text_overlay(
    input_path: Path, output_path: Path,
    text: str, font_size: int = 48,
    font_color: str = "white", stroke_color: str = "black", stroke_width: int = 2,
    x: str = "(w-text_w)/2", y: str = "h-th-20",
    start: float = 0.0, end: float | None = None,
) -> list[str]:
    enable = f"between(t,{start},{end})" if end is not None else f"gte(t,{start})"
    draw = (
        f"drawtext=text='{text}'"
        f":fontsize={font_size}"
        f":fontcolor={font_color}"
        f":borderw={stroke_width}"
        f":bordercolor={stroke_color}"
        f":x={x}:y={y}"
        f":enable='{enable}'"
    )
    return [
        "-i", str(input_path),
        "-vf", draw,
        "-c:v", "libx264", "-c:a", "copy",
        str(output_path),
    ]


def add_audio_overlay(
    video_path: Path, audio_path: Path, output_path: Path,
    video_volume: float = 1.0, audio_volume: float = 0.8,
    start_at: float = 0.0,
    fade_in: float = 0.0, fade_out: float = 0.0,
) -> list[str]:
    audio_filter = f"[1:a]volume={audio_volume}"
    if fade_in > 0:
        audio_filter += f",afade=in:d={fade_in}"
    if fade_out > 0:
        audio_filter += f",afade=out:d={fade_out}"
    audio_filter += "[music]"

    video_filter = f"[0:a]volume={video_volume}[orig]"
    mix_filter = "[orig][music]amix=inputs=2:duration=first"

    return [
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", f"{audio_filter};{video_filter};{mix_filter}",
        "-c:v", "copy", "-c:a", "aac",
        str(output_path),
    ]


def flash_transition(
    video_a: Path, video_b: Path, output_path: Path,
    duration: float = 0.15,
) -> list[str]:
    """Create a white flash transition between two videos via concat + fade."""
    # Approach: fade out + fade in over duration
    filter_complex = (
        f"[0:v]fade=out:st=0:d={duration}:color=white[va];"
        f"[1:v]fade=in:st=0:d={duration}:color=white[vb];"
        f"[va][vb]concat=n=2:v=1:a=0[v];"
        f"[0:a][1:a]concat=n=2:v=0:a=1[a]"
    )
    return [
        "-i", str(video_a),
        "-i", str(video_b),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac",
        str(output_path),
    ]


# Color grade presets
COLOR_GRADE_PRESETS: dict[str, dict] = {
    "cinematic_red": {
        "brightness": -0.05, "contrast": 1.2, "saturation": 0.9,
        "tint_hex": "#FF2200", "tint_strength": 0.25,
    },
    "noir": {
        "brightness": -0.1, "contrast": 1.4, "saturation": 0.0,
    },
    "vintage": {
        "brightness": 0.05, "contrast": 0.9, "saturation": 0.7,
        "tint_hex": "#E8C88C", "tint_strength": 0.2,
    },
}
