"""Celery tasks for knowledge ingestion."""
import asyncio
from typing import Optional, Dict, Any

from .celery_app import celery_app
from app.services.knowledge_ingestion import get_knowledge_ingestion_service
from app.core.database import AsyncSessionLocal
from app.schemas.common import Coordinate


def run_async(coro):
    """Run async function in Celery task."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # If loop is already running, create a new one
        import nest_asyncio
        nest_asyncio.apply()
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, name="knowledge.ingest_trailforks")
def ingest_trailforks_task(
    self,
    location_name: str,
    sport_type: Optional[str] = None,
    limit: int = 100,
    location_lat: Optional[float] = None,
    location_lng: Optional[float] = None,
):
    """Background task for ingesting Trailforks data."""
    async def _ingest():
        async with AsyncSessionLocal() as db:
            ingestion_service = await get_knowledge_ingestion_service()
            
            location = None
            if location_lat and location_lng:
                location = Coordinate(lat=location_lat, lng=location_lng)
            
            count = await ingestion_service.ingest_trailforks_data(
                location=location,
                location_name=location_name,
                sport_type=sport_type,
                limit=limit,
                db=db,
            )
            return {"ingested_count": count, "location": location_name}

    return run_async(_ingest())


@celery_app.task(bind=True, name="knowledge.ingest_location_knowledge")
def ingest_location_knowledge_task(
    self,
    location_region: str,
    sport_type: Optional[str] = None,
):
    """Background task for ingesting location knowledge."""
    async def _ingest():
        async with AsyncSessionLocal() as db:
            ingestion_service = await get_knowledge_ingestion_service()
            
            count = await ingestion_service.ingest_location_knowledge(
                location_region=location_region,
                sport_type=sport_type,
                db=db,
            )
            return {"ingested_count": count, "location_region": location_region}

    return run_async(_ingest())
