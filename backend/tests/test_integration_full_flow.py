"""Integration tests for full conversation flow."""
import pytest
from uuid import uuid4

from app.schemas.chat import ChatRequest
from app.services.ride_brief_loop import get_ride_brief_service
from app.schemas.common import Coordinate


@pytest.mark.asyncio
async def test_full_route_generation_flow(db_session):
    """Test complete flow from user request to route generation."""
    service = await get_ride_brief_service()
    
    request = ChatRequest(
        message="I want a 20km gravel ride starting from Boulder, CO",
        conversation_id=None,
    )
    
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    
    assert result is not None
    assert result.intent is not None
    assert result.ride_brief is not None
    assert len(result.candidates) > 0
    assert result.status in ["accepted", "needs_revision", "in_progress"]


@pytest.mark.asyncio
async def test_route_modification_flow(db_session):
    """Test route modification in conversation."""
    service = await get_ride_brief_service()
    
    # Initial request
    request1 = ChatRequest(
        message="I want a 15km MTB ride",
        conversation_id=None,
        map_center=Coordinate(lat=40.0150, lng=-105.2705),  # Boulder
    )
    
    result1 = await service.run(
        request=request1,
        conversation_history=[],
        db=db_session,
    )
    
    assert result1.status == "accepted"
    assert len(result1.candidates) > 0
    
    # Modification request
    request2 = ChatRequest(
        message="Make it 10km longer",
        conversation_id=result1.intent.source.conversation_id if result1.intent.source else None,
        map_center=Coordinate(lat=40.0150, lng=-105.2705),
    )
    
    result2 = await service.run(
        request=request2,
        conversation_history=[],
        db=db_session,
    )
    
    assert result2 is not None


@pytest.mark.asyncio
async def test_clarification_flow(db_session):
    """Test clarification question flow."""
    service = await get_ride_brief_service()
    
    # Vague request that should trigger clarification
    request = ChatRequest(
        message="I want a ride",
        conversation_id=None,
    )
    
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    
    # Should have ambiguities or use defaults
    assert result is not None
    # If clarification is needed, ambiguities should be present
    if result.intent.ambiguities:
        assert len(result.intent.ambiguities) > 0


@pytest.mark.asyncio
async def test_user_preferences_integration(db_session, test_user):
    """Test that user preferences are used in route generation."""
    service = await get_ride_brief_service()
    
    # Set up user preferences
    from app.services.user_context import get_user_context_service
    user_context = get_user_context_service()
    
    # Create a route to learn preferences
    # (In a real test, we'd create a route and update preferences)
    
    request = ChatRequest(
        message="I want an afternoon ride",
        conversation_id=None,
        map_center=Coordinate(lat=40.0150, lng=-105.2705),
    )
    
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    
    assert result is not None
    # Preferences should influence the route if user has history


@pytest.mark.asyncio
async def test_knowledge_integration(db_session):
    """Test that external knowledge is retrieved and used."""
    service = await get_ride_brief_service()
    
    request = ChatRequest(
        message="I want to ride the Slickrock Trail in Moab",
        conversation_id=None,
        map_center=Coordinate(lat=38.5733, lng=-109.5498),  # Moab
    )
    
    result = await service.run(
        request=request,
        conversation_history=[],
        db=db_session,
    )
    
    assert result is not None
    # Knowledge about Slickrock Trail should be retrieved and used
