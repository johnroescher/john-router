"""Route and related models."""
from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    text,
    ARRAY,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, BIGINT
from sqlalchemy.orm import relationship

from app.core.database import Base


class Route(Base):
    """Route model - represents a complete cycling route."""

    __tablename__ = "routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sport_type = Column(String(50), nullable=False, default="mtb")
    geometry = Column(Geometry("LINESTRING", srid=4326), nullable=True)

    # Computed stats
    distance_meters = Column(Float, nullable=True)
    elevation_gain_meters = Column(Float, nullable=True)
    elevation_loss_meters = Column(Float, nullable=True)
    estimated_time_seconds = Column(Integer, nullable=True)
    max_elevation_meters = Column(Float, nullable=True)
    min_elevation_meters = Column(Float, nullable=True)

    # Surface breakdown (percentages)
    surface_breakdown = Column(
        JSONB,
        default={"pavement": 0, "gravel": 0, "dirt": 0, "singletrack": 0, "unknown": 100},
        nullable=False,
    )

    # Difficulty ratings (0-5 scale)
    physical_difficulty = Column(Float, nullable=True)
    technical_difficulty = Column(Float, nullable=True)
    risk_rating = Column(Float, nullable=True)
    overall_difficulty = Column(Float, nullable=True)

    # MTB-specific breakdown
    mtb_difficulty_breakdown = Column(
        JSONB,
        default={"green": 0, "blue": 0, "black": 0, "double_black": 0, "unknown": 100},
        nullable=False,
    )

    # Metadata
    tags = Column(ARRAY(String), default=[], nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    confidence_score = Column(Float, default=0, nullable=False)

    # Validation
    validation_status = Column(String(50), default="pending", nullable=False)
    validation_results = Column(
        JSONB,
        default={"errors": [], "warnings": [], "info": []},
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    waypoints = relationship("RouteWaypoint", back_populates="route", cascade="all, delete-orphan")
    segments = relationship("RouteSegment", back_populates="route", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Route {self.name} ({self.sport_type})>"


class RouteWaypoint(Base):
    """Waypoint within a route."""

    __tablename__ = "route_waypoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    route_id = Column(UUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    idx = Column(Integer, nullable=False)
    waypoint_type = Column(String(50), nullable=False, default="via")
    point = Column(Geometry("POINT", srid=4326), nullable=False)
    name = Column(String(255), nullable=True)
    lock_strength = Column(String(20), default="soft", nullable=False)
    waypoint_metadata = Column("metadata", JSONB, default={}, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    # Relationships
    route = relationship("Route", back_populates="waypoints")

    def __repr__(self) -> str:
        return f"<RouteWaypoint {self.waypoint_type} #{self.idx}>"


class RouteSegment(Base):
    """Individual segment of a route with detailed metadata."""

    __tablename__ = "route_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    route_id = Column(UUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    idx = Column(Integer, nullable=False)
    geometry = Column(Geometry("LINESTRING", srid=4326), nullable=False)
    source = Column(String(50), default="router", nullable=False)

    # Segment stats
    distance_meters = Column(Float, nullable=True)
    elevation_gain_meters = Column(Float, nullable=True)
    elevation_loss_meters = Column(Float, nullable=True)
    avg_grade = Column(Float, nullable=True)
    max_grade = Column(Float, nullable=True)
    min_grade = Column(Float, nullable=True)

    # Surface and type
    surface = Column(String(100), nullable=True)
    highway_type = Column(String(100), nullable=True)
    way_name = Column(String(255), nullable=True)

    # MTB ratings
    mtb_scale = Column(Float, nullable=True)
    mtb_scale_uphill = Column(Float, nullable=True)
    sac_scale = Column(String(50), nullable=True)
    smoothness = Column(String(50), nullable=True)
    tracktype = Column(String(50), nullable=True)

    # Access and legal
    bicycle_access = Column(String(50), default="unknown", nullable=False)
    foot_access = Column(String(50), nullable=True)

    # Hazards
    hazards = Column(JSONB, default=[], nullable=False)

    # Confidence
    confidence_score = Column(Float, default=0, nullable=False)
    data_completeness = Column(Float, default=0, nullable=False)

    # Raw OSM data
    osm_way_ids = Column(ARRAY(BIGINT), default=[], nullable=False)
    osm_tags = Column(JSONB, default={}, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    # Relationships
    route = relationship("Route", back_populates="segments")

    def __repr__(self) -> str:
        return f"<RouteSegment #{self.idx} ({self.distance_meters}m)>"
