"""Ride Brief Loop persistence models."""
from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class PlanningSession(Base):
    """Persistent session state for the Ride Brief Loop."""

    __tablename__ = "planning_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    intent_object = Column(JSONB, default={}, nullable=False)
    ride_brief = Column(JSONB, default={}, nullable=False)
    discovery_plan = Column(JSONB, default={}, nullable=False)
    ingredient_set = Column(JSONB, default={}, nullable=False)
    critique_report = Column(JSONB, default={}, nullable=False)
    conversation_context = Column(JSONB, default={}, nullable=False)

    iteration = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="in_progress", nullable=False)
    selected_candidate_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    candidates = relationship("PlanningCandidate", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PlanningSession {self.id} status={self.status}>"


class PlanningCandidate(Base):
    """Candidate route generated in a planning session."""

    __tablename__ = "planning_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("planning_sessions.id", ondelete="CASCADE"), nullable=False)

    label = Column(String(10), nullable=False)
    routing_profile = Column(String(50), nullable=False)
    generation_strategy = Column(String(100), nullable=False)

    geometry = Column(Geometry("LINESTRING", srid=4326), nullable=True)
    waypoints = Column(JSONB, default=[], nullable=False)
    computed = Column(JSONB, default={}, nullable=False)
    validation = Column(JSONB, default={}, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)

    session = relationship("PlanningSession", back_populates="candidates")

    def __repr__(self) -> str:
        return f"<PlanningCandidate {self.id} label={self.label}>"
