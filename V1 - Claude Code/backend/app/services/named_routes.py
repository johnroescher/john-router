"""Named routes service for finding and using famous routes."""
from typing import Optional, List
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.location_knowledge import get_location_knowledge_service
from app.schemas.knowledge import NamedRoute
from app.schemas.common import Coordinate
from app.schemas.route import RouteConstraints

logger = structlog.get_logger()


class NamedRouteService:
    """Service for finding and suggesting famous/named routes."""

    def __init__(self):
        self.location_knowledge_service = None

    async def find_named_routes(
        self,
        location: Optional[Coordinate] = None,
        location_region: Optional[str] = None,
        constraints: Optional[RouteConstraints] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[NamedRoute]:
        """Find named routes matching the constraints.
        
        Args:
            location: Coordinate location
            location_region: Region name
            constraints: Route constraints to match
            db: Database session
            
        Returns:
            List of NamedRoute objects
        """
        if not db:
            return []

        try:
            location_service = get_location_knowledge_service()
            named_routes = await location_service.suggest_named_routes(
                location=location,
                location_region=location_region,
                constraints=constraints,
                db=db,
            )
            return named_routes
        except Exception as e:
            logger.error(f"Error finding named routes: {e}", exc_info=True)
            return []

    async def get_named_route_by_name(
        self,
        route_name: str,
        location_region: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[NamedRoute]:
        """Get a specific named route by name.
        
        Args:
            route_name: Name of the route (e.g., "Slickrock Trail")
            location_region: Region to search in
            db: Database session
            
        Returns:
            NamedRoute if found, None otherwise
        """
        if not db:
            return None

        try:
            from app.models.location_knowledge import LocationKnowledge
            from sqlalchemy import select, and_, or_

            conditions = [
                LocationKnowledge.knowledge_type == "popular_route",
                or_(
                    LocationKnowledge.name.ilike(f"%{route_name}%"),
                    LocationKnowledge.description.ilike(f"%{route_name}%"),
                ),
            ]
            if location_region:
                conditions.append(LocationKnowledge.location_region == location_region)

            result = await db.execute(
                select(LocationKnowledge).where(and_(*conditions)).limit(1)
            )
            entry = result.scalar_one_or_none()

            if entry:
                return NamedRoute(
                    id=entry.id,
                    name=entry.name or "Unknown Route",
                    description=entry.description,
                    location_region=entry.location_region,
                    sport_type=entry.sport_type,
                    distance_km=entry.metadata_json.get("distance_km") if entry.metadata_json else None,
                    elevation_gain_m=entry.metadata_json.get("elevation_gain_m") if entry.metadata_json else None,
                    difficulty=entry.metadata_json.get("difficulty") if entry.metadata_json else None,
                    geometry=entry.geometry,
                    metadata=entry.metadata_json,
                    confidence=entry.confidence,
                    source=entry.source,
                )
            return None
        except Exception as e:
            logger.error(f"Error getting named route by name: {e}", exc_info=True)
            return None


# Singleton instance
_named_route_service: Optional[NamedRouteService] = None


async def get_named_route_service() -> NamedRouteService:
    """Get or create NamedRouteService singleton."""
    global _named_route_service
    if _named_route_service is None:
        _named_route_service = NamedRouteService()
    return _named_route_service
