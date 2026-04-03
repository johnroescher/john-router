"""User context models for preferences and route history."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String, Float, Integer, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class UserPreference(Base):
    """User preferences model - stores user-specific cycling preferences by region."""

    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    location_region = Column(String(100), nullable=True)  # e.g., "Boulder, CO"
    sport_type = Column(String(20), nullable=True)  # e.g., "road", "gravel", "mtb"
    typical_distance_km = Column(Float, nullable=True)
    preferred_surfaces = Column(JSONB, nullable=True)  # e.g., {"paved": 0.7, "dirt": 0.3}
    avoided_areas = Column(JSONB, nullable=True)  # e.g., list of blacklisted trail IDs or regions
    favorite_trails = Column(JSONB, nullable=True)  # e.g., list of trail IDs or names the user loved
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<UserPreference {self.id} user={self.user_id} region={self.location_region}>"


class RouteHistory(Base):
    """Route history model - logs completed routes for learning user preferences."""

    __tablename__ = "route_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    route_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to routes table
    sport_type = Column(String(20), nullable=True)
    distance_km = Column(Float, nullable=True)
    elevation_gain_m = Column(Float, nullable=True)
    rating = Column(Integer, nullable=True)  # User-given rating 1-5
    feedback_text = Column(Text, nullable=True)  # Optional textual feedback
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)

    def __repr__(self) -> str:
        return f"<RouteHistory {self.id} user={self.user_id} route={self.route_id}>"
