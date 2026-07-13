"""
Thin wrapper around the Anthropic Messages API.

Kept in one place so the rest of the app (router, RAG, text-to-SQL) never
imports the SDK directly. Swapping providers later means editing only this
file plus the model name in config.py.
"""
import json
from typing import AsyncGenerator, Optional

import anthropic

from app import config

_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


async def complete(system: str, user: str, max_tokens: int = 1024) -> str:
    """Single non-streaming completion. Used for routing + tool-generation
    steps where we need the whole response before acting on it."""
    resp = await _client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


async def complete_json(system: str, user: str, max_tokens: int = 512) -> dict:
    """Completion that is expected to return a single JSON object.
    Strips markdown code fences defensively before parsing."""
    raw = await complete(system, user, max_tokens=max_tokens)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Best-effort recovery: grab the first {...} block in the text.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        raise


async def stream(system: str, user: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
    """Token-level streaming completion, used for the final answer only."""
    async with _client.messages.stream(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream_ctx:
        async for text in stream_ctx.text_stream:
            yield text
