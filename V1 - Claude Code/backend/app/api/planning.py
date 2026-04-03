"""Planning API endpoints for Ride Brief updates."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.database import get_db
from app.schemas.chat import ChatResponse, ChatRequest
from app.schemas.planning import PlanningBriefUpdateRequest
from app.services.ride_brief_loop import get_ride_brief_service
from app.api.chat import _build_chat_response

planning_router = APIRouter()
logger = structlog.get_logger()


@planning_router.post("/update-brief", response_model=ChatResponse)
async def update_ride_brief(
    request: PlanningBriefUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update Ride Brief assumptions and rerun planning loop."""
    planner = await get_ride_brief_service()
    try:
        # Reuse chat response format for UI updates
        tmp_request = ChatRequest(
            message="Update ride brief",
            conversation_id=request.conversation_id,
            route_id=None,
            current_constraints={},
            current_route_geometry=request.current_route_context or [],
            quality_mode=True,
            explain_mode=True,
        )
        result = await planner.run(
            request=tmp_request,
            conversation_history=[],
            db=db,
            brief_updates=request.updates,
        )
        return await _build_chat_response(
            request=tmp_request,
            planning=result,
        )
    except Exception as exc:
        logger.error("Brief update failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update Ride Brief")

