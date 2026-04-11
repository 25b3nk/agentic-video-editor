"""Claude API client for agent_decision steps."""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def ask_claude(system_prompt: str, user_message: str) -> str:
    """
    Send a message to Claude and return the text response.

    Uses the Anthropic async client.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    logger.debug("Calling Claude model: %s", settings.claude_model)
    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text
