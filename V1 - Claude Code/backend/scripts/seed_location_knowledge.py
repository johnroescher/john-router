"""Seed location knowledge for pilot locations."""
import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.models.location_knowledge import LocationKnowledge


async def seed_location_knowledge():
    """Seed location knowledge for 2-3 pilot locations."""
    # Convert sync URL to async
    database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(database_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as db:
        # Check if data already exists
        result = await db.execute(select(LocationKnowledge).limit(1))
        existing = result.scalar_one_or_none()
        if existing:
            print("Location knowledge already seeded. Skipping.")
            return

        # Seed Moab, UT - MTB
        moab_entries = [
            {
                "location_region": "Moab, UT",
                "sport_type": "mtb",
                "knowledge_type": "popular_route",
                "name": "Slickrock Trail",
                "description": "World-famous technical trail with grippy sandstone. Classic 10.5 mile loop with challenging terrain.",
                "metadata": {
                    "distance_km": 16.9,
                    "elevation_gain_m": 300,
                    "difficulty": "black",
                    "technical": "high",
                },
                "confidence": 0.95,
                "source": "manual_curation",
            },
            {
                "location_region": "Moab, UT",
                "sport_type": "mtb",
                "knowledge_type": "popular_route",
                "name": "Porcupine Rim",
                "description": "Epic 14-mile singletrack descent with stunning views. Often combined with other trails for longer rides.",
                "metadata": {
                    "distance_km": 22.5,
                    "elevation_gain_m": 200,
                    "difficulty": "black",
                    "technical": "high",
                },
                "confidence": 0.9,
                "source": "manual_curation",
            },
            {
                "location_region": "Moab, UT",
                "sport_type": "mtb",
                "knowledge_type": "local_tip",
                "name": "Mud Season",
                "description": "Avoid trails during and immediately after rain - the clay soil becomes extremely sticky and damages trails.",
                "confidence": 0.85,
                "source": "manual_curation",
            },
        ]

        # Seed Boulder, CO - Mixed
        boulder_entries = [
            {
                "location_region": "Boulder, CO",
                "sport_type": "mtb",
                "knowledge_type": "trail_system",
                "name": "Betasso Preserve",
                "description": "Popular trail system with flowy singletrack. Great for intermediate riders. Requires reservation on weekends.",
                "metadata": {
                    "difficulty": "blue",
                    "technical": "medium",
                },
                "confidence": 0.9,
                "source": "manual_curation",
            },
            {
                "location_region": "Boulder, CO",
                "sport_type": "gravel",
                "knowledge_type": "popular_route",
                "name": "Boulder to Nederland Gravel",
                "description": "Classic gravel route connecting Boulder to Nederland via Peak to Peak Highway and side roads.",
                "metadata": {
                    "distance_km": 35.0,
                    "elevation_gain_m": 800,
                    "difficulty": "intermediate",
                },
                "confidence": 0.85,
                "source": "manual_curation",
            },
            {
                "location_region": "Boulder, CO",
                "sport_type": "road",
                "knowledge_type": "notable_feature",
                "name": "Flagstaff Road Climb",
                "description": "Steep 5-mile climb with switchbacks. Popular training climb for local cyclists.",
                "metadata": {
                    "distance_km": 8.0,
                    "elevation_gain_m": 600,
                    "avg_grade": 0.075,
                },
                "confidence": 0.9,
                "source": "manual_curation",
            },
        ]

        # Seed Marin County, CA - Road/Gravel
        marin_entries = [
            {
                "location_region": "Marin County, CA",
                "sport_type": "road",
                "knowledge_type": "popular_route",
                "name": "Paradise Loop",
                "description": "Classic 35-mile road loop through Tiburon, Corte Madera, and back. Scenic with moderate hills.",
                "metadata": {
                    "distance_km": 56.3,
                    "elevation_gain_m": 400,
                    "difficulty": "intermediate",
                },
                "confidence": 0.9,
                "source": "manual_curation",
            },
            {
                "location_region": "Marin County, CA",
                "sport_type": "gravel",
                "knowledge_type": "popular_route",
                "name": "Mount Tamalpais Gravel",
                "description": "Epic gravel route up Mount Tam with stunning bay views. Mix of fire roads and singletrack.",
                "metadata": {
                    "distance_km": 40.0,
                    "elevation_gain_m": 1200,
                    "difficulty": "advanced",
                },
                "confidence": 0.85,
                "source": "manual_curation",
            },
        ]

        all_entries = moab_entries + boulder_entries + marin_entries

        for entry_data in all_entries:
            entry = LocationKnowledge(**entry_data)
            db.add(entry)

        await db.commit()
        print(f"Seeded {len(all_entries)} location knowledge entries for 3 pilot locations.")


if __name__ == "__main__":
    asyncio.run(seed_location_knowledge())
