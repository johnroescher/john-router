"""Trailforks API integration."""
from typing import Optional, List, Dict, Any
import httpx
import structlog

from app.core.config import settings
from app.services.cache_service import get_cache_service
from app.schemas.common import Coordinate

logger = structlog.get_logger()


class TrailforksAPI:
    """Client for Trailforks API."""

    BASE_URL = "https://www.trailforks.com/api/1"

    def __init__(self):
        self.api_key = getattr(settings, 'trailforks_api_key', None)
        self.enabled = self.api_key is not None

    async def search_trails(
        self,
        location: Optional[Coordinate] = None,
        location_name: Optional[str] = None,
        sport_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search for trails in an area.
        
        Args:
            location: Coordinate location
            location_name: Location name (e.g., "Moab, UT")
            sport_type: Sport type filter
            limit: Maximum number of results
            
        Returns:
            List of trail dictionaries
        """
        if not self.enabled:
            logger.debug("Trailforks API not enabled (no API key)")
            return []

        # Check cache first
        cache_service = await get_cache_service()
        cache_key = cache_service._make_key(
            "trailforks:search",
            location_name=location_name,
            sport_type=sport_type,
            limit=limit,
        )
        cached = await cache_service.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for Trailforks search: {location_name}")
            return cached

        try:
            # Build query parameters
            params = {
                "key": self.api_key,
                "limit": limit,
            }
            
            if location:
                params["lat"] = location.lat
                params["lon"] = location.lng
            elif location_name:
                params["q"] = location_name

            if sport_type:
                # Map our sport types to Trailforks types
                sport_map = {
                    "mtb": "mtb",
                    "gravel": "gravel",
                    "road": "road",
                }
                if sport_type in sport_map:
                    params["activitytype"] = sport_map[sport_type]

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.BASE_URL}/trails", params=params)
                response.raise_for_status()
                data = response.json()

                trails = data.get("trails", [])
                
                # Cache the results
                await cache_service.set(cache_key, trails, ttl_seconds=86400)  # 24 hours
                
                logger.info(f"Retrieved {len(trails)} trails from Trailforks for {location_name}")
                return trails
        except Exception as e:
            logger.warning(f"Trailforks API error: {e}", exc_info=True)
            return []

    async def get_trail_details(self, trail_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific trail."""
        if not self.enabled:
            return None

        # Check cache
        cache_service = await get_cache_service()
        cache_key = cache_service._make_key("trailforks:trail", trail_id=trail_id)
        cached = await cache_service.get(cache_key)
        if cached:
            return cached

        try:
            params = {
                "key": self.api_key,
                "trailid": trail_id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.BASE_URL}/trail", params=params)
                response.raise_for_status()
                data = response.json()

                trail = data.get("trail")
                
                if trail:
                    await cache_service.set(cache_key, trail, ttl_seconds=86400)
                
                return trail
        except Exception as e:
            logger.warning(f"Trailforks API error getting trail {trail_id}: {e}")
            return None


# Singleton instance
_trailforks_api: Optional[TrailforksAPI] = None


async def get_trailforks_api() -> TrailforksAPI:
    """Get or create TrailforksAPI singleton."""
    global _trailforks_api
    if _trailforks_api is None:
        _trailforks_api = TrailforksAPI()
    return _trailforks_api
