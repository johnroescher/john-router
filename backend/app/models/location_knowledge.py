"""Location knowledge models for storing local cycling knowledge."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Float, Text, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class LocationKnowledge(Base):
    """Location knowledge model - stores local cycling knowledge for regions."""

    __tablename__ = "location_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    location_region = Column(String(100), nullable=True)  # e.g., "Moab, UT"
    sport_type = Column(String(20), nullable=True)  # e.g., "MTB", "road"
    knowledge_type = Column(String(50), nullable=True)  # e.g., 'trail_system', 'popular_route', 'local_tip', 'event'
    name = Column(String(255), nullable=True)  # name of trail/route or category
    description = Column(Text, nullable=True)  # textual description or details
    geometry = Column(JSONB, nullable=True)  # GeoJSON geometry if applicable
    metadata_json = Column("metadata", JSONB, nullable=True)  # any additional data (difficulty, length, etc.)
    confidence = Column(Float, nullable=True)  # confidence/relevance score
    source = Column(String(100), nullable=True)  # source of this info (e.g., 'Trailforks', 'UserUpload')
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<LocationKnowledge {self.id} region={self.location_region} type={self.knowledge_type}>"
