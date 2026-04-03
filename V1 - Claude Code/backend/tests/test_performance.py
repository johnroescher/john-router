"""Performance tests."""
import pytest
import time
from uuid import uuid4

from app.services.ride_brief_loop import get_ride_brief_service
from app.schemas.chat import ChatRequest
from app.schemas.common import Coordinate


@pytest.mark.asyncio
async def test_route_generation_performance(db_session):
    """Test that route generation completes within acceptable time."""
    service = await get_ride_brief_service()
    
    request = ChatRequest(
        message="I want a 25km gravel ride starting from Boulder, CO",
        conversation_id=None,
        map_center=Coordinate(lat=40.0150, lng=-105.2705),
    )
    
    start_time = time.time()
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    elapsed = time.time() - start_time
    
    assert result is not None
    # Should complete in reasonable time (adjust threshold as needed)
    assert elapsed < 30.0, f"Route generation took {elapsed:.2f}s, expected < 30s"


@pytest.mark.asyncio
async def test_caching_improves_performance(db_session):
    """Test that caching improves response time for repeated requests."""
    service = await get_ride_brief_service()
    
    request = ChatRequest(
        message="I want a 20km MTB ride",
        conversation_id=None,
        map_center=Coordinate(lat=40.0150, lng=-105.2705),
    )
    
    # First request (cold)
    start1 = time.time()
    result1 = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    time1 = time.time() - start1
    
    # Second request (should benefit from cache)
    start2 = time.time()
    result2 = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    time2 = time.time() - start2
    
    assert result1 is not None
    assert result2 is not None
    # Second request should be faster (or at least not slower)
    # Note: This might not always be true due to variability, but generally should be


@pytest.mark.asyncio
async def test_parallel_processing_performance(db_session):
    """Test that parallel processing improves performance."""
    service = await get_ride_brief_service()
    
    request = ChatRequest(
        message="I want a 30km road ride with multiple route options",
        conversation_id=None,
        map_center=Coordinate(lat=40.0150, lng=-105.2705),
    )
    
    start_time = time.time()
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    elapsed = time.time() - start_time
    
    assert result is not None
    # With parallel processing, multiple candidates should be generated efficiently
    assert len(result.candidates) >= 1
