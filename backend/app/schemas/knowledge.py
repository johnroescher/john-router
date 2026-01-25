"""Knowledge schemas for location knowledge and named routes."""
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.common import Coordinate


class AreaInsights(BaseModel):
    """Area insights schema - local knowledge about cycling in an area."""
    location_region: Optional[str] = None
    sport_type: Optional[str] = None
    popular_routes: List[str] = Field(default_factory=list)  # List of route/trail names
    trail_systems: List[str] = Field(default_factory=list)  # List of trail system names
    notable_features: List[str] = Field(default_factory=list)  # Notable climbs, landmarks, etc.
    seasonal_considerations: List[str] = Field(default_factory=list)  # Mud season, closures, etc.
    local_tips: List[str] = Field(default_factory=list)  # Insider tips
    difficulty_info: Optional[Dict[str, Any]] = None  # General difficulty info for area

    class Config:
        from_attributes = True


class NamedRoute(BaseModel):
    """Named route schema - famous or well-known routes."""
    id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    location_region: Optional[str] = None
    sport_type: Optional[str] = None
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    difficulty: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None  # GeoJSON geometry
    metadata: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class KnowledgeChunk(BaseModel):
    """Knowledge chunk schema for RAG."""
    id: Optional[UUID] = None
    content: str
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    location_region: Optional[str] = None
    sport_type: Optional[str] = None
    relevance_score: Optional[float] = None  # For ranked results

    class Config:
        from_attributes = True
