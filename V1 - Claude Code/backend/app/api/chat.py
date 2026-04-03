"""Chat API endpoints."""
import asyncio
import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
import structlog
import anthropic

from app.core.database import get_db
from app.models.chat import ChatConversation
from app.models.planning import PlanningSession
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    ChatMessage,
    RouteData,
    StatusUpdate,
    ActionChip,
    PlanningMeta,
)
from uuid import uuid4
from app.services.ride_brief_loop import get_ride_brief_service
from app.services.planning_tools import geocode_place, route_generate
from app.schemas.planning import PlanningLoopResult
from app.schemas.route import RouteCandidateResponse, RouteValidation, RouteResponse
from app.schemas.common import GeoJSONLineString
from app.services.analysis import get_analysis_service
from app.services.validation import get_validation_service
from app.services.surface_match import get_surface_match_service
from app.services.response_generator import get_response_generator
from app.services.route_evaluator import get_route_evaluator
from app.services.conversation_agent import get_conversation_agent
from app.core.feature_flags import is_feature_enabled

chat_router = APIRouter()
logger = structlog.get_logger()

CHAT_RESPONSE_TIMEOUT_SECONDS = 60

# Common place name patterns for extraction
PLACE_PATTERNS = [
    r"(?:near|around|in|at|from|starting from|starting at|close to|by)\s+([A-Z][a-zA-Z\s]+(?:,\s*[A-Z]{2})?)",
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z]{2})?)\s+(?:area|region|trail|trails|loop|route)",
]


def _dependency_status() -> Dict[str, Any]:
    """Return availability of external dependencies for planning meta."""
    from app.core.config import settings
    return {
        "anthropic": bool(settings.anthropic_api_key),
        "ors": bool(settings.ors_api_key),
        "graphhopper": bool(settings.graphhopper_api_key),
        "valhalla": bool(settings.valhalla_api_key),
        "trailforks": bool(settings.trailforks_api_key),
        "openai": bool(settings.openai_api_key),
        "overpass": True,  # Public endpoint
        "brouter": True,   # Public endpoint
    }


def _has_usable_start_location(request: ChatRequest) -> bool:
    """Determine if we have enough information to route a new plan."""
    if request.map_center:
        return True
    if request.current_constraints:
        start = request.current_constraints.get("start")
        if isinstance(start, dict) and start.get("lat") is not None and start.get("lng") is not None:
            return True
    if request.current_route_geometry:
        return True
    if _extract_place_names(request.message):
        return True
    return False


async def _context_has_start_location(
    conversation_id: Optional[UUID],
    db: AsyncSession,
) -> bool:
    if not conversation_id:
        return False
    try:
        result = await db.execute(
            select(PlanningSession).where(PlanningSession.conversation_id == conversation_id)
        )
        session = result.scalar_one_or_none()
    except Exception as exc:
        logger.debug("Failed to load planning session for context", error=str(exc))
        return False
    if not session or not isinstance(session.conversation_context, dict):
        return False

    context = session.conversation_context or {}
    entities = context.get("entities") if isinstance(context, dict) else None
    if isinstance(entities, dict):
        start_location = entities.get("start_location")
        if isinstance(start_location, dict) and start_location.get("lat") is not None and start_location.get("lng") is not None:
            return True
        start_place = entities.get("start_place")
        if isinstance(start_place, str) and start_place.strip():
            return True

    last_intent = context.get("last_intent") if isinstance(context, dict) else None
    if isinstance(last_intent, dict):
        hard_constraints = last_intent.get("hard_constraints") or {}
        start_spec = hard_constraints.get("start") or {}
        start_type = start_spec.get("type")
        start_value = start_spec.get("value")
        if start_type == "point" and isinstance(start_value, dict):
            if start_value.get("lat") is not None and start_value.get("lng") is not None:
                return True
        if start_type == "place" and isinstance(start_value, str) and start_value.strip():
            return True

    return False


async def _has_usable_start_location_async(
    request: ChatRequest,
    db: AsyncSession,
) -> bool:
    if _has_usable_start_location(request):
        return True
    return await _context_has_start_location(request.conversation_id, db)


def _build_clarification_response(
    request: ChatRequest,
    question: str,
    why: Optional[str] = None,
    request_id: Optional[str] = None,
) -> ChatResponse:
    prompt_reference = _build_prompt_reference(request)
    why_text = f"\n\n{why}" if why else ""
    message_text = (
        f"I need a bit more detail: {question}"
        f"{why_text}\n\n"
        f"{prompt_reference}"
    )
    return ChatResponse(
        conversation_id=request.conversation_id or uuid4(),
        message=ChatMessage(
            role="assistant",
            content=message_text.strip(),
            timestamp=datetime.utcnow(),
            tool_calls=[],
            action_chips=[],
            confidence=0.4,
        ),
        route_updated=False,
        suggested_prompts=[],
        needs_clarification=True,
        clarification_question=question,
        planning_meta=PlanningMeta(
            fallback_used=False,
            fallback_reason=None,
            dependency_status=_dependency_status(),
            request_id=request_id,
        ),
    )


def _extract_place_names(message: str) -> List[str]:
    """Extract potential place names from a user message."""
    places = []
    for pattern in PLACE_PATTERNS:
        matches = re.findall(pattern, message)
        for match in matches:
            place = match.strip()
            # Filter out common false positives
            if place.lower() not in {"a", "the", "my", "this", "here", "there", "route", "ride", "loop", "gravel", "mtb", "road"}:
                places.append(place)
    return places


def _extract_sport_type(message: str) -> str:
    """Extract the sport/bike type from a message."""
    msg_lower = message.lower()
    if "mtb" in msg_lower or "mountain bike" in msg_lower or "singletrack" in msg_lower:
        return "mtb"
    if "gravel" in msg_lower or "unpaved" in msg_lower or "dirt" in msg_lower:
        return "gravel"
    if "road" in msg_lower or "paved" in msg_lower or "pavement" in msg_lower:
        return "road"
    return "gravel"  # Default to gravel for mixed terrain


def _extract_explicit_start_point(request: ChatRequest) -> Optional[Tuple[float, float]]:
    """Best-effort extraction of a start point for fallback routing."""
    constraints = request.current_constraints or {}
    start = constraints.get("start") or {}
    if isinstance(start, dict) and start.get("lat") is not None and start.get("lng") is not None:
        return float(start["lat"]), float(start["lng"])

    geometry = request.current_route_geometry or []
    if geometry and isinstance(geometry[0], list) and len(geometry[0]) >= 2:
        lng, lat = geometry[0][0], geometry[0][1]
        return float(lat), float(lng)

    return None


def _parse_distance_from_message(message: str) -> Optional[float]:
    if not message:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(mile|miles|mi|km|kilometer|kilometre|kilometers|kilometres)", message, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"km", "kilometer", "kilometre", "kilometers", "kilometres"}:
        return value * 1000
    return value * 1609.34


def _safe_target_distance_meters(request: ChatRequest) -> float:
    constraints = request.current_constraints or {}
    for key in ("target_distance_meters", "max_distance_meters", "min_distance_meters"):
        value = constraints.get(key)
        if value:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    inferred = _parse_distance_from_message(request.message)
    if inferred:
        return inferred
    return 20000.0


def _format_distance_for_prompt(distance_meters: float, message: str) -> str:
    if re.search(r"\bkm\b|kilometer|kilometre", message, re.IGNORECASE):
        return f"about {distance_meters / 1000:.1f} km"
    return f"about {distance_meters / 1609.34:.1f} mi"


def _build_prompt_reference(request: ChatRequest) -> str:
    message = (request.message or "").strip()
    constraints = request.current_constraints or {}
    sport_type = (
        constraints.get("sport_type")
        or constraints.get("sportType")
        or _extract_sport_type(message)
    )
    route_type = constraints.get("route_type") or constraints.get("routeType")
    inferred_distance = _parse_distance_from_message(message)
    constrained_distance = constraints.get("target_distance_meters") or constraints.get("max_distance_meters") or constraints.get("min_distance_meters")
    distance_meters = constrained_distance or inferred_distance
    places = _extract_place_names(message)

    route_label = None
    if sport_type and route_type:
        route_label = f"{sport_type} {route_type.replace('_', ' ')}"
    elif sport_type:
        route_label = f"{sport_type} route"
    elif route_type:
        route_label = f"{route_type.replace('_', ' ')} route"

    summary_bits = []
    if route_label:
        summary_bits.append(route_label)
    if distance_meters:
        summary_bits.append(_format_distance_for_prompt(float(distance_meters), message))
    if places:
        summary_bits.append(f"around {places[0]}")
    elif constraints.get("start"):
        summary_bits.append("from your start point")

    if summary_bits:
        return f"Keeping your request in mind: {', '.join(summary_bits)}."

    if message:
        short_quote = message if len(message) <= 120 else f"{message[:117].rstrip()}..."
        return f"Keeping your request in mind: “{short_quote}”."

    return "Keeping your request in mind."


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _estimate_distance_meters(coords: List[List[float]]) -> float:
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        total += _haversine_distance_m(lat1, lon1, lat2, lon2)
    return total


def _build_geometric_fallback_geometry(lat: float, lng: float, target_distance_m: float) -> Dict[str, Any]:
    side_m = max(500.0, target_distance_m / 4)
    lat_delta = side_m / 111000.0
    lng_delta = side_m / (111000.0 * max(0.1, math.cos(math.radians(lat))))
    coords = [
        [lng, lat],
        [lng + lng_delta, lat],
        [lng + lng_delta, lat + lat_delta],
        [lng, lat + lat_delta],
        [lng, lat],
    ]
    return {"type": "LineString", "coordinates": coords}


async def _build_route_data_from_geometry(
    geometry: Dict[str, Any],
    sport_type: str,
    route_type: str,
    target_distance_m: float,
) -> RouteData:
    try:
        analysis_service = await get_analysis_service()
        analysis = await analysis_service.analyze_route(geometry)
        segmented_surface = None
        try:
            surface_service = await get_surface_match_service()
            segmented_surface = await surface_service.match_geometry(geometry.get("coordinates", []))
        except Exception as exc:
            logger.debug(f"Surface match failed for fallback geometry: {exc}")
        surface_breakdown = analysis.surface_breakdown.model_dump() if hasattr(analysis.surface_breakdown, "model_dump") else {}
        return RouteData(
            geometry=geometry,
            distance_meters=analysis.distance_meters,
            elevation_gain=analysis.elevation_gain_meters,
            duration_seconds=analysis.estimated_time_seconds,
            sport_type=sport_type,
            route_type=route_type,
            surface_breakdown=surface_breakdown,
            elevation_profile=analysis.elevation_profile,
            segmented_surface=segmented_surface,
        )
    except Exception as e:
        logger.warning("Analysis failed for fallback route", error=str(e))
        coords = geometry.get("coordinates", [])
        estimated_distance = _estimate_distance_meters(coords) or target_distance_m
        return RouteData(
            geometry=geometry,
            distance_meters=estimated_distance,
            elevation_gain=0,
            duration_seconds=estimated_distance / 5,
            sport_type=sport_type,
            route_type=route_type,
            surface_breakdown={"unknown": 100},
        )


def _format_route_summary(route_data: RouteData, location_name: Optional[str] = None) -> str:
    distance_mi = route_data.distance_meters / 1609.34
    elevation_ft = route_data.elevation_gain * 3.28084
    duration_min = route_data.duration_seconds / 60 if route_data.duration_seconds else 0
    route_type = route_data.route_type.replace("_", " ")
    
    # Surface summary
    surface = route_data.surface_breakdown or {}
    unpaved_pct = surface.get("gravel", 0) + surface.get("dirt", 0) + surface.get("singletrack", 0) + surface.get("unpaved", 0)
    paved_pct = surface.get("pavement", 0) + surface.get("paved", 0)
    
    surface_desc = ""
    if unpaved_pct > 70:
        surface_desc = "mostly unpaved"
    elif unpaved_pct > 40:
        surface_desc = "mixed surfaces"
    elif paved_pct > 70:
        surface_desc = "mostly paved"
    
    location_part = f" near {location_name}" if location_name else ""
    surface_part = f", {surface_desc}" if surface_desc else ""
    
    return (
        f"Route: {distance_mi:.1f} mi {route_type}{location_part}, "
        f"{elevation_ft:.0f} ft gain, ~{duration_min:.0f} min{surface_part}."
    )


def _build_follow_up_question(sport_type: str = "gravel") -> str:
    if sport_type == "gravel":
        return "Want it longer/shorter, flatter, or with more/less pavement?"
    elif sport_type == "mtb":
        return "Want it longer/shorter, more/less technical, or different terrain?"
    return "Want it longer/shorter, flatter, or with different surfaces?"


async def _resolve_start_point(request: ChatRequest) -> Tuple[float, float, str, Optional[str]]:
    """Resolve a start point from request. Returns (lat, lng, source, location_name)."""
    # 1. Check for explicit start in constraints
    explicit = _extract_explicit_start_point(request)
    if explicit:
        return explicit[0], explicit[1], "explicit", None

    # 2. Extract and geocode place names from the message
    place_names = _extract_place_names(request.message)
    for place_name in place_names:
        try:
            logger.info(f"Attempting to geocode place name: {place_name}")
            geocoded = await geocode_place(place_name)
            point = geocoded.get("point")
            if point and point.get("lat") is not None and point.get("lng") is not None:
                logger.info(f"Successfully geocoded '{place_name}' to {point}")
                return float(point["lat"]), float(point["lng"]), "place_name", place_name
        except Exception as e:
            logger.warning(f"Failed to geocode '{place_name}': {e}")
            continue

    # 3. Use map center as fallback
    if request.map_center:
        return float(request.map_center.lat), float(request.map_center.lng), "map_center", None

    # 4. Default fallback (should rarely happen)
    return 40.0150, -105.2705, "default", "Boulder, CO"


async def _generate_real_route(lat: float, lng: float, target_distance_m: float, sport_type: str) -> Optional[dict]:
    """Generate a real route using BRouter/ORS routing service.
    
    Returns None if routing fails - never returns fake geometric routes.
    Routes must follow actual roads and trails.
    """
    try:
        from app.services.routing import get_routing_service
        
        # Check routing service availability first
        routing_service = await get_routing_service()
        
        # Diagnostic logging
        logger.info(
            "Route generation attempt",
            lat=lat,
            lng=lng,
            target_distance_m=target_distance_m,
            sport_type=sport_type,
            ors_api_key_configured=bool(routing_service.ors_api_key),
            graphhopper_api_key_configured=bool(routing_service.graphhopper_api_key),
            brouter_available=True,  # BRouter is public, no API key needed
        )
        
        result = await route_generate(
            profile=sport_type,
            waypoints=[{"lat": lat, "lng": lng}],
            options={
                "route_type": "loop",
                "target_distance_km": target_distance_m / 1000,
            },
        )
        
        # Check result
        meta = result.get("meta", {})
        if meta.get("success") is False:
            logger.error(
                "Route generation failed",
                meta=meta,
                has_geometry=bool(result.get("geometry")),
            )
            return None
            
        if result.get("geometry") and result["geometry"].get("coordinates"):
            coords = result["geometry"]["coordinates"]
            if len(coords) >= 4:  # Need at least 4 points for a valid loop
                logger.info(f"Route generation succeeded: {len(coords)} coordinates")
                return result
            else:
                logger.warning(f"Route generation returned insufficient coordinates: {len(coords)} < 4")
        else:
            logger.warning("Route generation returned no geometry", result_keys=list(result.keys()))
            
    except ValueError as e:
        # This is likely an API key or configuration issue
        error_msg = str(e)
        logger.error(f"Route generation configuration error: {error_msg}")
        if "not configured" in error_msg.lower() or "api key" in error_msg.lower():
            logger.error(
                "Routing service unavailable: API key missing",
                error=error_msg,
                sport_type=sport_type,
            )
    except Exception as e:
        logger.error(f"Real route generation failed: {e}", exc_info=True)
        logger.error(
            "Route generation exception details",
            exception_type=type(e).__name__,
            exception_message=str(e),
        )
    return None


# Geometric fallback helper is intentionally last-resort to keep responses alive
# when routing services fail or return no viable geometry.

async def _build_no_route_response(
    request: ChatRequest,
    reason: str,
    detail: Optional[str] = None,
    request_id: Optional[str] = None,
) -> ChatResponse:
    reason_map = {
        "timeout": "Planning took too long to complete.",
        "no_candidates": "No viable route candidates were generated.",
        "no_route_data": "Route generation completed without a usable route geometry.",
        "error": "An unexpected error occurred during planning.",
    }
    reason_text = reason_map.get(reason, "Route generation did not complete.")
    detail_text = f"\n\nDetails: {detail}" if detail else ""

    prompt_reference = _build_prompt_reference(request)
    message_text = (
        f"I couldn't generate a route yet. {reason_text}"
        f"{detail_text}\n\n"
        f"{prompt_reference}\n\n"
        f"Try again, or adjust the request (e.g., change time/distance or terrain)."
    )

    return ChatResponse(
        conversation_id=request.conversation_id or uuid4(),
        message=ChatMessage(
            role="assistant",
            content=message_text.strip(),
            timestamp=datetime.utcnow(),
            tool_calls=[],
            action_chips=[],
            confidence=0.1,
        ),
        route_id=None,
        route_updated=False,
        route_data=None,
        suggested_prompts=[
            "Try again",
            "Make it shorter",
            "Make it less technical",
        ],
        planning_meta=PlanningMeta(
            fallback_used=True,
            fallback_reason=reason,
            dependency_status=_dependency_status(),
            request_id=request_id,
        ),
    )


async def _build_fallback_response(
    request: ChatRequest,
    reason: str,
    note: Optional[str] = None,
    request_id: Optional[str] = None,
) -> ChatResponse:
    lat, lng, source, location_name = await _resolve_start_point(request)
    target_distance_m = _safe_target_distance_meters(request)
    sport_type = _extract_sport_type(request.message)
    
    # Try to generate a real route using routing service
    logger.info(f"Generating route at ({lat}, {lng}), {target_distance_m}m, sport={sport_type}")
    real_route = await _generate_real_route(lat, lng, target_distance_m, sport_type)
    
    if real_route and real_route.get("geometry"):
        geometry = real_route["geometry"]
        meta = real_route.get("meta", {})
        surface_breakdown = meta.get("surface_breakdown", {})
        
        route_data = RouteData(
            geometry=geometry,
            distance_meters=meta.get("distance_meters", target_distance_m),
            elevation_gain=meta.get("elevation_gain", 0),
            duration_seconds=meta.get("duration_seconds", target_distance_m / 5),
            sport_type=sport_type,
            route_type="loop",
            surface_breakdown=surface_breakdown,
        )
        confidence = 0.70
        route_quality = "I found a route following actual roads and trails."
    else:
        geometry = None
        constraints = request.current_constraints or {}
        route_type = constraints.get("route_type") or constraints.get("routeType") or "loop"
        if request.current_route_geometry:
            geometry = {"type": "LineString", "coordinates": request.current_route_geometry}
            route_quality = "I reused your current route geometry as a fallback."
            confidence = 0.55
        if not geometry:
            geometry = _build_geometric_fallback_geometry(lat, lng, target_distance_m)
            route_quality = "I created a simplified fallback loop near your start."
            confidence = 0.35
        route_data = await _build_route_data_from_geometry(geometry, sport_type, route_type, target_distance_m)

    source_messages = {
        "explicit": "Using your start point.",
        "place_name": f"Found '{location_name}' from your request.",
        "map_center": "Using the map center as your start.",
        "default": f"Starting from {location_name or 'a default location'}.",
    }
    source_line = source_messages.get(source, "")

    prompt_reference = _build_prompt_reference(request)
    timeout_note = ""
    if reason == "timeout":
        timeout_note = (
            "\n\nI went with the best route I could assemble before the clock buzzer. "
            "Tell me what you like or want tweaked—I love quick feedback."
        )

    fallback_note = f"\n\nNote: {note}" if note else ""
    message_text = (
        f"{source_line} {route_quality}\n\n"
        f"{_format_route_summary(route_data, location_name)}"
        f"{timeout_note}"
        f"{fallback_note}\n\n"
        f"{prompt_reference}\n\n"
        f"{_build_follow_up_question(sport_type)}"
    )

    return ChatResponse(
        conversation_id=request.conversation_id or uuid4(),
        message=ChatMessage(
            role="assistant",
            content=message_text.strip(),
            timestamp=datetime.utcnow(),
            tool_calls=[],
            action_chips=[],
            confidence=confidence,
        ),
        route_id=str(uuid4()),
        route_updated=True,
        route_data=route_data,
        suggested_prompts=[
            "Make it longer",
            "Reduce climbing",
            f"More {'singletrack' if sport_type == 'mtb' else 'gravel'}, less pavement",
        ],
        planning_meta=PlanningMeta(
            fallback_used=True,
            fallback_reason=reason,
            dependency_status=_dependency_status(),
            request_id=request_id,
        ),
    )


@chat_router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI copilot and get a response."""
    request_id = http_request.headers.get("X-Request-Id")
    # Get or create conversation
    conversation = None
    history = []

    if request.conversation_id:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == request.conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if conversation:
            history = [ChatMessage(**msg) for msg in conversation.messages]

    # Require a usable start location unless modifying an existing route
    if not await _has_usable_start_location_async(request, db):
        return _build_clarification_response(
            request=request,
            question="Where should the route start?",
            why="I need a starting point (or a nearby place name) to build the route.",
            request_id=request_id,
        )

    # Trigger prefetch if we have location information
    if request.map_center:
        try:
            from app.workers.prefetch_tasks import prefetch_location_data_task
            # Trigger async prefetch (don't wait for it)
            prefetch_location_data_task.delay(
                location_lat=request.map_center.lat,
                location_lng=request.map_center.lng,
            )
        except Exception as e:
            logger.debug(f"Prefetch trigger failed (non-critical): {e}")

    # Get response from Ride Brief Loop
    try:
        planner = await get_ride_brief_service()
        planning_result: PlanningLoopResult = await asyncio.wait_for(
            planner.run(request, history, db, request_id=request_id),
            timeout=CHAT_RESPONSE_TIMEOUT_SECONDS,
        )
        response = await _build_chat_response(request, planning_result, request_id=request_id)
        if response.route_updated and not response.route_data and not response.route_id:
            logger.warning("Route marked updated but missing data; returning fallback route")
            response = await _build_fallback_response(
                request,
                reason="no_route_data",
                note="Planning returned no usable route data.",
                request_id=request_id,
            )
        elif (not response.route_updated) and (not planning_result.candidates):
            logger.warning("Planning produced no candidates; returning fallback route")
            response = await _build_fallback_response(
                request,
                reason="no_candidates",
                note="Planning produced no viable candidates.",
                request_id=request_id,
            )
    except asyncio.TimeoutError:
        logger.warning("Chat planning timed out; returning fallback route")
        response = await _build_fallback_response(request, reason="timeout", request_id=request_id)
    except anthropic.BadRequestError as e:
        message = str(e)
        if "credit balance" in message.lower():
            response = await _build_fallback_response(
                request,
                reason="error",
                note="AI credit balance is too low; returned a fallback route.",
                request_id=request_id,
            )
        else:
            response = await _build_fallback_response(
                request,
                reason="error",
                note=f"AI request error: {message}",
                request_id=request_id,
            )
    except anthropic.AuthenticationError:
        response = await _build_fallback_response(
            request,
            reason="error",
            note="Invalid AI API key; returned a fallback route.",
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        response = await _build_fallback_response(request, reason="error", note=str(e), request_id=request_id)

    # Save conversation (best effort; don't block response on DB issues)
    try:
        if conversation:
            # Append messages
            messages = conversation.messages.copy()
            messages.append({
                "role": "user",
                "content": request.message,
                "timestamp": response.message.timestamp.isoformat(),
                "tool_calls": [],
                "action_chips": [],
            })
            messages.append({
                "role": "assistant",
                "content": response.message.content,
                "timestamp": response.message.timestamp.isoformat(),
                "tool_calls": [tc.model_dump() for tc in response.message.tool_calls],
                "action_chips": [ac.model_dump() for ac in response.message.action_chips],
                "confidence": response.message.confidence,
            })
            conversation.messages = messages

            if request.current_constraints:
                conversation.current_constraints = request.current_constraints

        else:
            # Create new conversation
            conversation = ChatConversation(
                user_id=None,  # Would come from auth
                route_id=None,  # Routes are cached in-memory, not persisted until saved
                messages=[
                    {
                        "role": "user",
                        "content": request.message,
                        "timestamp": response.message.timestamp.isoformat(),
                        "tool_calls": [],
                        "action_chips": [],
                    },
                    {
                        "role": "assistant",
                        "content": response.message.content,
                        "timestamp": response.message.timestamp.isoformat(),
                        "tool_calls": [tc.model_dump() for tc in response.message.tool_calls],
                        "action_chips": [ac.model_dump() for ac in response.message.action_chips],
                        "confidence": response.message.confidence,
                    },
                ],
                current_constraints=request.current_constraints or {},
            )
            db.add(conversation)

        await db.commit()
        await db.refresh(conversation)
        response.conversation_id = conversation.id
    except Exception as exc:
        logger.warning("Skipping conversation save due to database error", error=str(exc))
        response.conversation_id = request.conversation_id or response.conversation_id

    return response


async def _stream_chat_response(
    request: ChatRequest,
    db: AsyncSession,
    request_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream chat response with status updates via SSE."""
    try:
        if not await _has_usable_start_location_async(request, db):
            clarification = _build_clarification_response(
                request=request,
                question="Where should the route start?",
                why="I need a starting point (or a nearby place name) to build the route.",
                request_id=request_id,
            )
            response_dict = clarification.model_dump()
            response_dict["message"]["timestamp"] = clarification.message.timestamp.isoformat()
            response_dict["conversation_id"] = str(clarification.conversation_id)
            yield f"data: {json.dumps({'type': 'response', 'data': response_dict})}\n\n"
            return

        # Get or create conversation
        conversation = None
        history = []

        if request.conversation_id:
            result = await db.execute(
                select(ChatConversation).where(ChatConversation.id == request.conversation_id)
            )
            conversation = result.scalar_one_or_none()

            if conversation:
                history = [ChatMessage(**msg) for msg in conversation.messages]

        # Status updates queue
        status_queue = asyncio.Queue()

        async def status_callback(stage: str, message: str, progress: Optional[float] = None):
            """Callback to emit status updates."""
            try:
                logger.info(f"Status update: {stage} - {message}", progress=progress)
                status = StatusUpdate(
                    stage=stage,
                    message=message,
                    progress=progress,
                    timestamp=datetime.utcnow(),
                )
                await status_queue.put(("status", status))
            except Exception as e:
                logger.error(f"Status callback error: {e}", exc_info=True)
                # Don't raise - just log the error

        # Run planning in background task
        async def run_planning():
            try:
                # Send immediate status to replace "Starting..." message
                try:
                    await status_callback("extracting_intent", "Initializing...", 0.01)
                except Exception as status_err:
                    logger.warning(f"Failed to send initial status: {status_err}")
                
                planner = await get_ride_brief_service()
                logger.info("Starting planning loop", message=request.message[:100])
                planning_result: PlanningLoopResult = await asyncio.wait_for(
                    planner.run(request, history, db, status_callback=status_callback, request_id=request_id),
                    timeout=CHAT_RESPONSE_TIMEOUT_SECONDS,
                )
                logger.info("Planning loop completed", status=planning_result.status)
                response = await _build_chat_response(request, planning_result, request_id=request_id)
                if response.route_updated and not response.route_data and not response.route_id:
                    logger.warning("Route marked updated but missing data; returning fallback route")
                    response = await _build_fallback_response(
                        request,
                        reason="no_route_data",
                        note="Planning returned no usable route data.",
                        request_id=request_id,
                    )
                elif (not response.route_updated) and (not planning_result.candidates):
                    logger.warning("Planning produced no candidates; returning fallback route")
                    response = await _build_fallback_response(
                        request,
                        reason="no_candidates",
                        note="Planning produced no viable candidates.",
                        request_id=request_id,
                    )
                await status_queue.put(("response", response))
            except asyncio.TimeoutError:
                logger.warning("Chat planning timed out; returning fallback route")
                response = await _build_fallback_response(request, reason="timeout", request_id=request_id)
                await status_queue.put(("response", response))
            except anthropic.BadRequestError as e:
                message = str(e)
                if "credit balance" in message.lower():
                    response = await _build_fallback_response(
                        request,
                        reason="error",
                        note="AI credit balance is too low; returned a fallback route.",
                        request_id=request_id,
                    )
                else:
                    response = await _build_fallback_response(
                        request,
                        reason="error",
                        note=f"AI request error: {message}",
                        request_id=request_id,
                    )
                await status_queue.put(("response", response))
            except anthropic.AuthenticationError:
                response = await _build_fallback_response(
                    request,
                    reason="error",
                    note="Invalid AI API key; returned a fallback route.",
                    request_id=request_id,
                )
                await status_queue.put(("response", response))
            except Exception as e:
                logger.error(f"Chat error: {e}", exc_info=True)
                try:
                    error_status = StatusUpdate(
                        stage="error",
                        message=f"Error: {str(e)[:100]}",
                        timestamp=datetime.utcnow(),
                    )
                    await status_queue.put(("status", error_status))
                except Exception:
                    pass
                response = await _build_fallback_response(request, reason="error", note=str(e), request_id=request_id)
                await status_queue.put(("response", response))

        # Start planning task
        planning_task = asyncio.create_task(run_planning())

        async def heartbeat():
            try:
                while not planning_task.done():
                    await asyncio.sleep(8)
                    await status_callback("working", "Still working on your route...", None)
            except asyncio.CancelledError:
                return

        heartbeat_task = asyncio.create_task(heartbeat())

        # Stream status updates and final response
        # Send an immediate status to show we're connected
        try:
            initial_status = StatusUpdate(
                stage="extracting_intent",
                message="Connecting...",
                timestamp=datetime.utcnow(),
            )
            status_dict = initial_status.model_dump()
            status_dict["timestamp"] = status_dict["timestamp"].isoformat()
            yield f"data: {json.dumps({'type': 'status', 'data': status_dict})}\n\n"
        except Exception as e:
            logger.warning(f"Failed to send initial status: {e}")
        
        while True:
            try:
                # Wait for status update or response with timeout
                item_type, item = await asyncio.wait_for(status_queue.get(), timeout=1.0)
                
                if item_type == "status":
                    # Yield status update as SSE event
                    status_dict = item.model_dump()
                    status_dict["timestamp"] = status_dict["timestamp"].isoformat()
                    yield f"data: {json.dumps({'type': 'status', 'data': status_dict})}\n\n"
                
                elif item_type == "response":
                    # Save conversation and yield final response
                    try:
                        if conversation:
                            messages = conversation.messages.copy()
                            messages.append({
                                "role": "user",
                                "content": request.message,
                                "timestamp": item.message.timestamp.isoformat(),
                                "tool_calls": [],
                                "action_chips": [],
                            })
                            messages.append({
                                "role": "assistant",
                                "content": item.message.content,
                                "timestamp": item.message.timestamp.isoformat(),
                                "tool_calls": [tc.model_dump() for tc in item.message.tool_calls],
                                "action_chips": [ac.model_dump() for ac in item.message.action_chips],
                                "confidence": item.message.confidence,
                            })
                            conversation.messages = messages
                            if request.current_constraints:
                                conversation.current_constraints = request.current_constraints
                        else:
                            conversation = ChatConversation(
                                user_id=None,
                                route_id=None,
                                messages=[
                                    {
                                        "role": "user",
                                        "content": request.message,
                                        "timestamp": item.message.timestamp.isoformat(),
                                        "tool_calls": [],
                                        "action_chips": [],
                                    },
                                    {
                                        "role": "assistant",
                                        "content": item.message.content,
                                        "timestamp": item.message.timestamp.isoformat(),
                                        "tool_calls": [tc.model_dump() for tc in item.message.tool_calls],
                                        "action_chips": [ac.model_dump() for ac in item.message.action_chips],
                                        "confidence": item.message.confidence,
                                    },
                                ],
                                current_constraints=request.current_constraints or {},
                            )
                            db.add(conversation)

                        await db.commit()
                        await db.refresh(conversation)
                        item.conversation_id = conversation.id
                    except Exception as exc:
                        logger.warning("Skipping conversation save due to database error", error=str(exc))
                        item.conversation_id = request.conversation_id or item.conversation_id
                    
                    # Yield final response
                    response_dict = item.model_dump()
                    # Convert datetime objects to ISO strings
                    if "message" in response_dict and "timestamp" in response_dict["message"]:
                        response_dict["message"]["timestamp"] = response_dict["message"]["timestamp"].isoformat()
                    if "conversation_id" in response_dict:
                        response_dict["conversation_id"] = str(response_dict["conversation_id"])
                    yield f"data: {json.dumps({'type': 'response', 'data': response_dict})}\n\n"
                    break
                
                elif item_type == "error":
                    # Yield error status
                    error_dict = item.model_dump()
                    error_dict["timestamp"] = error_dict["timestamp"].isoformat()
                    yield f"data: {json.dumps({'type': 'error', 'data': error_dict})}\n\n"
                    break
                    
            except asyncio.TimeoutError:
                # Check if planning task is done
                if planning_task.done():
                    # Task completed but no response in queue - should not happen
                    break
                # Continue waiting
                continue

        heartbeat_task.cancel()

    except Exception as e:
        logger.error(f"Stream error: {e}")
        error_status = StatusUpdate(
            stage="error",
            message=f"Stream error: {str(e)}",
            timestamp=datetime.utcnow(),
        )
        error_dict = error_status.model_dump()
        error_dict["timestamp"] = error_dict["timestamp"].isoformat()
        yield f"data: {json.dumps({'type': 'error', 'data': error_dict})}\n\n"


@chat_router.post("/message/stream")
async def send_message_stream(
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI copilot and get a streaming response with status updates."""
    request_id = http_request.headers.get("X-Request-Id")
    return StreamingResponse(
        _stream_chat_response(request, db, request_id=request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


async def _build_chat_response(
    request: ChatRequest,
    planning: PlanningLoopResult,
    request_id: Optional[str] = None,
) -> ChatResponse:
    """Format chat response from planning result."""
    async def _build_action_chips_from_suggestions(suggestions: List[str]) -> List[ActionChip]:
        chips: List[ActionChip] = []
        for idx, suggestion in enumerate(suggestions):
            prompt = _suggestion_to_prompt(suggestion)
            if not prompt:
                continue
            chips.append(ActionChip(
                id=f"suggestion_{idx}",
                label=prompt,
                action="send_message",
                data={"message": prompt},
            ))
        return chips

    def _suggestion_to_prompt(suggestion: str) -> Optional[str]:
        suggestion_lower = suggestion.lower()
        if "flatter" in suggestion_lower or "avoid hills" in suggestion_lower:
            return "Make it flatter"
        if "busy roads" in suggestion_lower or "quieter" in suggestion_lower or "traffic" in suggestion_lower:
            return "Avoid busy roads"
        if "extend" in suggestion_lower or "longer" in suggestion_lower or "more distance" in suggestion_lower:
            return "Make it longer"
        if "surface" in suggestion_lower or "better surface" in suggestion_lower:
            return "Improve surface quality"
        if "scenic detour" in suggestion_lower or "scenic" in suggestion_lower:
            return "Add a scenic detour"
        if "point of interest" in suggestion_lower or "interesting stop" in suggestion_lower:
            return "Add an interesting stop"
        return suggestion.strip().rstrip(".") if suggestion else None
    # Check if clarification is needed
    if planning.intent.ambiguities and len(planning.intent.ambiguities) > 0:
        # Return clarification question instead of route
        ambiguity = planning.intent.ambiguities[0]
        prompt_reference = _build_prompt_reference(request)
        clarification_message = ChatMessage(
            role="assistant",
            content=(
                f"I'd like to clarify: {ambiguity.question}\n\n"
                f"{ambiguity.why_it_matters}\n\n"
                f"(If you don't specify, I'll use: {ambiguity.default_if_unanswered})\n\n"
                f"{prompt_reference}"
            ),
        )
        return ChatResponse(
            conversation_id=request.conversation_id or uuid4(),
            message=clarification_message,
            route_updated=False,
            suggested_prompts=[],
            needs_clarification=True,
            clarification_question=ambiguity.question,
            planning_meta=PlanningMeta(
                fallback_used=False,
                fallback_reason=None,
                dependency_status=_dependency_status(),
                request_id=request_id,
            ),
        )

    if planning.failure_reason:
        clarification_question = None
        if planning.failure_reason.startswith("clarification_required:"):
            clarification_question = planning.failure_reason.split("clarification_required:", 1)[1].strip()
        prompt_reference = _build_prompt_reference(request)
        message_lines = [clarification_question or planning.failure_reason]
        if planning.fallback_suggestion:
            message_lines.append(planning.fallback_suggestion)
        message_lines.append("")
        message_lines.append(prompt_reference)
        message_lines.append("")
        message_lines.append(_build_follow_up_question())
        message = ChatMessage(
            role="assistant",
            content="\n".join([line for line in message_lines if line is not None]).strip(),
            timestamp=datetime.utcnow(),
            tool_calls=[],
            action_chips=[],
            confidence=0.5,
        )
        return ChatResponse(
            conversation_id=request.conversation_id or uuid4(),
            message=message,
            route_updated=False,
            suggested_prompts=[],
            planning=planning,
            route_candidates=[],
            needs_clarification=bool(clarification_question),
            clarification_question=clarification_question,
            planning_meta=PlanningMeta(
                fallback_used=False,
                fallback_reason=None,
                dependency_status=_dependency_status(),
                request_id=request_id,
            ),
        )
    
    summary = planning.ride_brief.brief_summary_for_ui
    candidate_labels = ", ".join([c.label for c in planning.candidates])
    recommendation = ""
    action_chips: List[ActionChip] = []
    if planning.critique.ranked_candidates:
        top = planning.critique.ranked_candidates[0]
        top_candidate = next((c for c in planning.candidates if c.candidate_id == top.candidate_id), None)
        label = top_candidate.label if top_candidate else "Top candidate"
        recommendation = f"Top pick: {label} ({top.recommendation})."

    prompt_reference = _build_prompt_reference(request)
    intent_summary = f"{planning.intent.hard_constraints.discipline} {planning.intent.hard_constraints.route_type}"
    message_lines = [
        summary.one_liner,
        " / ".join(summary.bullets),
        "",
        f"Candidates: {candidate_labels or 'none'}",
        recommendation,
        f"Routing: {intent_summary} | {len(planning.candidates)} candidates | status: {planning.status}",
    ]

    route_candidates = await _build_route_candidates(planning)
    route_updated = planning.status == "accepted" and planning.selected_candidate_id is not None
    route_data = None
    route_id = planning.selected_candidate_id

    if route_updated and planning.selected_candidate_id:
        selected = next((c for c in planning.candidates if c.candidate_id == planning.selected_candidate_id), None)
        if selected:
            evaluation = None
            analysis = None
            segmented_surface = None
            if is_feature_enabled("route_evaluation"):
                try:
                    route_evaluator = get_route_evaluator()
                    evaluation = await route_evaluator.evaluate_route_against_intent(
                        route=selected,
                        intent=planning.intent,
                        original_request=request.message,
                    )
                except Exception as e:
                    logger.warning(f"Route evaluation failed during response generation: {e}", exc_info=True)

            route_type = "loop"
            if request.current_constraints:
                route_type = request.current_constraints.get("route_type") or request.current_constraints.get("routeType") or "loop"
            try:
                analysis_service = await get_analysis_service()
                analysis = await analysis_service.analyze_route(selected.geometry)
            except Exception as e:
                logger.warning(f"Failed to analyze selected route for response: {e}", exc_info=True)

            try:
                surface_service = await get_surface_match_service()
                segmented_surface = await surface_service.match_geometry(selected.geometry.get("coordinates", []))
            except Exception as e:
                logger.debug(f"Surface enrichment skipped for response: {e}")

            surface_breakdown = selected.computed.surface_mix.model_dump()
            elevation_profile = None
            if analysis:
                surface_breakdown = analysis.surface_breakdown.model_dump() if hasattr(analysis.surface_breakdown, "model_dump") else surface_breakdown
                elevation_profile = analysis.elevation_profile

            route_data = RouteData(
                geometry=selected.geometry,
                distance_meters=selected.computed.distance_km * 1000,
                elevation_gain=selected.computed.elevation_gain_m,
                duration_seconds=selected.computed.time_est_min * 60,
                sport_type=selected.routing_profile,
                route_type=route_type,
                surface_breakdown=surface_breakdown,
                elevation_profile=elevation_profile,
                segmented_surface=segmented_surface,
                transition_segments=selected.transition_segments,
            )
            if is_feature_enabled("response_generation"):
                try:
                    response_generator = get_response_generator()
                    message_text = await response_generator.generate_route_response(
                        route=selected,
                        intent=planning.intent,
                        evaluation=evaluation,
                        original_request=request.message,
                    )
                    message_lines = [message_text]
                except Exception as e:
                    logger.warning(f"Response generator failed: {e}", exc_info=True)
                    message_lines.append(_format_route_summary(route_data))
            else:
                message_lines.append(_format_route_summary(route_data))

            if is_feature_enabled("proactive_suggestions") and evaluation:
                try:
                    conversation_agent = get_conversation_agent()
                    suggestions = conversation_agent.get_proactive_suggestions(selected, evaluation)
                    action_chips = await _build_action_chips_from_suggestions(suggestions)
                except Exception as e:
                    logger.warning(f"Failed to build suggestion chips: {e}", exc_info=True)

    message_lines.append("")
    message_lines.append(prompt_reference)
    message_lines.append("")
    message_lines.append(_build_follow_up_question())

    message = ChatMessage(
        role="assistant",
        content="\n".join([line for line in message_lines if line is not None]).strip(),
        timestamp=datetime.utcnow(),
        tool_calls=[],
        action_chips=action_chips,
        confidence=0.75 if route_updated else 0.55,
    )

    return ChatResponse(
        conversation_id=request.conversation_id or uuid4(),
        message=message,
        route_id=route_id,
        route_updated=route_updated,
        route_data=route_data,
        suggested_prompts=[
            "Tighten the pavement cap",
            "Lower technical max",
            "Make it shorter",
        ],
        planning=planning,
        route_candidates=route_candidates,
        planning_meta=PlanningMeta(
            fallback_used=False,
            fallback_reason=None,
            dependency_status=_dependency_status(),
            request_id=request_id,
        ),
    )


async def _build_route_candidates(planning: PlanningLoopResult) -> List[RouteCandidateResponse]:
    analysis_service = await get_analysis_service()
    validation_service = await get_validation_service()
    responses: List[RouteCandidateResponse] = []

    for idx, candidate in enumerate(planning.candidates):
        geometry = candidate.geometry
        if not geometry:
            continue
        analysis = await analysis_service.analyze_route(geometry)
        validation = await validation_service.validate_route(geometry)

        route_response = RouteResponse(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            user_id=None,
            name=f"Candidate {candidate.label}",
            description=None,
            sport_type=candidate.routing_profile,
            geometry=GeoJSONLineString(type="LineString", coordinates=geometry.get("coordinates", [])),
            distance_meters=analysis.distance_meters,
            elevation_gain_meters=analysis.elevation_gain_meters,
            elevation_loss_meters=analysis.elevation_loss_meters,
            estimated_time_seconds=analysis.estimated_time_seconds,
            max_elevation_meters=analysis.max_elevation_meters,
            min_elevation_meters=analysis.min_elevation_meters,
            surface_breakdown=analysis.surface_breakdown,
            mtb_difficulty_breakdown=analysis.mtb_difficulty_breakdown,
            physical_difficulty=analysis.physical_difficulty,
            technical_difficulty=analysis.technical_difficulty,
            risk_rating=analysis.risk_rating,
            overall_difficulty=analysis.overall_difficulty,
            tags=[],
            is_public=False,
            confidence_score=analysis.confidence_score,
            validation_status=validation.status,
            validation_results=RouteValidation(
                status=validation.status,
                errors=validation.errors,
                warnings=validation.warnings,
                info=validation.info,
                confidence_score=validation.confidence_score,
            ),
            waypoints=[],
            created_at=None,
            updated_at=None,
        )

        responses.append(RouteCandidateResponse(
            route=route_response,
            analysis=analysis,
            validation=validation,
            rank=idx + 1,
            explanation=f"Loop candidate {candidate.label}",
            tradeoffs={},
        ))

    return responses


@chat_router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List chat conversations."""
    result = await db.execute(
        select(ChatConversation)
        .offset(skip)
        .limit(limit)
        .order_by(ChatConversation.updated_at.desc())
    )
    conversations = result.scalars().all()

    return [
        ConversationResponse(
            id=c.id,
            user_id=c.user_id,
            route_id=c.route_id,
            messages=[ChatMessage(**msg) for msg in c.messages],
            current_constraints=c.current_constraints,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conversations
    ]


@chat_router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific conversation."""
    result = await db.execute(
        select(ChatConversation).where(ChatConversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        route_id=conversation.route_id,
        messages=[ChatMessage(**msg) for msg in conversation.messages],
        current_constraints=conversation.current_constraints,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@chat_router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation."""
    result = await db.execute(
        select(ChatConversation).where(ChatConversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conversation)
    await db.commit()

    return {"message": "Conversation deleted"}


@chat_router.post("/action/{action_id}")
async def execute_action(
    action_id: str,
    conversation_id: Optional[UUID] = None,
    route_id: Optional[UUID] = None,
    data: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
):
    """Execute an action chip from the chat."""
    # Map action IDs to operations
    if action_id == "export_gpx" and route_id:
        # Redirect to GPX export
        return {"redirect": f"/api/routes/{route_id}/export/gpx"}

    elif action_id == "try_alternatives":
        # Generate more alternatives
        return {"message": "Send a chat message asking for alternatives"}

    elif action_id.startswith("modify_constraint"):
        # Suggest constraint modification
        return {"message": "Use the controls to adjust constraints"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_id}")
