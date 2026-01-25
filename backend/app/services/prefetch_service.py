"""Prefetch service for predictive data loading."""
from typing import Optional
import structlog

from app.schemas.common import Coordinate
from app.services.trail_database import get_trail_database
from app.services.knowledge_retrieval import get_knowledge_retrieval_service
from app.services.location_knowledge import get_location_knowledge_service
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class PrefetchService:
    """Service for predictive prefetching of trail data and knowledge."""

    def __init__(self):
        pass

    async def prefetch_for_location(
        self,
        location: Coordinate,
        location_region: Optional[str] = None,
        sport_type: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Prefetch trail data and knowledge for a location.
        
        This runs in the background to speed up subsequent requests.
        
        Args:
            location: Coordinate location
            location_region: Region name (optional)
            sport_type: Sport type (optional)
            db: Database session
        """
        try:
            # Prefetch trail data
            trail_db = await get_trail_database()
            
            # Prefetch MTB trails if sport_type is MTB or not specified
            if not sport_type or sport_type in ["mtb", "emtb"]:
                await trail_db.find_mtb_trails(location, radius_km=15, limit=30)
            
            # Prefetch gravel roads if sport_type is gravel or not specified
            if not sport_type or sport_type == "gravel":
                await trail_db.find_gravel_roads(location, radius_km=15, limit=30)
            
            # Prefetch location knowledge
            if db:
                location_service = get_location_knowledge_service()
                await location_service.get_area_insights(
                    location=location,
                    location_region=location_region,
                    sport_type=sport_type,
                    db=db,
                )
            
            logger.info(f"Prefetched data for location {location.lat},{location.lng}")
        except Exception as e:
            logger.warning(f"Prefetch failed: {e}", exc_info=True)


# Singleton instance
_prefetch_service: Optional[PrefetchService] = None


async def get_prefetch_service() -> PrefetchService:
    """Get or create PrefetchService singleton."""
    global _prefetch_service
    if _prefetch_service is None:
        _prefetch_service = PrefetchService()
    return _prefetch_service
