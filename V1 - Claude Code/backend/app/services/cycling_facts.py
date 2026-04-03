"""Cycling facts service with lightweight caching."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import List, Optional

import structlog

logger = structlog.get_logger()


class CyclingFactsService:
    """Generates short cycling facts and caches them briefly."""

    def __init__(self) -> None:
        from app.services.llm_client import clamp_max_tokens, extract_llm_text, get_llm_client, get_llm_model
        self.client = get_llm_client()
        self.model = get_llm_model()
        self._cache_facts: List[str] = []
        self._cache_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    def _cache_valid(self) -> bool:
        return bool(self._cache_facts) and self._cache_expires_at is not None and datetime.utcnow() < self._cache_expires_at

    async def get_facts(self, count: int = 6) -> List[str]:
        if self._cache_valid():
            return self._cache_facts[:count]

        async with self._lock:
            if self._cache_valid():
                return self._cache_facts[:count]
            facts = await self._generate_facts(count)
            self._cache_facts = facts
            self._cache_expires_at = datetime.utcnow() + timedelta(minutes=20)
            return facts[:count]

    async def _generate_facts(self, count: int) -> List[str]:
        fallback = self._fallback_facts()
        if not self.client:
            return fallback[:count]

        prompt = (
            "Return a JSON array of short, accurate, general cycling facts. "
            f"Provide {count} items. "
            "Each fact should be under 90 characters, no emojis, no numbering, no markdown."
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=clamp_max_tokens(300),
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )
            text = extract_llm_text(response.choices[0]) if response.choices else ""
            facts = self._parse_facts(text)
            if not facts:
                return fallback[:count]
            return facts[:count]
        except Exception as exc:
            logger.warning("Cycling facts generation failed", error=str(exc))
            return fallback[:count]

    def _parse_facts(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []

        facts: List[str] = []
        try:
            data = json.loads(text)
            if isinstance(data, list):
                facts = [str(item).strip() for item in data]
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                try:
                    data = json.loads(match.group(0))
                    if isinstance(data, list):
                        facts = [str(item).strip() for item in data]
                except json.JSONDecodeError:
                    facts = []

        cleaned: List[str] = []
        for fact in facts:
            if not fact:
                continue
            fact = re.sub(r"^[\-\*\d\.\)\s]+", "", fact).strip()
            if not fact:
                continue
            cleaned.append(fact[:120])
        return cleaned

    @staticmethod
    def _fallback_facts() -> List[str]:
        return [
            "A steady cadence can save energy on longer rides.",
            "Tire pressure affects comfort, speed, and grip.",
            "Headwinds make flat roads feel like short climbs.",
            "Rolling resistance drops when tires are properly inflated.",
            "Small grade changes can add up to big effort over distance.",
            "Keeping a relaxed upper body reduces fatigue.",
            "A clean, lubricated chain improves efficiency.",
            "Drafting behind a rider reduces effort at higher speeds.",
            "Short climbs reward pacing more than brute force.",
            "Smooth pedaling improves traction on loose surfaces.",
        ]


_cycling_facts_service: Optional[CyclingFactsService] = None


def get_cycling_facts_service() -> CyclingFactsService:
    """Get or create CyclingFactsService singleton."""
    global _cycling_facts_service
    if _cycling_facts_service is None:
        _cycling_facts_service = CyclingFactsService()
    return _cycling_facts_service
