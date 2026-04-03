"""Trail metadata and elevation cache models."""
from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import Column, String, Float, DateTime, text, BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class TrailMetadataCache(Base):
    """Cached trail metadata from OSM and other sources."""

    __tablename__ = "trail_metadata_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    osm_way_id = Column(BigInteger, unique=True, nullable=True)
    external_id = Column(String(255), nullable=True)
    external_source = Column(String(100), nullable=True)
    geometry = Column(Geometry("LINESTRING", srid=4326), nullable=True)

    # Core attributes
    name = Column(String(255), nullable=True)
    surface = Column(String(100), nullable=True)
    smoothness = Column(String(50), nullable=True)
    tracktype = Column(String(50), nullable=True)
    highway = Column(String(100), nullable=True)

    # MTB-specific
    mtb_scale = Column(Float, nullable=True)
    mtb_scale_uphill = Column(Float, nullable=True)
    mtb_description = Column(Text, nullable=True)
    sac_scale = Column(String(50), nullable=True)

    # Access
    access = Column(String(50), nullable=True)
    bicycle = Column(String(50), nullable=True)
    foot = Column(String(50), nullable=True)

    # Physical
    width = Column(Float, nullable=True)
    incline = Column(String(50), nullable=True)
    trail_visibility = Column(String(50), nullable=True)

    # Computed
    avg_grade = Column(Float, nullable=True)
    max_grade = Column(Float, nullable=True)

    # Management
    operator = Column(String(255), nullable=True)
    land_manager = Column(String(255), nullable=True)

    # Raw tags
    all_tags = Column(JSONB, default={}, nullable=False)

    # Freshness
    last_osm_update = Column(DateTime(timezone=True), nullable=True)
    last_verified = Column(DateTime(timezone=True), nullable=True)
    confidence_score = Column(Float, default=0, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TrailMetadataCache {self.name or self.osm_way_id}>"


class ElevationCache(Base):
    """Cached elevation data to reduce API calls."""

    __tablename__ = "elevation_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    point = Column(Geometry("POINT", srid=4326), nullable=False)
    elevation_meters = Column(Float, nullable=False)
    source = Column(String(100), default="unknown", nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ElevationCache {self.elevation_meters}m>"
