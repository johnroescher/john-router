"""User model."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    google_id = Column(String(255), unique=True, nullable=True)
    name = Column(String(255), nullable=True)
    preferences = Column(
        JSONB,
        default={
            "bike_type": "mtb",
            "fitness_level": "intermediate",
            "ftp": None,
            "typical_speed_mph": 12,
            "max_climb_tolerance_ft": 3000,
            "mtb_skill": "intermediate",
            "risk_tolerance": "medium",
            "surface_preferences": {"pavement": 0.2, "gravel": 0.3, "singletrack": 0.5},
            "avoidances": [],
            "units": "imperial",
        },
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

    def __repr__(self) -> str:
        return f"<User {self.email or self.id}>"
