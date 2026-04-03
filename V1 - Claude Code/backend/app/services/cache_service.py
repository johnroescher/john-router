"""Caching service for API responses and data."""
from typing import Optional, Any
import json
import hashlib
from datetime import datetime, timedelta

import structlog
import redis.asyncio as redis
from app.core.config import settings

logger = structlog.get_logger()


class CacheService:
    """Service for caching API responses and data using Redis."""

    def __init__(self):
        self._redis_client: Optional[redis.Redis] = None
        self._enabled = True

    async def _get_client(self) -> Optional[redis.Redis]:
        """Get or create Redis client."""
        if self._redis_client is None:
            try:
                redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')
                self._redis_client = await redis.from_url(redis_url, decode_responses=True)
                # Test connection
                await self._redis_client.ping()
                logger.info("Redis cache connected")
            except Exception as e:
                logger.warning(f"Redis not available, caching disabled: {e}")
                self._enabled = False
                return None
        return self._redis_client

    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Create a cache key from prefix and arguments."""
        key_parts = [prefix]
        if args:
            key_parts.extend(str(arg) for arg in args)
        if kwargs:
            # Sort kwargs for consistent keys
            sorted_kwargs = sorted(kwargs.items())
            key_parts.extend(f"{k}:{v}" for k, v in sorted_kwargs)
        key_str = ":".join(key_parts)
        # Hash if too long
        if len(key_str) > 200:
            key_str = f"{prefix}:{hashlib.md5(key_str.encode()).hexdigest()}"
        return key_str

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._enabled:
            return None
        try:
            client = await self._get_client()
            if not client:
                return None
            value = await client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = 3600) -> bool:
        """Set value in cache with TTL."""
        if not self._enabled:
            return False
        try:
            client = await self._get_client()
            if not client:
                return False
            value_str = json.dumps(value, default=str)
            await client.setex(key, ttl_seconds or 3600, value_str)
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self._enabled:
            return False
        try:
            client = await self._get_client()
            if not client:
                return False
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern."""
        if not self._enabled:
            return 0
        try:
            client = await self._get_client()
            if not client:
                return 0
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache clear_pattern failed for pattern {pattern}: {e}")
            return 0


# Singleton instance
_cache_service: Optional[CacheService] = None


async def get_cache_service() -> CacheService:
    """Get or create CacheService singleton."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
