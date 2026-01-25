"""Location knowledge service for querying local cycling knowledge."""
from typing import Optional, List
from uuid import UUID

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location_knowledge import LocationKnowledge
from app.schemas.knowledge import AreaInsights, NamedRoute
from app.schemas.common import Coordinate
from app.schemas.route import RouteConstraints

logger = structlog.get_logger()


class LocationKnowledgeService:
    """Service for retrieving local cycling knowledge for regions."""

    def __init__(self):
        pass

    async def get_area_insights(
        self,
        location: Optional[Coordinate] = None,
        location_region: Optional[str] = None,
        sport_type: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[AreaInsights]:
        """Return local knowledge about cycling in this area and sport type.
        
        Args:
            location: Coordinate location (optional)
            location_region: Region name as string (optional, e.g., "Boulder, CO")
            sport_type: Sport type filter (optional)
            db: Database session
            
        Returns:
            AreaInsights object if found, None otherwise
        """
        if not db:
            logger.warning("No database session provided to get_area_insights")
            return None

        if not location_region and not location:
            return None

        try:
            # Build query conditions
            conditions = []
            if location_region:
                conditions.append(LocationKnowledge.location_region == location_region)
            if sport_type:
                conditions.append(LocationKnowledge.sport_type == sport_type)

            if not conditions:
                return None

            # Query for knowledge entries
            result = await db.execute(
                select(LocationKnowledge).where(and_(*conditions))
            )
            knowledge_entries = result.scalars().all()

            if not knowledge_entries:
                return None

            # Aggregate into AreaInsights
            insights = AreaInsights(
                location_region=location_region,
                sport_type=sport_type,
            )

            for entry in knowledge_entries:
                if entry.knowledge_type == "popular_route" and entry.name:
                    insights.popular_routes.append(entry.name)
                elif entry.knowledge_type == "trail_system" and entry.name:
                    insights.trail_systems.append(entry.name)
                elif entry.knowledge_type == "local_tip" and entry.description:
                    insights.local_tips.append(entry.description)
                elif entry.knowledge_type == "notable_feature" and entry.name:
                    insights.notable_features.append(entry.name)
                elif entry.knowledge_type == "seasonal" and entry.description:
                    insights.seasonal_considerations.append(entry.description)
                elif entry.knowledge_type == "difficulty" and entry.metadata_json:
                    if not insights.difficulty_info:
                        insights.difficulty_info = {}
                    insights.difficulty_info.update(entry.metadata_json)

            return insights if (insights.popular_routes or insights.trail_systems or 
                               insights.notable_features or insights.local_tips) else None
        except Exception as e:
            logger.error(f"Error retrieving area insights: {e}", exc_info=True)
            return None

    async def suggest_named_routes(
        self,
        location: Optional[Coordinate] = None,
        location_region: Optional[str] = None,
        constraints: Optional[RouteConstraints] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[NamedRoute]:
        """Suggest well-known or famous routes in the area that meet the constraints (if any).
        
        Args:
            location: Coordinate location (optional)
            location_region: Region name (optional)
            constraints: Route constraints to match against
            db: Database session
            
        Returns:
            List of NamedRoute objects
        """
        if not db:
            logger.warning("No database session provided to suggest_named_routes")
            return []

        if not location_region and not location:
            return []

        try:
            conditions = [LocationKnowledge.knowledge_type == "popular_route"]
            
            if location_region:
                conditions.append(LocationKnowledge.location_region == location_region)
            
            if constraints:
                discipline = getattr(constraints, "discipline", None)
                sport_type = getattr(constraints, "sport_type", None)
                if discipline and discipline != "any":
                    conditions.append(LocationKnowledge.sport_type == discipline)
                elif sport_type:
                    conditions.append(LocationKnowledge.sport_type == sport_type)

            result = await db.execute(
                select(LocationKnowledge).where(and_(*conditions))
            )
            entries = result.scalars().all()

            named_routes = []
            for entry in entries:
                # Check if route matches distance constraints if provided
                if constraints and entry.metadata_json and "distance_km" in entry.metadata_json:
                    route_distance = entry.metadata_json["distance_km"]
                    distance_range = getattr(constraints, "distance_km", None)
                    if distance_range:
                        min_dist = distance_range.min
                        max_dist = distance_range.max
                        if min_dist and route_distance < min_dist:
                            continue
                        if max_dist and route_distance > max_dist:
                            continue
                    else:
                        target_meters = getattr(constraints, "target_distance_meters", None)
                        if target_meters:
                            target_km = target_meters / 1000
                            if route_distance < target_km * 0.7 or route_distance > target_km * 1.3:
                                continue

                named_route = NamedRoute(
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
                named_routes.append(named_route)

            # Sort by confidence if available
            named_routes.sort(key=lambda x: x.confidence or 0.0, reverse=True)
            return named_routes
        except Exception as e:
            logger.error(f"Error suggesting named routes: {e}", exc_info=True)
            return []


# Singleton instance
_location_knowledge_service: Optional[LocationKnowledgeService] = None


def get_location_knowledge_service() -> LocationKnowledgeService:
    """Get or create LocationKnowledgeService singleton."""
    global _location_knowledge_service
    if _location_knowledge_service is None:
        _location_knowledge_service = LocationKnowledgeService()
    return _location_knowledge_service
