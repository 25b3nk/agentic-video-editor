"""Gemini Imagen API client for image generation steps."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


async def generate_image_from_photo(
    input_image_path: str | Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str = "",
) -> None:
    """
    Call Gemini Imagen to stylize/transform a photo.

    Saves the result to output_path.
    Uses Gemini's image-to-image generation capability.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _generate_sync,
        str(input_image_path),
        output_path,
        prompt,
        negative_prompt,
    )


def _generate_sync(
    input_image_path: str,
    output_path: Path,
    prompt: str,
    negative_prompt: str,
) -> None:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")

    try:
        import google.generativeai as genai
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "google-generativeai and Pillow are required. "
            "Run: pip install google-generativeai Pillow"
        )

    genai.configure(api_key=settings.gemini_api_key)

    # Load input image
    input_image = Image.open(input_image_path)

    # Build full prompt
    full_prompt = prompt
    if negative_prompt:
        full_prompt += f". Avoid: {negative_prompt}"

    logger.info("Calling Gemini Imagen with prompt: %s", full_prompt[:100])

    # Use Gemini 2.0 Flash for image generation (supports image output)
    model = genai.GenerativeModel("gemini-2.0-flash-exp-image-generation")

    response = model.generate_content(
        [full_prompt, input_image],
        generation_config=genai.GenerationConfig(response_mime_type="image/png"),
    )

    # Extract image from response
    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            image_data = base64.b64decode(part.inline_data.data)
            output_path.write_bytes(image_data)
            logger.info("Gemini Imagen output saved to: %s", output_path)
            return

    raise RuntimeError("Gemini did not return an image in the response")
