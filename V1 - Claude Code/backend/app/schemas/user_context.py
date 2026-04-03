"""User context schemas for preferences and route history."""
from typing import Optional, Dict, List, Any
from uuid import UUID
from pydantic import BaseModel, Field


class UserPreferences(BaseModel):
    """User preferences schema."""
    user_id: Optional[UUID] = None
    location_region: Optional[str] = None
    sport_type: Optional[str] = None
    typical_distance_km: Optional[float] = None
    preferred_surfaces: Optional[Dict[str, float]] = None  # e.g., {"paved": 0.7, "dirt": 0.3}
    avoided_areas: Optional[List[str]] = None  # List of trail IDs or region names
    favorite_trails: Optional[List[str]] = None  # List of trail IDs or names

    class Config:
        from_attributes = True


class RouteFeedback(BaseModel):
    """Route feedback schema."""
    rating: Optional[int] = Field(None, ge=1, le=5)  # 1-5 star rating
    feedback_text: Optional[str] = None


class UserPreferencesResponse(BaseModel):
    """Response schema for user preferences."""
    preferences: Optional[UserPreferences] = None
    has_preferences: bool = False
