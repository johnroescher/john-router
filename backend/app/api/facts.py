"""Facts API endpoints."""
from fastapi import APIRouter, Query

from app.schemas.common import CyclingFactsResponse
from app.services.cycling_facts import get_cycling_facts_service

facts_router = APIRouter()


@facts_router.get("/cycling", response_model=CyclingFactsResponse)
async def get_cycling_facts(count: int = Query(6, ge=3, le=12)) -> CyclingFactsResponse:
    """Return short cycling facts for loading UI."""
    service = get_cycling_facts_service()
    facts = await service.get_facts(count=count)
    return CyclingFactsResponse(facts=facts)
