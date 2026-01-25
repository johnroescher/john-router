"""Knowledge retrieval service for RAG."""
from typing import Optional, List
from uuid import UUID

import structlog
import numpy as np
from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_chunk import KnowledgeChunk
from app.schemas.knowledge import KnowledgeChunk as KnowledgeChunkSchema
from app.schemas.common import Coordinate
from app.services.cache_service import get_cache_service
from app.services.external_apis.trailforks import get_trailforks_api

logger = structlog.get_logger()


class KnowledgeRetrievalService:
    """Service for retrieving relevant knowledge chunks using vector similarity and external APIs."""

    def __init__(self):
        pass

    async def retrieve_knowledge(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        location: Optional[Coordinate] = None,
        location_region: Optional[str] = None,
        sport_type: Optional[str] = None,
        limit: int = 5,
        db: Optional[AsyncSession] = None,
    ) -> List[KnowledgeChunkSchema]:
        """Retrieve relevant knowledge chunks using vector similarity search.
        
        Args:
            query: Text query to search for
            query_embedding: Pre-computed embedding vector (optional, will generate if not provided)
            location: Coordinate location filter
            location_region: Region name filter
            sport_type: Sport type filter
            limit: Maximum number of results
            db: Database session
            
        Returns:
            List of KnowledgeChunkSchema objects ranked by relevance
        """
        if not db:
            logger.warning("No database session provided to retrieve_knowledge")
            return []

        # Check cache
        cache_service = await get_cache_service()
        cache_key = cache_service._make_key(
            "knowledge:retrieve",
            query=query[:100],  # Use first 100 chars for key
            location_region=location_region,
            sport_type=sport_type,
            limit=limit,
        )
        cached = await cache_service.get(cache_key)
        if cached:
            logger.debug("Cache hit for knowledge retrieval")
            return [KnowledgeChunkSchema(**item) for item in cached]

        chunks = []

        # Generate embedding if not provided (for vector search)
        if not query_embedding:
            query_embedding = await self._generate_embedding(query)

        # Try vector similarity search if we have embeddings
        if query_embedding:
            try:
                vector_chunks = await self._vector_search(
                    query_embedding,
                    location_region=location_region,
                    sport_type=sport_type,
                    limit=limit,
                    db=db,
                )
                chunks.extend(vector_chunks)
            except Exception as e:
                logger.warning(f"Vector search failed: {e}", exc_info=True)

        # If we don't have enough chunks, try external APIs
        if len(chunks) < limit:
            try:
                external_chunks = await self._retrieve_from_external_apis(
                    query=query,
                    location=location,
                    location_name=location_region,
                    sport_type=sport_type,
                    limit=limit - len(chunks),
                )
                chunks.extend(external_chunks)
            except Exception as e:
                logger.warning(f"External API retrieval failed: {e}", exc_info=True)

        # Rank and deduplicate
        ranked_chunks = self._rank_chunks(chunks, query)
        final_chunks = ranked_chunks[:limit]
        
        # Cache the results (1 hour TTL for knowledge)
        await cache_service.set(cache_key, [chunk.model_dump() for chunk in final_chunks], ttl_seconds=3600)
        
        return final_chunks

    async def _vector_search(
        self,
        query_embedding: List[float],
        location_region: Optional[str] = None,
        sport_type: Optional[str] = None,
        limit: int = 5,
        db: Optional[AsyncSession] = None,
    ) -> List[KnowledgeChunkSchema]:
        """Perform vector similarity search."""
        if not db:
            return []

        try:
            # Conditions will be built in SQL query

            # Build similarity query using pgvector
            embedding_str = str(query_embedding)
            
            # Build WHERE clause for filters
            where_clauses = ["embedding IS NOT NULL"]
            params = {
                "query_embedding": embedding_str,
                "limit": limit,
            }
            
            if location_region:
                where_clauses.append("location_region = :location_region")
                params["location_region"] = location_region
            if sport_type:
                where_clauses.append("sport_type = :sport_type")
                params["sport_type"] = sport_type
            
            where_clause = " AND ".join(where_clauses)
            
            # Use cosine distance (1 - cosine similarity)
            # Lower distance = higher similarity
            similarity_query = text(f"""
                SELECT id, content, metadata, source, location_region, sport_type,
                       1 - (embedding <=> :query_embedding::vector) as similarity
                FROM knowledge_chunks
                WHERE {where_clause}
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :limit
            """)

            result = await db.execute(similarity_query, params)
            rows = result.fetchall()

            chunks = []
            for row in rows:
                chunk = KnowledgeChunkSchema(
                    id=row.id,
                    content=row.content,
                    metadata=row.metadata,
                    source=row.source,
                    location_region=row.location_region,
                    sport_type=row.sport_type,
                    relevance_score=row.similarity,
                )
                chunks.append(chunk)

            logger.info(f"Vector search returned {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Vector search error: {e}", exc_info=True)
            return []

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a query using OpenAI embeddings."""
        try:
            from openai import AsyncOpenAI
            from app.core.config import settings

            api_key = getattr(settings, "openai_api_key", None)
            if not api_key:
                logger.warning("OpenAI API key not configured, skipping vector search")
                return None

            client = AsyncOpenAI(api_key=api_key)
            response = await client.embeddings.create(
                model="text-embedding-ada-002",
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}", exc_info=True)
            return None

    async def _retrieve_from_external_apis(
        self,
        query: str,
        location: Optional[Coordinate] = None,
        location_name: Optional[str] = None,
        sport_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[KnowledgeChunkSchema]:
        """Retrieve knowledge from external APIs (Trailforks, etc.)."""
        chunks = []

        # Try Trailforks API
        try:
            trailforks_api = await get_trailforks_api()
            trails = await trailforks_api.search_trails(
                location=location,
                location_name=location_name,
                sport_type=sport_type,
                limit=limit,
            )

            for trail in trails:
                # Convert trail to knowledge chunk
                content = f"Trail: {trail.get('name', 'Unknown')}. "
                if trail.get('description'):
                    content += trail['description']
                if trail.get('difficulty'):
                    content += f" Difficulty: {trail['difficulty']}."
                if trail.get('distance'):
                    content += f" Distance: {trail['distance']} km."

                chunk = KnowledgeChunkSchema(
                    content=content,
                    metadata={
                        "trail_id": trail.get('id'),
                        "name": trail.get('name'),
                        "difficulty": trail.get('difficulty'),
                        "distance_km": trail.get('distance'),
                        "elevation_gain_m": trail.get('elevation_gain'),
                    },
                    source="trailforks",
                    location_region=location_name,
                    sport_type=sport_type,
                    relevance_score=0.8,  # Default score for external API results
                )
                chunks.append(chunk)
        except Exception as e:
            logger.warning(f"Trailforks API retrieval failed: {e}")

        return chunks

    def _rank_chunks(
        self,
        chunks: List[KnowledgeChunkSchema],
        query: str,
    ) -> List[KnowledgeChunkSchema]:
        """Rank chunks by relevance (simple keyword matching for now)."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        def score_chunk(chunk: KnowledgeChunkSchema) -> float:
            score = chunk.relevance_score or 0.5
            
            # Boost score if query words appear in content
            content_lower = chunk.content.lower()
            matches = sum(1 for word in query_words if word in content_lower)
            if matches > 0:
                score += 0.1 * matches / len(query_words)
            
            # Boost if source is high-quality
            if chunk.source == "trailforks":
                score += 0.1
            
            return min(score, 1.0)  # Cap at 1.0

        # Sort by score descending
        ranked = sorted(chunks, key=score_chunk, reverse=True)
        return ranked


# Singleton instance
_knowledge_retrieval_service: Optional[KnowledgeRetrievalService] = None


async def get_knowledge_retrieval_service() -> KnowledgeRetrievalService:
    """Get or create KnowledgeRetrievalService singleton."""
    global _knowledge_retrieval_service
    if _knowledge_retrieval_service is None:
        _knowledge_retrieval_service = KnowledgeRetrievalService()
    return _knowledge_retrieval_service
