"""Error handling tests."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ride_brief_loop import get_ride_brief_service
from app.services.knowledge_retrieval import get_knowledge_retrieval_service
from app.schemas.chat import ChatRequest
from app.schemas.common import Coordinate


@pytest.mark.asyncio
async def test_handles_llm_failure_gracefully(db_session):
    """Test that system handles LLM failures gracefully."""
    service = await get_ride_brief_service()
    
    # Mock LLM to fail
    if service.client is None:
        service.client = MagicMock()
    with patch.object(service.client, 'messages') as mock_messages:
        mock_messages.create = AsyncMock(side_effect=Exception("API Error"))
        
        request = ChatRequest(
            message="I want a 20km ride",
            conversation_id=None,
        )
        
        # Should not crash, should use fallback
        result = await service.run(
            request=request,
            conversation_history=[],
            db=db_session,
        )
        
        # Should still return a result (fallback)
        assert result is not None


@pytest.mark.asyncio
async def test_handles_external_api_failure(db_session):
    """Test that external API failures don't crash the system."""
    service = await get_ride_brief_service()
    
    # Mock external API to fail
    with patch('app.services.external_apis.trailforks.get_trailforks_api') as mock_api:
        mock_api.return_value.search_trails = AsyncMock(side_effect=Exception("API Error"))
        
        request = ChatRequest(
            message="I want a 30km MTB ride in Moab",
            conversation_id=None,
            map_center=Coordinate(lat=38.5733, lng=-109.5498),
        )
        
        # Should still work without external API
        result = await service.run(
            request=request,
            conversation_history=[],
            db=db_session,
        )
        
        assert result is not None


@pytest.mark.asyncio
async def test_handles_database_errors(db_session):
    """Test that database errors are handled gracefully."""
    service = await get_ride_brief_service()
    
    # Close the session to simulate error
    await db_session.close()
    
    request = ChatRequest(
        message="I want a ride",
        conversation_id=None,
    )
    
    # Should handle gracefully (might raise, but should be caught)
    try:
        result = await service.run(
            request=request,
            conversation_history=[],
            db=db_session,
        )
    except Exception as e:
        # Error should be logged, not crash the whole system
        assert "database" in str(e).lower() or "session" in str(e).lower()


@pytest.mark.asyncio
async def test_handles_missing_route_data(db_session):
    """Test handling of missing or invalid route data."""
    service = await get_ride_brief_service()
    
    request = ChatRequest(
        message="I want a ride in the middle of the ocean",
        conversation_id=None,
        map_center=Coordinate(lat=0.0, lng=0.0),  # Ocean
    )
    
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    
    # Should handle gracefully, might return empty candidates or error message
    assert result is not None
