"""Shared LLM client backed by NVIDIA NIM (OpenAI-compatible endpoint).

Kimi K2.5 is a reasoning model: it writes an internal chain-of-thought in
``message.reasoning`` before producing ``message.content``.  Both fields
consume the ``max_tokens`` budget, so callers that request small limits
(e.g. 300) may exhaust the budget during reasoning and get ``content=None``.

``MIN_MAX_TOKENS`` ensures every request has enough headroom.
``extract_llm_text`` reads ``content`` first, falls back to ``reasoning``.
"""
from __future__ import annotations

from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

_LLM_MODEL = "moonshotai/kimi-k2.5"
_LLM_BASE_URL = "https://integrate.api.nvidia.com/v1"
MIN_MAX_TOKENS = 16384

_client: Optional[AsyncOpenAI] = None


def get_llm_client() -> Optional[AsyncOpenAI]:
    """Return the singleton AsyncOpenAI client pointed at NVIDIA NIM."""
    global _client
    if _client is None:
        api_key = settings.nvidia_api_key
        if not api_key:
            return None
        _client = AsyncOpenAI(base_url=_LLM_BASE_URL, api_key=api_key)
    return _client


def get_llm_model() -> str:
    return _LLM_MODEL


def clamp_max_tokens(requested: int) -> int:
    """Ensure max_tokens is at least MIN_MAX_TOKENS for reasoning models."""
    return max(requested, MIN_MAX_TOKENS)


def extract_llm_text(choice) -> str:
    """Get usable text from a chat completion choice.

    Kimi K2.5 puts its answer in ``content`` and reasoning in ``reasoning``.
    When the token budget is tight, ``content`` may be None while
    ``reasoning`` still has useful text.
    """
    if choice.message.content:
        return choice.message.content
    reasoning = getattr(choice.message, "reasoning", None)
    if reasoning:
        return reasoning
    return ""
