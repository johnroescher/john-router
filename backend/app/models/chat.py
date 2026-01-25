"""Chat conversation model."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class ChatConversation(Base):
    """Chat conversation model - stores conversation history and state."""

    __tablename__ = "chat_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    route_id = Column(UUID(as_uuid=True), ForeignKey("routes.id", ondelete="SET NULL"), nullable=True)

    messages = Column(JSONB, default=[], nullable=False)
    current_constraints = Column(JSONB, default={}, nullable=False)

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
        return f"<ChatConversation {self.id}>"
