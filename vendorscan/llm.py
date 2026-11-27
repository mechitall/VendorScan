"""Minimal JSON chat client for Nebius Token Factory (OpenAI-compatible API)."""
from __future__ import annotations

import json
import os

import httpx

from .config import load_env, require
from .settings import LLM_TIMEOUT

BASE_URL = "https://api.tokenfactory.nebius.com/v1"
# Non-reasoning model: answers directly, so JSON never gets cut off by hidden reasoning.
DEFAULT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


def available() -> bool:
    load_env()
    return bool(os.environ.get("NEBIUS_API_KEY"))


async def chat_json(system: str, user: str, *, client: httpx.AsyncClient,
                    max_tokens: int = 1200) -> dict:
    """One chat completion in JSON mode; returns the parsed object."""
    load_env()
    response = await client.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {require('NEBIUS_API_KEY')}"},
        json={
            "model": os.environ.get("NEBIUS_MODEL", DEFAULT_MODEL),
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        },
        timeout=LLM_TIMEOUT,
    )
    response.raise_for_status()
    choice = response.json()["choices"][0]
    content = choice["message"].get("content")
    if not content:
        raise RuntimeError(f"Nebius returned no content (finish_reason={choice.get('finish_reason')})")
    return json.loads(content)
