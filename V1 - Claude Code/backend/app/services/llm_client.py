"""Shared LLM client backed by NVIDIA NIM (OpenAI-compatible endpoint)."""
from __future__ import annotations

from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

_LLM_MODEL = "moonshotai/kimi-k2.5"
_LLM_BASE_URL = "https://integrate.api.nvidia.com/v1"

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
