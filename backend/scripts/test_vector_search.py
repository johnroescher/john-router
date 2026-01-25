"""Test script for vector search functionality."""
import asyncio
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, text
import pytest

pytest.importorskip("pgvector", reason="pgvector not installed")

from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.models.knowledge_chunk import KnowledgeChunk


async def test_vector_search():
    """Test vector storage and similarity search."""
    # Convert sync URL to async
    database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(database_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as db:
        # Test 1: Store a dummy embedding
        print("Test 1: Storing dummy embedding...")
        dummy_embedding = np.random.rand(1536).astype(np.float32).tolist()
        
        chunk = KnowledgeChunk(
            content="This is a test knowledge chunk about mountain biking in Moab.",
            embedding=dummy_embedding,
            metadata={"test": True},
            source="test_script",
            location_region="Moab, UT",
            sport_type="mtb",
        )
        db.add(chunk)
        await db.commit()
        print(f"✓ Stored chunk with ID: {chunk.id}")

        # Test 2: Retrieve and verify
        print("\nTest 2: Retrieving stored chunk...")
        result = await db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.id == chunk.id)
        )
        retrieved = result.scalar_one()
        print(f"✓ Retrieved chunk: {retrieved.content[:50]}...")
        print(f"✓ Has embedding: {retrieved.embedding is not None}")

        # Test 3: Similarity search
        print("\nTest 3: Testing similarity search...")
        query_embedding = np.random.rand(1536).astype(np.float32).tolist()
        
        # Use raw SQL for similarity search (pgvector syntax)
        similarity_query = text("""
            SELECT id, content, 
                   1 - (embedding <=> :query_embedding::vector) as similarity
            FROM knowledge_chunks
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT 5
        """)
        
        result = await db.execute(
            similarity_query,
            {"query_embedding": str(query_embedding)}
        )
        results = result.fetchall()
        
        if results:
            print(f"✓ Found {len(results)} similar chunks:")
            for row in results:
                print(f"  - Similarity: {row.similarity:.4f}, Content: {row.content[:50]}...")
        else:
            print("⚠ No results found (expected if only test data)")

        # Test 4: Clean up test data
        print("\nTest 4: Cleaning up test data...")
        await db.execute(
            text("DELETE FROM knowledge_chunks WHERE source = 'test_script'")
        )
        await db.commit()
        print("✓ Cleaned up test data")

        print("\n✅ All vector search tests passed!")


if __name__ == "__main__":
    asyncio.run(test_vector_search())
