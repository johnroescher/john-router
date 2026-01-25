"""Celery tasks for prefetching data."""
import asyncio
from typing import Optional

from .celery_app import celery_app
from app.services.prefetch_service import get_prefetch_service
from app.core.database import AsyncSessionLocal
from app.schemas.common import Coordinate


def run_async(coro):
    """Run async function in Celery task."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, name="prefetch.location_data")
def prefetch_location_data_task(
    self,
    location_lat: float,
    location_lng: float,
    location_region: Optional[str] = None,
    sport_type: Optional[str] = None,
):
    """Background task for prefetching location data."""
    async def _prefetch():
        async with AsyncSessionLocal() as db:
            prefetch_service = await get_prefetch_service()
            location = Coordinate(lat=location_lat, lng=location_lng)
            
            await prefetch_service.prefetch_for_location(
                location=location,
                location_region=location_region,
                sport_type=sport_type,
                db=db,
            )
            return {"status": "prefetched", "location": f"{location_lat},{location_lng}"}

    return run_async(_prefetch())
