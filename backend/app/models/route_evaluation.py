"""Route evaluation logging models."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class RouteEvaluationLog(Base):
    """Log of route evaluations for analysis and learning."""

    __tablename__ = "route_evaluation_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    route_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to route or candidate
    intent = Column(JSONB, nullable=True)  # Snapshot of intent
    initial_scores = Column(JSONB, nullable=True)  # Scores before improvement
    final_scores = Column(JSONB, nullable=True)  # Scores after improvement
    issues_found = Column(JSONB, nullable=True)  # List of issue types found
    improvements_made = Column(JSONB, nullable=True)  # List of improvements applied
    timestamp = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)

    def __repr__(self) -> str:
        return f"<RouteEvaluationLog {self.id} route={self.route_id}>"
