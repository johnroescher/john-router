"""Knowledge chunk model for RAG."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - fallback for environments without pgvector
    Vector = None

from app.core.database import Base


class KnowledgeChunk(Base):
    """Knowledge chunk model - stores text chunks with vector embeddings for RAG."""

    __tablename__ = "knowledge_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True) if Vector else Column(JSONB, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    source = Column(String(100), nullable=True)  # e.g., 'Trailforks', 'UserUpload'
    location_region = Column(String(100), nullable=True)
    sport_type = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)

    def __repr__(self) -> str:
        return f"<KnowledgeChunk {self.id} region={self.location_region} source={self.source}>"
