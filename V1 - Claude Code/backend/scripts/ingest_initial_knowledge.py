"""Initial knowledge ingestion script for test region."""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.services.knowledge_ingestion import get_knowledge_ingestion_service
from app.schemas.common import Coordinate


async def ingest_initial_knowledge():
    """Ingest initial knowledge for test regions."""
    # Convert sync URL to async
    database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(database_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as db:
        ingestion_service = await get_knowledge_ingestion_service()

        # Ingest for Moab, UT - MTB
        print("Ingesting knowledge for Moab, UT (MTB)...")
        moab_location = Coordinate(lat=38.5733, lng=-109.5498)
        count1 = await ingestion_service.ingest_trailforks_data(
            location=moab_location,
            location_name="Moab, UT",
            sport_type="mtb",
            limit=50,
            db=db,
        )
        print(f"✓ Ingested {count1} chunks for Moab, UT")

        # Ingest location knowledge for Moab
        count2 = await ingestion_service.ingest_location_knowledge(
            location_region="Moab, UT",
            sport_type="mtb",
            db=db,
        )
        print(f"✓ Ingested {count2} chunks from location_knowledge for Moab, UT")

        # Ingest for Boulder, CO - Mixed
        print("\nIngesting knowledge for Boulder, CO...")
        boulder_location = Coordinate(lat=40.0150, lng=-105.2705)
        count3 = await ingestion_service.ingest_trailforks_data(
            location=boulder_location,
            location_name="Boulder, CO",
            sport_type="mtb",
            limit=30,
            db=db,
        )
        print(f"✓ Ingested {count3} chunks for Boulder, CO (MTB)")

        count4 = await ingestion_service.ingest_location_knowledge(
            location_region="Boulder, CO",
            db=db,
        )
        print(f"✓ Ingested {count4} chunks from location_knowledge for Boulder, CO")

        total = count1 + count2 + count3 + count4
        print(f"\n✅ Total ingested: {total} knowledge chunks")


if __name__ == "__main__":
    asyncio.run(ingest_initial_knowledge())
