"""Knowledge ingestion service for populating knowledge base."""
from typing import Optional, List, Dict, Any
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge_chunk import KnowledgeChunk
from app.services.external_apis.trailforks import get_trailforks_api
from app.schemas.common import Coordinate

logger = structlog.get_logger()


class KnowledgeIngestionService:
    """Service for ingesting knowledge from external sources and generating embeddings."""

    def __init__(self):
        self.embedding_model = "text-embedding-ada-002"  # OpenAI model
        self.embedding_dimension = 1536

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI API.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if generation fails
        """
        try:
            from openai import AsyncOpenAI
            from app.core.config import settings
            
            api_key = getattr(settings, 'openai_api_key', None)
            if not api_key:
                logger.warning("OpenAI API key not configured, embeddings disabled")
                return None
            
            client = AsyncOpenAI(api_key=api_key)
            response = await client.embeddings.create(
                model=self.embedding_model,
                input=text[:8000],  # Limit text length
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            return None

    async def ingest_trailforks_data(
        self,
        location: Optional[Coordinate] = None,
        location_name: Optional[str] = None,
        sport_type: Optional[str] = None,
        limit: int = 100,
        db: Optional[AsyncSession] = None,
    ) -> int:
        """Ingest trail data from Trailforks API.
        
        Args:
            location: Coordinate location
            location_name: Location name
            sport_type: Sport type filter
            limit: Maximum number of trails to ingest
            db: Database session
            
        Returns:
            Number of chunks ingested
        """
        if not db:
            logger.warning("No database session provided to ingest_trailforks_data")
            return 0

        try:
            trailforks_api = await get_trailforks_api()
            trails = await trailforks_api.search_trails(
                location=location,
                location_name=location_name,
                sport_type=sport_type,
                limit=limit,
            )

            ingested_count = 0
            for trail in trails:
                # Check if already exists
                trail_id = trail.get('id')
                if trail_id:
                    from sqlalchemy import select
                    result = await db.execute(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.metadata_json['trail_id'].astext == str(trail_id)
                        ).limit(1)
                    )
                    if result.scalar_one_or_none():
                        continue  # Already exists

                # Create content
                content = f"Trail: {trail.get('name', 'Unknown')}. "
                if trail.get('description'):
                    content += trail['description'] + " "
                if trail.get('difficulty'):
                    content += f"Difficulty: {trail['difficulty']}. "
                if trail.get('distance'):
                    content += f"Distance: {trail['distance']} km. "
                if trail.get('elevation_gain'):
                    content += f"Elevation gain: {trail['elevation_gain']} m."

                # Generate embedding
                embedding = await self.generate_embedding(content)
                if not embedding:
                    logger.warning(f"Skipping trail {trail_id} - embedding generation failed")
                    continue

                # Create knowledge chunk
                chunk = KnowledgeChunk(
                    content=content,
                    embedding=embedding,
                    metadata_json={
                        "trail_id": trail_id,
                        "name": trail.get('name'),
                        "difficulty": trail.get('difficulty'),
                        "distance_km": trail.get('distance'),
                        "elevation_gain_m": trail.get('elevation_gain'),
                    },
                    source="trailforks",
                    location_region=location_name,
                    sport_type=sport_type or trail.get('activitytype'),
                )
                db.add(chunk)
                ingested_count += 1

            await db.commit()
            logger.info(f"Ingested {ingested_count} knowledge chunks from Trailforks")
            return ingested_count
        except Exception as e:
            logger.error(f"Failed to ingest Trailforks data: {e}", exc_info=True)
            await db.rollback()
            return 0

    async def ingest_location_knowledge(
        self,
        location_region: str,
        sport_type: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> int:
        """Ingest knowledge from location_knowledge table into knowledge_chunks.
        
        Args:
            location_region: Location region
            sport_type: Sport type filter
            db: Database session
            
        Returns:
            Number of chunks ingested
        """
        if not db:
            return 0

        try:
            from app.models.location_knowledge import LocationKnowledge
            from sqlalchemy import select, and_

            conditions = [LocationKnowledge.location_region == location_region]
            if sport_type:
                conditions.append(LocationKnowledge.sport_type == sport_type)

            result = await db.execute(
                select(LocationKnowledge).where(and_(*conditions))
            )
            entries = result.scalars().all()

            ingested_count = 0
            for entry in entries:
                # Check if already exists
                result = await db.execute(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.source == "location_knowledge",
                        KnowledgeChunk.metadata_json['location_knowledge_id'].astext == str(entry.id)
                    ).limit(1)
                )
                if result.scalar_one_or_none():
                    continue

                # Create content
                content = ""
                if entry.name:
                    content += f"{entry.name}. "
                if entry.description:
                    content += entry.description

                if not content:
                    continue

                # Generate embedding
                embedding = await self.generate_embedding(content)
                if not embedding:
                    continue

                # Create knowledge chunk
                chunk = KnowledgeChunk(
                    content=content,
                    embedding=embedding,
                    metadata_json={
                        "location_knowledge_id": str(entry.id),
                        "knowledge_type": entry.knowledge_type,
                        "name": entry.name,
                        "metadata": entry.metadata_json,
                    },
                    source="location_knowledge",
                    location_region=entry.location_region,
                    sport_type=entry.sport_type,
                )
                db.add(chunk)
                ingested_count += 1

            await db.commit()
            logger.info(f"Ingested {ingested_count} knowledge chunks from location_knowledge")
            return ingested_count
        except Exception as e:
            logger.error(f"Failed to ingest location knowledge: {e}", exc_info=True)
            await db.rollback()
            return 0


# Singleton instance
_knowledge_ingestion_service: Optional[KnowledgeIngestionService] = None


async def get_knowledge_ingestion_service() -> KnowledgeIngestionService:
    """Get or create KnowledgeIngestionService singleton."""
    global _knowledge_ingestion_service
    if _knowledge_ingestion_service is None:
        _knowledge_ingestion_service = KnowledgeIngestionService()
    return _knowledge_ingestion_service
