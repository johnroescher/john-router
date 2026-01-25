"""User context service for managing user preferences and route history.

This service enables the system to remember user preferences and learn from
completed routes, allowing for personalized route planning over time.
"""
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_context import UserPreference, RouteHistory
from app.models.route import Route
from app.schemas.user_context import UserPreferences, RouteFeedback
from app.schemas.common import Coordinate
from app.core.feature_flags import is_feature_enabled

logger = structlog.get_logger()


class UserContextService:
    """Service for managing user preferences and learning from route history."""

    def __init__(self):
        pass

    async def get_user_preferences(
        self,
        user_id: Optional[UUID],
        location: Optional[Coordinate] = None,
        location_region: Optional[str] = None,
        sport_type: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[UserPreferences]:
        """Retrieve user's historical preferences for this area (if any).
        
        This method queries the database for user preferences matching the
        provided location region and sport type. Preferences are used to
        provide defaults when user intent is vague (e.g., "afternoon ride"
        uses typical_distance_km from preferences).
        
        Args:
            user_id: User ID (optional, for anonymous users)
            location: Coordinate location (optional)
            location_region: Region name as string (optional, e.g., "Boulder, CO")
            sport_type: Sport type filter (optional)
            db: Database session
            
        Returns:
            UserPreferences object if found, None otherwise
        """
        if not is_feature_enabled("user_preferences"):
            return None
        """Retrieve user's historical preferences for this area (if any).
        
        Args:
            user_id: User ID (optional, for anonymous users)
            location: Coordinate location (optional)
            location_region: Region name as string (optional, e.g., "Boulder, CO")
            sport_type: Sport type filter (optional)
            db: Database session
            
        Returns:
            UserPreferences object if found, None otherwise
        """
        if not db:
            logger.warning("No database session provided to get_user_preferences")
            return None

        if not user_id:
            return None

        try:
            # Build query to find matching preferences
            conditions = [UserPreference.user_id == user_id]
            
            # If location_region is provided, match it
            if location_region:
                conditions.append(UserPreference.location_region == location_region)
            elif location:
                # Try to derive region from location (simplified - could use reverse geocoding)
                # For now, we'll match any preferences for this user
                pass
            
            # If sport_type is provided, prefer matching sport type
            if sport_type:
                # First try exact match
                result = await db.execute(
                    select(UserPreference)
                    .where(and_(*conditions, UserPreference.sport_type == sport_type))
                    .order_by(UserPreference.updated_at.desc())
                    .limit(1)
                )
                pref = result.scalar_one_or_none()
                if pref:
                    return self._model_to_preferences(pref)
                
                # Fall back to any sport type for this user/region
                result = await db.execute(
                    select(UserPreference)
                    .where(and_(*conditions))
                    .order_by(UserPreference.updated_at.desc())
                    .limit(1)
                )
                pref = result.scalar_one_or_none()
                if pref:
                    return self._model_to_preferences(pref)
            else:
                # No sport type filter, just get most recent
                result = await db.execute(
                    select(UserPreference)
                    .where(and_(*conditions))
                    .order_by(UserPreference.updated_at.desc())
                    .limit(1)
                )
                pref = result.scalar_one_or_none()
                if pref:
                    return self._model_to_preferences(pref)

            return None
        except Exception as e:
            logger.error(f"Error retrieving user preferences: {e}", exc_info=True)
            return None

    async def update_preferences_from_route(
        self,
        user_id: UUID,
        route: Route,
        feedback: Optional[RouteFeedback] = None,
        location_region: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Learn from a completed route and user feedback (explicit or implicit).
        
        Args:
            user_id: User ID
            route: Route object that was completed
            feedback: Optional explicit feedback from user
            location_region: Region name (optional, will try to derive if not provided)
            db: Database session
            
        Returns:
            True if preferences were updated, False otherwise
        """
        if not db:
            logger.warning("No database session provided to update_preferences_from_route")
            return False

        try:
            # Record in route history
            route_history = RouteHistory(
                user_id=user_id,
                route_id=route.id,
                sport_type=route.sport_type,
                distance_km=route.distance_meters / 1000.0 if route.distance_meters else None,
                elevation_gain_m=route.elevation_gain_meters,
                rating=feedback.rating if feedback else None,
                feedback_text=feedback.feedback_text if feedback else None,
            )
            db.add(route_history)

            # Update or create user preferences
            # Find existing preference for this user/region/sport_type
            conditions = [
                UserPreference.user_id == user_id,
                UserPreference.sport_type == route.sport_type,
            ]
            if location_region:
                conditions.append(UserPreference.location_region == location_region)

            result = await db.execute(
                select(UserPreference).where(and_(*conditions)).limit(1)
            )
            pref = result.scalar_one_or_none()

            if pref:
                # Update existing preference
                # Update typical distance (running average)
                if route.distance_meters:
                    distance_km = route.distance_meters / 1000.0
                    if pref.typical_distance_km:
                        # Simple moving average (could be more sophisticated)
                        pref.typical_distance_km = (pref.typical_distance_km + distance_km) / 2.0
                    else:
                        pref.typical_distance_km = distance_km

                # Update preferred surfaces from route's surface breakdown
                if route.surface_breakdown:
                    if not pref.preferred_surfaces:
                        pref.preferred_surfaces = {}
                    # Merge surface preferences (weighted average)
                    for surface, percentage in route.surface_breakdown.items():
                        if percentage > 0:
                            current = pref.preferred_surfaces.get(surface, 0.0)
                            pref.preferred_surfaces[surface] = (current + percentage / 100.0) / 2.0

                # If user gave positive feedback, add to favorites
                if feedback and feedback.rating and feedback.rating >= 4:
                    if not pref.favorite_trails:
                        pref.favorite_trails = []
                    # Could add route name or ID here
                    # For now, we'll track by route characteristics

                # If user gave negative feedback, consider adding to avoided areas
                if feedback and feedback.rating and feedback.rating <= 2:
                    # Could add route segments or areas to avoided_areas
                    pass
            else:
                # Create new preference
                pref = UserPreference(
                    user_id=user_id,
                    location_region=location_region,
                    sport_type=route.sport_type,
                    typical_distance_km=route.distance_meters / 1000.0 if route.distance_meters else None,
                    preferred_surfaces=route.surface_breakdown if route.surface_breakdown else {},
                    avoided_areas=[],
                    favorite_trails=[],
                )
                db.add(pref)

            await db.commit()
            logger.info(f"Updated preferences for user {user_id} from route {route.id}")
            return True
        except Exception as e:
            logger.error(f"Error updating preferences from route: {e}", exc_info=True)
            await db.rollback()
            return False

    def _model_to_preferences(self, pref: UserPreference) -> UserPreferences:
        """Convert database model to schema."""
        return UserPreferences(
            user_id=pref.user_id,
            location_region=pref.location_region,
            sport_type=pref.sport_type,
            typical_distance_km=pref.typical_distance_km,
            preferred_surfaces=pref.preferred_surfaces,
            avoided_areas=pref.avoided_areas,
            favorite_trails=pref.favorite_trails,
        )


# Singleton instance
_user_context_service: Optional[UserContextService] = None


def get_user_context_service() -> UserContextService:
    """Get or create UserContextService singleton."""
    global _user_context_service
    if _user_context_service is None:
        _user_context_service = UserContextService()
    return _user_context_service
