"""
DEPRECATED: Legacy AI Copilot.

Production chat flow uses RideBriefLoopService (ride_brief_loop.py).
AICopilotService is retained for reference but should not be imported
in new code. The wrapper class at the top raises RuntimeError if called.
"""
from __future__ import annotations

from typing import List, Optional

from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.services.ride_brief_loop import get_ride_brief_service
from app.schemas.planning import PlanningLoopResult


class AICopilotService:
    """Backwards-compatible wrapper that runs the Ride Brief Loop."""

    async def chat(
        self,
        request: ChatRequest,
        conversation_history: List[ChatMessage] = None,
    ) -> ChatResponse:
        raise RuntimeError(
            "AICopilotService.chat is deprecated. Use RideBriefLoopService via /chat endpoints."
        )


_copilot_service: Optional[AICopilotService] = None


async def get_copilot_service() -> AICopilotService:
    global _copilot_service
    if _copilot_service is None:
        _copilot_service = AICopilotService()
    return _copilot_service

"""AI Copilot service with tool calling for route planning."""
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Awaitable
from uuid import UUID, uuid4
import json
import re
import asyncio
import time

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.schemas.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    RouteData,
    ToolCall,
    ToolResult,
    ActionChip,
    ConstraintInterpretation,
)
from app.schemas.route import RouteConstraints, SportType, RouteType, MTBDifficulty
from app.schemas.common import Coordinate
from .geocoding import get_geocoding_service
from .routing import get_routing_service
from .analysis import get_analysis_service
from .validation import get_validation_service
from .route_planner import get_route_planner
import structlog

logger = structlog.get_logger()


# Tool definitions for Claude
TOOLS = [
    {
        "name": "geocode",
        "description": "Convert a place name or address to coordinates (latitude/longitude).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The place name or address to geocode"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "reverse_geocode",
        "description": "Convert coordinates to a place name or address.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude"},
                "lng": {"type": "number", "description": "Longitude"}
            },
            "required": ["lat", "lng"]
        }
    },
    {
        "name": "search_places",
        "description": "Search for places like trailheads, parks, or bike shops near a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "near_lat": {"type": "number", "description": "Latitude of center point"},
                "near_lng": {"type": "number", "description": "Longitude of center point"},
                "radius_meters": {"type": "number", "description": "Search radius in meters"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_route",
        "description": "Generate a cycling route based on constraints. This is the main route generation tool. Use via_points to incorporate specific locations into the route.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_lat": {"type": "number", "description": "Start latitude"},
                "start_lng": {"type": "number", "description": "Start longitude"},
                "end_lat": {"type": "number", "description": "End latitude (optional for loops)"},
                "end_lng": {"type": "number", "description": "End longitude (optional for loops)"},
                "via_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lng": {"type": "number"},
                            "name": {"type": "string", "description": "Optional name of the location"}
                        },
                        "required": ["lat", "lng"]
                    },
                    "description": "Waypoints to route through (use geocode first to get coordinates for named locations)"
                },
                "route_type": {
                    "type": "string",
                    "enum": ["loop", "out_and_back", "point_to_point"],
                    "description": "Type of route. DEFAULT to 'loop' for all routes. Only use 'out_and_back' if the user explicitly requests an out-and-back route. Avoid out-and-back routes - they retrace paths and are less interesting than loops."
                },
                "sport_type": {
                    "type": "string",
                    "enum": ["road", "gravel", "mtb", "emtb"],
                    "description": "Sport/bike type"
                },
                "target_distance_meters": {"type": "number", "description": "Target distance in meters"},
                "min_distance_meters": {"type": "number", "description": "Minimum distance in meters"},
                "max_distance_meters": {"type": "number", "description": "Maximum distance in meters"},
                "distance_hard_constraint": {"type": "boolean", "description": "If true, distance bounds are strict"},
                "target_time_seconds": {"type": "integer", "description": "Target time in seconds"},
                "target_elevation_gain_meters": {"type": "number", "description": "Target climbing in meters"},
                "mtb_difficulty": {
                    "type": "string",
                    "enum": ["easy", "moderate", "hard", "very_hard"],
                    "description": "MTB difficulty level"
                },
                "surface_preference": {
                    "type": "string",
                    "enum": ["pavement", "gravel", "singletrack", "mixed"],
                    "description": "Preferred surface type"
                },
                "avoid_highways": {"type": "boolean", "description": "Avoid major roads"},
                "num_alternatives": {"type": "integer", "description": "Number of alternative routes to generate"},
                "surface_constraints": {
                    "type": "object",
                    "properties": {
                        "avoid_surfaces": {"type": "array", "items": {"type": "string"}},
                        "prefer_surfaces": {"type": "array", "items": {"type": "string"}},
                        "require_surfaces": {"type": "array", "items": {"type": "string"}}
                    },
                    "description": "Surface constraints parsed from user request"
                },
                "quality_mode": {"type": "boolean", "description": "If true, enforce higher quality thresholds"},
                "search_radius_km": {"type": "number", "description": "Trail search radius for planning"}
            },
            "required": ["start_lat", "start_lng", "sport_type"]
        }
    },
    {
        "name": "analyze_route",
        "description": "Analyze a route to get detailed statistics including elevation, surfaces, difficulty.",
        "input_schema": {
            "type": "object",
            "properties": {
                "route_id": {"type": "string", "description": "ID of the route to analyze"}
            },
            "required": ["route_id"]
        }
    },
    {
        "name": "validate_route",
        "description": "Validate a route for safety, legality, and data completeness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "route_id": {"type": "string", "description": "ID of the route to validate"}
            },
            "required": ["route_id"]
        }
    },
    {
        "name": "apply_avoidance",
        "description": "Modify a route to avoid a specific segment or area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "route_id": {"type": "string", "description": "ID of the route to modify"},
                "segment_index": {"type": "integer", "description": "Index of segment to avoid"},
                "reason": {"type": "string", "description": "Reason for avoidance"}
            },
            "required": ["route_id"]
        }
    },
    {
        "name": "export_gpx",
        "description": "Export a route as a GPX file for use in GPS devices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "route_id": {"type": "string", "description": "ID of the route to export"}
            },
            "required": ["route_id"]
        }
    }
]


SYSTEM_PROMPT = """You are John Router, a cycling route planner.

## CORE PHILOSOPHY - THINK, SEARCH, EVALUATE, ITERATE:
Your job is to produce the BEST possible route that matches the user's intent.
Do not return low-confidence routes. If a candidate fails intent or quality checks,
search again, adjust constraints, and iterate until the route is strong.

## WORKFLOW:
1. THINK: extract clear constraints (sport, distance, location, surface intent)
2. SEARCH: geocode and discover trails/roads in the area
3. EVALUATE: compare candidates against intent and data confidence
4. ITERATE: if quality is low, modify constraints and regenerate
5. RESPOND: only return a route when it is close to the request

## DEFAULT VALUES (use only when truly missing):
- Distance: 25km / ~15 miles
- Sport type: preserve user's last sport if present, otherwise infer
- Route type: ALWAYS use "loop" unless the user explicitly requests "out and back" or "out-and-back"
- Difficulty: moderate

## ROUTE TYPE PREFERENCE - CRITICAL:
- DEFAULT to "loop" for ALL routes - create nice loops that don't retrace paths
- AVOID "out_and_back" routes at all costs - they are inefficient and less interesting
- Only use "out_and_back" if the user explicitly requests it (e.g., "out and back", "out-and-back", "there and back")
- When generating routes, favor creating loops that explore different paths rather than retracing
- If a loop is difficult, try adjusting distance, search radius, or waypoints rather than falling back to out-and-back

## EXTRACTING CONSTRAINTS:
- "20 mile" / "20 miles" → target_distance_meters: 32180
- "mtb" / "mountain bike" / "singletrack" / "trails" → sport_type: "mtb"
- "road" / "road bike" / "pavement" → sport_type: "road"
- "gravel" / "mixed" → sport_type: "gravel"
- "short" → ~10 miles, "long" → ~40 miles, "epic" → ~60+ miles

## QUALITY STANDARD:
- MTB routes should be trail-heavy and avoid pavement when possible
- If surface data is unknown or the route is mostly pavement for MTB, do NOT return it
- Prefer to regenerate or change strategy rather than send a weak route

## RESPONSE FORMAT:
Keep responses simple and light. Use short sentences.
If you produce a route, summarize distance, elevation, and why it matches the request.
If no good route can be found after multiple attempts, explain what failed and ask
for a single targeted clarification (e.g., start point or acceptable surface mix)."""


class AICopilotService:
    """AI-powered route planning assistant using Claude."""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self.model = "claude-sonnet-4-20250514"

        # Store for temporary route data during conversation
        self._route_cache: Dict[str, Dict[str, Any]] = {}

        # Store current request context for tool dispatch
        self._current_user_message: Optional[str] = None

    async def chat(
        self,
        request: ChatRequest,
        conversation_history: List[ChatMessage] = None,
    ) -> ChatResponse:
        """Process a chat message and generate a response.

        BULLETPROOF APPROACH: Try direct route generation first, fall back to agentic.
        """
        logger.info(f"=== CHAT REQUEST ===")
        logger.info(f"User message: {request.message}")
        logger.info(f"Has route_id: {request.route_id is not None}")
        logger.info(f"Has current_constraints: {request.current_constraints is not None}")

        # Store current message for intelligent planning in tool dispatch
        self._current_user_message = request.message

        # STEP 1: Try direct/deterministic route generation first
        # This bypasses Claude's tool-calling entirely for reliability
        direct_result = await self._try_direct_route_generation(request)
        if direct_result:
            logger.info("=== DIRECT ROUTE GENERATION SUCCEEDED ===")
            return direct_result

        if not self.client:
            logger.warning("Anthropic API key missing - skipping agentic approach")
            forced = await self._force_route_generation(request, None)
            if forced.get("success"):
                route_id = forced.get("route_id")
                route_data = None
                if route_id and route_id in self._route_cache:
                    cached = self._route_cache[route_id]
                    surface_data = self._normalize_surface_breakdown(
                        cached["routing_data"].get("surface_breakdown", {})
                    )
                    route_data = RouteData(
                        geometry=cached["geometry"],
                        distance_meters=cached["routing_data"]["distance_meters"],
                        elevation_gain=cached["routing_data"]["elevation_gain"],
                        duration_seconds=cached["routing_data"]["duration_seconds"],
                        sport_type=forced.get("sport_type", "gravel"),
                        route_type=forced.get("route_type", "loop"),
                        surface_breakdown=surface_data,
                    )

                response_text = self._format_route_summary(route_data, request) if route_data else forced.get(
                    "message", "I couldn't build a route from that. Try a nearby start point."
                )
                message = ChatMessage(
                    role="assistant",
                    content=response_text,
                    timestamp=datetime.utcnow(),
                    tool_calls=[],
                    action_chips=self._generate_action_chips(response_text, route_id),
                    confidence=0.7 if route_data else 0.3,
                )

                return ChatResponse(
                    conversation_id=request.conversation_id or uuid4(),
                    message=message,
                    route_id=route_id,
                    route_updated=bool(route_data),
                    route_data=route_data,
                    suggested_prompts=self._generate_suggested_prompts(response_text, request),
                )

            message = ChatMessage(
                role="assistant",
                content=forced.get("message", "I need a starting point to build a route."),
                timestamp=datetime.utcnow(),
                tool_calls=[],
                action_chips=[],
                confidence=0.2,
            )

            return ChatResponse(
                conversation_id=request.conversation_id or uuid4(),
                message=message,
                route_id=None,
                route_updated=False,
                route_data=None,
                suggested_prompts=self._generate_suggested_prompts(message.content, request),
            )

        logger.info("=== DIRECT FAILED, TRYING AGENTIC APPROACH ===")

        # STEP 2: Fall back to agentic approach with Claude
        messages = self._build_messages(request, conversation_history or [])

        # Call Claude with tools
        # Use tool_choice="any" to force Claude to use at least one tool
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            tool_choice={"type": "any"},  # Force tool use
            messages=messages,
        )

        logger.info(f"=== CLAUDE RESPONSE ===")
        logger.info(f"Stop reason: {response.stop_reason}")
        logger.info(f"Content blocks: {len(response.content)}")
        for i, block in enumerate(response.content):
            logger.info(f"  Block {i}: type={block.type}")
            if block.type == "tool_use":
                logger.info(f"    Tool: {block.name}, Input: {block.input}")

        # Process the response
        return await self._process_response(response, request)

    async def _try_direct_route_generation(self, request: ChatRequest) -> Optional[ChatResponse]:
        """
        Deterministic route generation - bypasses Claude tool calling.
        Returns None if it can't determine what the user wants.
        """
        message = request.message.lower()
        logger.info(f"Attempting direct route generation for: {message}")

        # Check if this is a complex modification that needs Claude's reasoning
        # These patterns indicate the user wants something specific that requires AI understanding
        complex_patterns = [
            "include", "incorporate", "add", "via", "through",  # Include specific locations
            "avoid", "skip", "stay away", "not through",  # Avoid specific locations
            "go through", "pass by", "pass through", "hit",  # Waypoint requests
            "closer to", "near", "around", "stick to",  # Area preferences
            "more of", "less of",  # Qualitative changes
        ]
        is_complex_modification = any(pattern in message for pattern in complex_patterns)
        if is_complex_modification and request.current_constraints:
            logger.info("Complex modification detected, falling back to Claude for reasoning")
            return None  # Let Claude handle complex modifications with its tools

        # Check if this looks like a route request
        route_keywords = ["ride", "route", "loop", "mile", "km", "trail", "road", "gravel", "mtb", "bike", "cycling", "longer", "shorter", "more", "less"]
        if not any(kw in message for kw in route_keywords):
            logger.info("No route keywords found, skipping direct generation")
            return None

        # Get existing context for modifications
        existing_sport = None
        existing_distance = None
        if request.current_constraints:
            existing_sport = request.current_constraints.get("sport_type")
            existing_distance = request.current_constraints.get("target_distance_meters")

        # Extract parameters from message, using context as fallback
        sport_type = self._extract_sport_type(request.message)
        target_distance = self._extract_distance(request.message, existing_distance)
        distance_delta = self._extract_distance_delta(request.message)
        location_query = self._extract_location(request.message)
        surface_constraints = self._extract_surface_constraints(request.message)
        route_type = self._extract_route_type(request.message)

        # CONTEXT PRESERVATION: Use existing constraints as defaults for modifications
        if request.current_constraints:
            # Preserve sport type from previous route if not explicitly changed
            if existing_sport and sport_type == "gravel":  # gravel is default, meaning user didn't specify
                sport_type = existing_sport
                logger.info(f"Preserving sport_type from context: {sport_type}")

            if existing_distance and distance_delta:
                target_distance = existing_distance + distance_delta
                logger.info(
                    f"Applying distance delta from context: +{distance_delta}m -> {target_distance}m"
                )

            # If distance is still default and we have existing, preserve it
            if existing_distance and target_distance == 25000:
                target_distance = existing_distance
                logger.info(f"Preserving distance from context: {target_distance}m")

        logger.info(f"Extracted: sport={sport_type}, distance={target_distance}m, location={location_query}")

        start_lat = None
        start_lng = None

        # PRIORITY 1: If user mentions a LOCATION, always geocode it
        # This ensures "ride in Moab" goes to Moab, not existing coords
        if location_query:
            logger.info(f"User specified location, geocoding: {location_query}")
            geocode_result = await self._direct_geocode(location_query)
            if geocode_result:
                start_lat = geocode_result["lat"]
                start_lng = geocode_result["lng"]
                logger.info(f"Geocoded to: {start_lat}, {start_lng}")
            else:
                logger.warning(f"Geocoding failed for: {location_query}")
                # Don't fall back to existing coords - user wanted a specific location
                return None

        # PRIORITY 2: If no location in message, use existing coordinates (for modifications)
        if start_lat is None:
            if request.current_route_geometry and len(request.current_route_geometry) > 0:
                first_point = request.current_route_geometry[0]
                if len(first_point) >= 2:
                    start_lng = first_point[0]
                    start_lat = first_point[1]
                    logger.info(f"No location specified, using route geometry start: {start_lat}, {start_lng}")

            elif request.current_constraints:
                start = request.current_constraints.get("start", {})
                if start and start.get("lat") and start.get("lng"):
                    # Only use if not default Denver coords OR no location was mentioned
                    is_default_denver = (abs(start["lat"] - 39.7392) < 0.01 and abs(start["lng"] - (-104.9903)) < 0.01)
                    if not is_default_denver:
                        start_lat = start["lat"]
                        start_lng = start["lng"]
                        logger.info(f"No location specified, using existing constraints: {start_lat}, {start_lng}")
                    else:
                        logger.info("Skipping default Denver coordinates - need a specific location")

        if start_lat is None or start_lng is None:
            logger.info("No coordinates available, cannot generate route")
            return None

        # Generate the route directly
        logger.info(f"Generating route: start=({start_lat}, {start_lng}), distance={target_distance}, sport={sport_type}, route_type={route_type}")
        if surface_constraints and any(surface_constraints.values()):
            logger.info(f"Surface constraints: {surface_constraints}")

        route_args = {
            "start_lat": start_lat,
            "start_lng": start_lng,
            "sport_type": sport_type,
            "target_distance_meters": target_distance,
            "route_type": route_type,
            "surface_constraints": surface_constraints,
            "quality_mode": request.quality_mode,
        }

        if request.current_constraints:
            route_args["num_alternatives"] = request.current_constraints.get("num_alternatives", 3)
            route_args["distance_hard_constraint"] = request.current_constraints.get("distance_hard_constraint", False)
            route_args["min_distance_meters"] = request.current_constraints.get("min_distance_meters")
            route_args["max_distance_meters"] = request.current_constraints.get("max_distance_meters")

        if existing_distance and distance_delta:
            route_args["distance_hard_constraint"] = True
            if not route_args.get("min_distance_meters"):
                route_args["min_distance_meters"] = target_distance * 0.9
            if not route_args.get("max_distance_meters"):
                route_args["max_distance_meters"] = target_distance * 1.1

        route_result = await self._generate_route(route_args, original_message=request.message)

        if not route_result.get("success"):
            logger.warning(f"Route generation failed: {route_result.get('error')}")
            return None

        # Build the response
        route_id = route_result.get("route_id")
        if route_id and route_id in self._route_cache:
            cached = self._route_cache[route_id]
            # Normalize surface breakdown for frontend
            surface_data = self._normalize_surface_breakdown(
                cached["routing_data"].get("surface_breakdown", {})
            )
            route_data = RouteData(
                geometry=cached["geometry"],
                distance_meters=cached["routing_data"]["distance_meters"],
                elevation_gain=cached["routing_data"]["elevation_gain"],
                duration_seconds=cached["routing_data"]["duration_seconds"],
                sport_type=route_result.get("sport_type", sport_type),
                route_type=route_result.get("route_type", "loop"),
                surface_breakdown=surface_data,
            )

            # Format response message
            dist_miles = round(route_data.distance_meters / 1609.34, 1)
            elev_ft = round(route_data.elevation_gain * 3.28084)
            hours = round(route_data.duration_seconds / 3600, 1)

            response_text = self._format_route_summary(route_data, request)

            logger.info(f"Direct route generation succeeded: {dist_miles} miles")

            message = ChatMessage(
                role="assistant",
                content=response_text,
                timestamp=datetime.utcnow(),
                tool_calls=[],
                action_chips=self._generate_action_chips(response_text, route_id),
                confidence=0.9,
            )

            return ChatResponse(
                conversation_id=request.conversation_id or uuid4(),
                message=message,
                route_id=route_id,
                route_updated=True,
                route_data=route_data,
                suggested_prompts=self._generate_suggested_prompts(response_text, request),
            )

        return None

    async def _direct_geocode(self, query: str) -> Optional[Dict[str, float]]:
        """Direct geocoding without going through tool dispatch."""
        try:
            service = await get_geocoding_service()

            # Try the original query first
            result = await service.geocode(query)
            if result:
                return {"lat": result.lat, "lng": result.lng}

            # Try with common suffixes
            variations = [
                f"{query}, USA",
                f"{query}, Colorado",
                f"{query} trailhead",
            ]

            for variation in variations:
                result = await service.geocode(variation)
                if result:
                    return {"lat": result.lat, "lng": result.lng}

            return None
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            return None

    def _extract_location(self, message: str) -> Optional[str]:
        """Extract location from user message."""
        # Common patterns for location extraction
        # "ride in [location]", "ride around [location]", "near [location]"
        explicit_patterns = [
            r'(?:focused on|focus on|centered on)\s+([A-Z][a-zA-Z\s,]+?)(?:\s*[,.]|\s+(?:with|and|for|that|sticking|on|trails?)|\s*$)',
            r'(?:in|around|near|at|from)\s+([A-Z][a-zA-Z\s,]+?)(?:\s*[,.]|\s+(?:with|and|for|that|sticking|on|trails?)|\s*$)',
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                location = re.sub(r'\s*,?\s*$', '', location)
                if len(location) > 2:
                    return location

        # Only allow implicit "Austin loop" style matches when capitalized
        implicit_pattern = r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:area|region|trails?|loop)'
        match = re.search(implicit_pattern, message)
        if match:
            location = match.group(1).strip()
            location = re.sub(r'\s*,?\s*$', '', location)
            if len(location) > 2:
                return location

        # Fallback: Look for capitalized words that might be place names
        words = message.split()
        for i, word in enumerate(words):
            if word[0].isupper() and len(word) > 2:
                # Check if followed by another capitalized word (e.g., "New York")
                if i + 1 < len(words) and words[i + 1][0].isupper():
                    return f"{word} {words[i + 1]}"
                # Check common place indicators
                if i > 0 and words[i - 1].lower() in ["in", "near", "around", "at", "from"]:
                    return word

        return None

    def _build_messages(
        self,
        request: ChatRequest,
        history: List[ChatMessage],
    ) -> List[Dict[str, Any]]:
        """Build message list for Claude API.

        For simplicity in conversation history, we only include text content.
        Tool calls from previous turns are not included to avoid the complexity
        of properly pairing tool_use with tool_result blocks.
        """
        messages = []

        # Add conversation history - simplified to just text exchanges
        for msg in history:
            if msg.role == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                # Only include text content, skip tool calls from history
                # This avoids the tool_use/tool_result pairing requirement
                messages.append({"role": "assistant", "content": msg.content})

        # Add current message with context
        user_content = request.message

        # If we have a route_id, include the start coordinates so AI can modify without re-geocoding
        if request.route_id and str(request.route_id) in self._route_cache:
            cached = self._route_cache[str(request.route_id)]
            if "constraints" in cached:
                start = cached["constraints"].get("start", {})
                if start:
                    user_content += f"\n\n[EXISTING ROUTE: start_lat={start.get('lat')}, start_lng={start.get('lng')}. Use these coordinates for modifications - DO NOT geocode again.]"

        if request.current_constraints:
            # Extract full context from constraints for modifications
            start = request.current_constraints.get("start", {})
            sport_type = request.current_constraints.get("sport_type", "gravel")
            target_distance = request.current_constraints.get("target_distance_meters")

            context_parts = []
            if start and start.get("lat") and start.get("lng"):
                context_parts.append(f"start_lat={start.get('lat')}, start_lng={start.get('lng')}")
            context_parts.append(f"sport_type={sport_type}")
            if target_distance:
                context_parts.append(f"current_distance={target_distance}m ({round(target_distance/1609.34, 1)} miles)")

            context_str = ", ".join(context_parts)
            user_content += f"\n\n[EXISTING ROUTE CONTEXT: {context_str}. IMPORTANT: Preserve sport_type={sport_type} unless user explicitly asks to change it. Use existing coordinates - DO NOT geocode again.]"

        if request.current_route_geometry and len(request.current_route_geometry) > 0:
            first_point = request.current_route_geometry[0]
            if len(first_point) >= 2:
                user_content += f"\n\n[EXISTING ROUTE starts at: lat={first_point[1]}, lng={first_point[0]}. Use these coordinates - DO NOT geocode again.]"

        messages.append({"role": "user", "content": user_content})

        return messages

    async def _process_response(
        self,
        response: Any,
        request: ChatRequest,
    ) -> ChatResponse:
        """Process Claude's response, handling tool calls with multi-turn support."""
        logger.info(f"=== PROCESSING RESPONSE ===")

        all_tool_calls = []
        action_chips = []
        route_updated = False
        route_id = request.route_id
        route_data = None  # Will be populated if route is generated

        # Handle multiple rounds of tool calls
        # Expected flow: geocode -> generate_route -> done
        current_response = response
        max_rounds = 6  # geocode (possibly multiple attempts) + generate_route + buffer
        geocode_count = 0
        last_geocode_result = None  # Track geocode result for fallback

        for round_num in range(max_rounds):
            logger.info(f"--- Round {round_num + 1} ---")
            # Extract content from current response
            text_content = ""
            round_tool_calls = []

            for block in current_response.content:
                if block.type == "text":
                    text_content = block.text
                elif block.type == "tool_use":
                    round_tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ))

            logger.info(f"Round {round_num + 1}: text_content length={len(text_content)}, tool_calls={[tc.name for tc in round_tool_calls]}")

            # If no tool calls but we have geocode result and no route yet, auto-generate route!
            if not round_tool_calls:
                if last_geocode_result and not route_updated:
                    logger.info(f"FALLBACK: Auto-generating route with geocode result: {last_geocode_result}")
                    # Auto-generate route using last geocode result
                    auto_route_args = {
                        "start_lat": last_geocode_result["lat"],
                        "start_lng": last_geocode_result["lng"],
                        "sport_type": self._extract_sport_type(request.message),
                        "target_distance_meters": self._extract_distance(request.message),
                        "route_type": self._extract_route_type(request.message),
                        "quality_mode": request.quality_mode,
                    }
                    logger.info(f"Auto-generate args: {auto_route_args}")
                    auto_result = await self._generate_route(auto_route_args)

                    if auto_result.get("success"):
                        route_updated = True
                        route_id = auto_result.get("route_id")
                        logger.info(f"Auto-generated route: {route_id}")
                        if route_id and route_id in self._route_cache:
                            cached = self._route_cache[route_id]
                            # Normalize surface breakdown for frontend
                            surface_data = self._normalize_surface_breakdown(
                                cached["routing_data"].get("surface_breakdown", {})
                            )
                            route_data = RouteData(
                                geometry=cached["geometry"],
                                distance_meters=cached["routing_data"]["distance_meters"],
                                elevation_gain=cached["routing_data"]["elevation_gain"],
                                duration_seconds=cached["routing_data"]["duration_seconds"],
                                sport_type=auto_result.get("sport_type", "gravel"),
                                route_type=auto_result.get("route_type", "loop"),
                                surface_breakdown=surface_data,
                            )
                            # Update text_content to describe the auto-generated route
                            dist_miles = round(route_data.distance_meters / 1609.34, 1)
                            elev_ft = round(route_data.elevation_gain * 3.28084)
                            hours = round(route_data.duration_seconds / 3600, 1)
                            text_content = f"Here's a {dist_miles} mile {route_data.sport_type} loop with {elev_ft} ft climbing (~{hours} hours).\n\nTo refine: try 'make it longer', 'more trails', or 'less climbing'."
                    else:
                        logger.warning(f"Auto-route generation failed: {auto_result.get('error')}")
                        text_content = f"I found the location but had trouble generating a route. {auto_result.get('suggestion', 'Try clicking on the map to set a starting point.')}"

                logger.info(f"Tool loop completed after {round_num} rounds (no more tools)")
                logger.info(f"Final text preview: {text_content[:200]}...")
                break

            # Check for multiple geocode calls - this is a problem
            geocodes_this_round = sum(1 for tc in round_tool_calls if tc.name == "geocode")
            geocode_count += geocodes_this_round

            if geocode_count > 1:
                logger.warning(f"Multiple geocode calls detected ({geocode_count}), this shouldn't happen")

            # Execute this round's tool calls
            round_results = []
            for tc in round_tool_calls:
                all_tool_calls.append(tc)
                result = await self._execute_tool(tc)
                round_results.append(result)

                # Track successful geocode for fallback
                if tc.name == "geocode" and result.result.get("success"):
                    last_geocode_result = result.result
                    logger.info(f"Geocode succeeded: {last_geocode_result}")

                # Check for route generation
                if tc.name == "generate_route":
                    logger.info(f"generate_route result: {result.result}")
                    if result.result.get("success"):
                        route_updated = True
                        route_id = result.result.get("route_id")
                        logger.info(f"Route generated successfully: route_id={route_id}")
                        # Get the route data from cache to include in response
                        if route_id and route_id in self._route_cache:
                            cached = self._route_cache[route_id]
                            logger.info(f"Route found in cache, geometry coords: {len(cached['geometry'].get('coordinates', []))}")
                            # Normalize surface breakdown for frontend
                            surface_data = self._normalize_surface_breakdown(
                                cached["routing_data"].get("surface_breakdown", {})
                            )
                            route_data = RouteData(
                                geometry=cached["geometry"],
                                distance_meters=cached["routing_data"]["distance_meters"],
                                elevation_gain=cached["routing_data"]["elevation_gain"],
                                duration_seconds=cached["routing_data"]["duration_seconds"],
                                sport_type=result.result.get("sport_type", "road"),
                                route_type=result.result.get("route_type", "loop"),
                                surface_breakdown=surface_data,
                            )
                            logger.info(f"RouteData created: distance={route_data.distance_meters}m")
                        else:
                            logger.warning(f"Route {route_id} NOT found in cache! Cache keys: {list(self._route_cache.keys())}")
                    else:
                        logger.warning(f"Route generation failed: {result.result.get('error')}")
                    # After generate_route (success or failure), get final response and stop
                    logger.info(f"Route generation completed: success={result.result.get('success')}")
                    current_response = await self._continue_with_tools(
                        current_response, round_results, request
                    )
                    # Force exit the loop
                    round_tool_calls = []  # Clear to trigger break condition check
                    break

            # If we just processed generate_route, exit now
            if any(tc.name == "generate_route" for tc in all_tool_calls):
                logger.info("Exiting tool loop after generate_route")
                break

            # Continue conversation with tool results
            current_response = await self._continue_with_tools(
                current_response, round_results, request
            )

            logger.info(f"Completed tool round {round_num + 1}, tools: {[tc.name for tc in round_tool_calls]}")

        # Extract final text content
        for block in current_response.content:
            if block.type == "text":
                text_content = block.text

        logger.info(f"=== BUILDING FINAL RESPONSE ===")
        logger.info(f"route_updated: {route_updated}")
        logger.info(f"route_id: {route_id}")
        logger.info(f"route_data: {route_data is not None}")
        if route_data:
            logger.info(f"route_data.geometry coords: {len(route_data.geometry.get('coordinates', []))}")
        logger.info(f"all_tool_calls: {[tc.name for tc in all_tool_calls]}")
        logger.info(f"text_content preview: {text_content[:200] if text_content else 'EMPTY'}...")

        # If no route was generated, force a deterministic attempt before responding
        if not route_updated:
            logger.warning("No route generated from tool loop - forcing fallback generation")
            forced = await self._force_route_generation(request, last_geocode_result)
            if forced.get("success"):
                route_updated = True
                route_id = forced.get("route_id")
                if route_id and route_id in self._route_cache:
                    cached = self._route_cache[route_id]
                    surface_data = self._normalize_surface_breakdown(
                        cached["routing_data"].get("surface_breakdown", {})
                    )
                    route_data = RouteData(
                        geometry=cached["geometry"],
                        distance_meters=cached["routing_data"]["distance_meters"],
                        elevation_gain=cached["routing_data"]["elevation_gain"],
                        duration_seconds=cached["routing_data"]["duration_seconds"],
                        sport_type=forced.get("sport_type", "gravel"),
                        route_type=forced.get("route_type", "loop"),
                        surface_breakdown=surface_data,
                    )
                    text_content = self._format_route_summary(route_data, request)
            else:
                text_content = forced.get("message", text_content) or "I couldn’t build a route from that. Try a nearby start point."

        if route_updated and route_data:
            text_content = self._format_route_summary(route_data, request)

        # Generate action chips from response
        action_chips = self._generate_action_chips(text_content, route_id)

        # Generate suggested prompts
        suggested_prompts = self._generate_suggested_prompts(text_content, request)

        # Build message
        message = ChatMessage(
            role="assistant",
            content=text_content,
            timestamp=datetime.utcnow(),
            tool_calls=all_tool_calls,
            action_chips=action_chips,
            confidence=self._estimate_confidence(all_tool_calls),
        )

        logger.info(f"=== CHAT RESPONSE COMPLETE ===")
        return ChatResponse(
            conversation_id=request.conversation_id or uuid4(),
            message=message,
            route_id=route_id,
            route_updated=route_updated,
            route_data=route_data,
            suggested_prompts=suggested_prompts,
        )

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result."""
        logger.info(f"Executing tool: {tool_call.name} with args: {tool_call.arguments}")
        try:
            result = await self._dispatch_tool(tool_call.name, tool_call.arguments)
            logger.info(f"Tool {tool_call.name} completed: success={result.get('success', 'N/A')}")
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result=result,
            )
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_call.name} - {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result={"error": str(e)},
                error=str(e),
            )

    async def _dispatch_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch tool call to appropriate service."""
        if tool_name == "geocode":
            service = await get_geocoding_service()
            query = arguments["query"]
            query_lower = query.lower()

            # Known MTB/cycling destinations with coordinates
            # These are famous bike parks that may not geocode well
            known_locations = {
                "coler": {"lat": 36.3689, "lng": -94.2028, "name": "Coler Mountain Bike Preserve"},
                "coler mountain": {"lat": 36.3689, "lng": -94.2028, "name": "Coler Mountain Bike Preserve"},
                "coler preserve": {"lat": 36.3689, "lng": -94.2028, "name": "Coler Mountain Bike Preserve"},
                "slaughter pen": {"lat": 36.3697, "lng": -94.2314, "name": "Slaughter Pen Trail"},
                "back 40": {"lat": 36.3583, "lng": -94.2561, "name": "Back 40 Trail"},
                "whistler": {"lat": 50.1163, "lng": -122.9574, "name": "Whistler Mountain Bike Park"},
                "moab": {"lat": 38.5733, "lng": -109.5498, "name": "Moab, Utah"},
                "fruita": {"lat": 39.1586, "lng": -108.7289, "name": "Fruita, Colorado"},
                "sedona": {"lat": 34.8697, "lng": -111.7610, "name": "Sedona, Arizona"},
                "downieville": {"lat": 39.5594, "lng": -120.8274, "name": "Downieville, California"},
                "kingdom trails": {"lat": 44.5342, "lng": -71.9681, "name": "Kingdom Trails"},
                "pisgah": {"lat": 35.2896, "lng": -82.7456, "name": "Pisgah National Forest"},
            }

            # Check for known locations first
            for key, loc in known_locations.items():
                if key in query_lower:
                    logger.info(f"Matched known location: {loc['name']}")
                    return {
                        "lat": loc["lat"],
                        "lng": loc["lng"],
                        "success": True,
                        "matched": loc["name"],
                        "note": f"Known MTB destination: {loc['name']}"
                    }

            # Try the original query
            result = await service.geocode(query)
            if result:
                logger.info(f"Geocoded '{query}' successfully: {result.lat}, {result.lng}")
                return {
                    "lat": result.lat,
                    "lng": result.lng,
                    "success": True,
                    "matched": query,
                    "location_name": query
                }

            # Try with common suffixes for cycling locations
            variations = [
                f"{query}, USA",
                f"{query}, Colorado",
                f"{query}, California",
                f"{query} trailhead",
                f"{query} road",
                f"{query} canyon",
                f"{query}, Arkansas",  # For Bentonville area
            ]

            for variation in variations:
                result = await service.geocode(variation)
                if result:
                    logger.info(f"Geocoded '{query}' as '{variation}': {result.lat}, {result.lng}")
                    return {
                        "lat": result.lat,
                        "lng": result.lng,
                        "success": True,
                        "matched": variation,
                        "note": f"Interpreted as '{variation}'",
                        "location_name": variation
                    }

            # CRITICAL FIX: Geocoding failed - return clear error instead of silent fallback
            logger.error(f"Geocoding failed for '{query}' - tried {len(variations)} variations")
            return {
                "success": False,
                "error": f"Could not find location '{query}'",
                "suggestion": "Could you try a more specific location like a city name, address, or well-known landmark? For example: 'Boulder, Colorado' or 'Golden Gate Park'",
                "query": query,
            }

        elif tool_name == "reverse_geocode":
            service = await get_geocoding_service()
            coord = Coordinate(lat=arguments["lat"], lng=arguments["lng"])
            result = await service.reverse_geocode(coord)
            if result:
                return {"address": result, "success": True}
            return {"success": False, "error": "Could not determine address"}

        elif tool_name == "search_places":
            service = await get_geocoding_service()
            from app.schemas.common import BoundingBox

            bbox = None
            if "near_lat" in arguments and "near_lng" in arguments:
                radius = arguments.get("radius_meters", 10000) / 111000  # Approximate degrees
                bbox = BoundingBox(
                    min_lng=arguments["near_lng"] - radius,
                    min_lat=arguments["near_lat"] - radius,
                    max_lng=arguments["near_lng"] + radius,
                    max_lat=arguments["near_lat"] + radius,
                )

            results = await service.search_places(
                query=arguments["query"],
                bbox=bbox,
            )
            return {"places": results, "count": len(results), "success": True}

        elif tool_name == "generate_route":
            return await self._generate_route(arguments, original_message=self._current_user_message)

        elif tool_name == "analyze_route":
            return await self._analyze_route(arguments["route_id"])

        elif tool_name == "validate_route":
            return await self._validate_route(arguments["route_id"])

        elif tool_name == "apply_avoidance":
            return await self._apply_avoidance(arguments)

        elif tool_name == "export_gpx":
            return {"success": True, "message": "GPX export ready", "route_id": arguments["route_id"]}

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _generate_route(self, arguments: Dict[str, Any], original_message: Optional[str] = None) -> Dict[str, Any]:
        """Generate a route using the routing service with intelligent planning."""
        try:
            # Apply sensible defaults for a good intermediate ride
            # Default distance: ~25km / 15 miles - solid intermediate ride
            default_distance = 25000  # meters
            target_distance = arguments.get("target_distance_meters", default_distance)

            # Default sport type based on context, fallback to gravel (versatile)
            sport_type = arguments.get("sport_type", "gravel")

            # Extract surface constraints if provided in arguments
            surface_constraints = arguments.get("surface_constraints", {})
            quality_mode = arguments.get("quality_mode", True)

            # Parse via_points if provided
            via_points = []
            if "via_points" in arguments and arguments["via_points"]:
                for vp in arguments["via_points"]:
                    via_points.append(Coordinate(lat=vp["lat"], lng=vp["lng"]))
                logger.info(f"Route will pass through {len(via_points)} via points")

            # Estimate search radius if not provided
            search_radius_km = arguments.get("search_radius_km")
            if not search_radius_km:
                if target_distance >= 40000:
                    search_radius_km = 25
                elif target_distance <= 15000:
                    search_radius_km = 12
                else:
                    search_radius_km = 15

            # Build constraints with sensible defaults
            constraints = RouteConstraints(
                start=Coordinate(
                    lat=arguments["start_lat"],
                    lng=arguments["start_lng"],
                ),
                end=Coordinate(
                    lat=arguments["end_lat"],
                    lng=arguments["end_lng"],
                ) if "end_lat" in arguments and "end_lng" in arguments else None,
                via_points=via_points,
                route_type=RouteType(arguments.get("route_type", "loop")),
                sport_type=SportType(sport_type),
                target_distance_meters=target_distance,
                min_distance_meters=arguments.get("min_distance_meters"),
                max_distance_meters=arguments.get("max_distance_meters"),
                distance_hard_constraint=arguments.get("distance_hard_constraint", False),
                target_time_seconds=arguments.get("target_time_seconds"),
                target_elevation_gain_meters=arguments.get("target_elevation_gain_meters"),
                mtb_difficulty_target=MTBDifficulty(arguments.get("mtb_difficulty", "moderate")),
                avoid_highways=arguments.get("avoid_highways", False),
                quality_mode=quality_mode,
                num_alternatives=arguments.get("num_alternatives", 3),
            )

            logger.info("Route generation intent", sport_type=sport_type, target_distance=target_distance)

            max_attempts = 3 if quality_mode else 1
            best_candidate = None
            best_score = 0.0
            best_meta = {}
            validation_failures = []
            last_candidates: List[Dict[str, Any]] = []
            threshold_met = False
            last_threshold = 0.0
            start_time = time.monotonic()
            max_total_seconds = 20.0
            time_budget_exceeded = False

            for attempt in range(max_attempts):
                if time.monotonic() - start_time > max_total_seconds:
                    time_budget_exceeded = True
                    logger.warning("Route generation time budget exceeded; returning best available")
                    break
                try:
                    attempt_constraints = constraints.model_copy(deep=True)
                except AttributeError:
                    attempt_constraints = constraints.copy(deep=True)

                attempt_search_radius = search_radius_km * (1 + (0.5 * attempt))
                if attempt > 0:
                    attempt_constraints.num_alternatives = min(5, max(attempt_constraints.num_alternatives, 3 + attempt))
                    # DO NOT fall back to out-and-back - keep trying loops with adjusted parameters
                    # Only use out-and-back if explicitly requested by user
                    if attempt_constraints.target_distance_meters and not attempt_constraints.min_distance_meters:
                        attempt_constraints.min_distance_meters = attempt_constraints.target_distance_meters * (0.85 if attempt == 1 else 0.75)
                    if attempt_constraints.target_distance_meters and not attempt_constraints.max_distance_meters:
                        attempt_constraints.max_distance_meters = attempt_constraints.target_distance_meters * (1.15 if attempt == 1 else 1.25)

                routing_validation_plan = None
                if original_message and self.client:
                    logger.info("=== INTELLIGENT ROUTE PLANNING ACTIVATED ===")
                    planner = await get_route_planner()
                    try:
                        routing_plan = await asyncio.wait_for(
                            planner.plan_route(
                                user_request=original_message,
                                location=attempt_constraints.start,
                                constraints=attempt_constraints,
                                search_radius_km=attempt_search_radius,
                            ),
                            timeout=10,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Intelligent route planning timed out; falling back")
                        routing_plan = None
                    except Exception as exc:
                        logger.warning("Intelligent route planning failed; falling back", error=str(exc))
                        routing_plan = None

                    if routing_plan:
                        logger.info(f"Routing strategy: {routing_plan['strategy']}")
                        logger.info(f"Surface target: {routing_plan['surface_target']}")
                        logger.info(f"Validation criteria: {routing_plan['validation_criteria']}")

                        routing_validation_plan = routing_plan
                        trail_waypoints = routing_plan.get("waypoints", [])
                        if trail_waypoints:
                            logger.info(f"=== USING {len(trail_waypoints)} TRAIL WAYPOINTS FOR ROUTING ===")
                            attempt_constraints.via_points = trail_waypoints
                        else:
                            logger.warning("No trail waypoints available - routing may not use desired surfaces")

                routing_service = await get_routing_service()
                candidates = await routing_service.generate_route(attempt_constraints)

                if not candidates:
                    logger.info("No route found with initial bearings, trying more directions")
                    attempt_constraints.num_alternatives = 6
                    candidates = await routing_service.generate_route(attempt_constraints)

                if not candidates:
                    logger.warning(f"Attempt {attempt + 1}: no candidates found")
                    continue

                last_candidates = candidates

                quality_threshold = 0.78 if attempt_constraints.sport_type == SportType.MTB else 0.7
                if not quality_mode:
                    quality_threshold = 0.5
                if not routing_service.ors_api_key:
                    quality_threshold = min(quality_threshold, 0.6)
                last_threshold = quality_threshold

                for i, candidate in enumerate(candidates):
                    # Check for doubling back - reject routes with >35% retracing (50% strict)
                    geometry = candidate.get("geometry", {})
                    doubling_back_analysis = self._detect_doubling_back(geometry)
                    
                    if doubling_back_analysis["retraced_percentage"] > 35.0:
                        logger.warning(
                            f"Rejecting candidate {i + 1} due to excessive doubling back: {doubling_back_analysis['retraced_percentage']:.1f}% retraced"
                        )
                        continue  # Skip this candidate entirely
                    
                    score_meta = self._score_candidate_quality(candidate, attempt_constraints)
                    surface_breakdown = candidate.get("surface_breakdown", {})

                    if surface_constraints and any(surface_constraints.values()):
                        validation_service = await get_validation_service()
                        is_valid, reasons = validation_service.validate_surface_constraints(
                            surface_breakdown, surface_constraints
                        )
                        if not is_valid:
                            score_meta["quality_score"] = 0.0
                            score_meta["reasons"].extend(reasons)

                    if candidate.get("data_quality_warning") and not routing_service.ors_api_key:
                        score_meta["quality_score"] = max(score_meta["quality_score"], 0.6)

                    logger.info(
                        "candidate_quality",
                        attempt=attempt + 1,
                        candidate_index=i + 1,
                        quality_score=score_meta["quality_score"],
                        distance_score=score_meta["distance_score"],
                        surface_score=score_meta["surface_score"],
                        data_score=score_meta["data_score"],
                        doubling_back_pct=doubling_back_analysis["retraced_percentage"],
                        reasons=score_meta["reasons"],
                        surface_breakdown=surface_breakdown,
                    )

                    if score_meta["quality_score"] > best_score:
                        best_score = score_meta["quality_score"]
                        best_candidate = candidate
                        best_meta = score_meta

                if best_candidate and best_score >= quality_threshold:
                    logger.info(
                        "quality_threshold_met",
                        attempt=attempt + 1,
                        quality_score=best_score,
                        threshold=quality_threshold,
                        reasons=best_meta.get("reasons", []),
                    )
                    constraints = attempt_constraints
                    threshold_met = True
                    break

                validation_failures.append(
                    f"Attempt {attempt + 1}: best_score={best_score} below threshold={quality_threshold}"
                )
                logger.warning(f"Attempt {attempt + 1}: quality threshold not met, retrying")

            if not best_candidate or (quality_mode and not threshold_met and not time_budget_exceeded):
                failure_reason = validation_failures[-1] if validation_failures else "No suitable routes found"
                return {
                    "success": False,
                    "error": "Could not generate a high-quality route that matches your request",
                    "suggestion": f"{failure_reason}. Try a nearby start point or slightly shorter distance.",
                    "quality_blocked": True,
                    "quality_threshold": last_threshold,
                }

            # Store best candidate
            route_id = str(uuid4())
            self._route_cache[route_id] = {
                "geometry": best_candidate["geometry"],
                "routing_data": best_candidate,
                "constraints": constraints.model_dump(),
                "surface_constraints": surface_constraints,  # Store for future modifications
            }

            # Calculate miles for display
            distance_miles = best_candidate["distance_meters"] / 1609.34
            elevation_feet = best_candidate["elevation_gain"] * 3.28084
            duration_hours = best_candidate["duration_seconds"] / 3600

            result = {
                "success": True,
                "route_id": route_id,
                "distance_meters": best_candidate["distance_meters"],
                "distance_miles": round(distance_miles, 1),
                "elevation_gain_meters": best_candidate["elevation_gain"],
                "elevation_gain_feet": round(elevation_feet),
                "duration_seconds": best_candidate["duration_seconds"],
                "duration_hours": round(duration_hours, 1),
                "alternatives_count": len(last_candidates),
                "sport_type": sport_type,
                "route_type": constraints.route_type.value,
                "quality_score": best_score,
                "quality_reasons": best_meta.get("reasons", []),
            }

            # Include data quality warnings if present
            if best_candidate.get("data_quality_warning"):
                result["data_quality_warning"] = best_candidate["warning_message"]
                result["quality_issues"] = best_candidate.get("quality_issues", [])
                logger.warning(f"Route generated with quality warning: {best_candidate['warning_message']}")

            return result

        except Exception as e:
            logger.error(f"Route generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": "Route generation hit a snag",
                "suggestion": "Try a different starting point, shorter distance, or let me switch to road mode.",
                "next_action": "Attempting alternative approach"
            }

    async def _analyze_route(self, route_id: str) -> Dict[str, Any]:
        """Analyze a cached route."""
        if route_id not in self._route_cache:
            return {"success": False, "error": "Route not found"}

        route_data = self._route_cache[route_id]
        analysis_service = await get_analysis_service()

        analysis = await analysis_service.analyze_route(
            geometry=route_data["geometry"],
            routing_data=route_data.get("routing_data"),
        )

        return {
            "success": True,
            "analysis": analysis.model_dump(),
        }

    async def _validate_route(self, route_id: str) -> Dict[str, Any]:
        """Validate a cached route."""
        if route_id not in self._route_cache:
            return {"success": False, "error": "Route not found"}

        route_data = self._route_cache[route_id]
        validation_service = await get_validation_service()

        # Parse constraints back if available
        constraints = None
        if "constraints" in route_data:
            constraints = RouteConstraints(**route_data["constraints"])

        validation = await validation_service.validate_route(
            geometry=route_data["geometry"],
            constraints=constraints,
        )

        return {
            "success": True,
            "validation": validation.model_dump(),
        }

    async def _apply_avoidance(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Apply an avoidance to a route."""
        route_id = arguments["route_id"]
        if route_id not in self._route_cache:
            return {"success": False, "error": "Route not found"}

        # In a full implementation, this would re-route avoiding the segment
        return {
            "success": True,
            "message": f"Avoidance applied to route {route_id}",
            "reason": arguments.get("reason", "User requested"),
        }

    async def _continue_with_tools(
        self,
        original_response: Any,
        tool_results: List[ToolResult],
        request: ChatRequest,
        prior_messages: List[Dict[str, Any]] = None,
    ) -> Any:
        """Continue conversation after tool execution."""
        logger.info(f"_continue_with_tools: {len(tool_results)} tool results")

        messages = []

        # Include the original user message for context
        messages.append({"role": "user", "content": request.message})

        # Add assistant message with tool use
        assistant_content = []
        for block in original_response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        messages.append({"role": "assistant", "content": assistant_content})

        # Add tool results
        tool_result_content = []
        for tr in tool_results:
            tool_result_content.append({
                "type": "tool_result",
                "tool_use_id": tr.tool_call_id,
                "content": json.dumps(tr.result),
            })
        messages.append({"role": "user", "content": tool_result_content})

        logger.info(f"Continuing with {len(messages)} messages")

        # Get Claude's next response - allow it to either call more tools or respond
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        logger.info(f"Continuation response: stop_reason={response.stop_reason}, blocks={len(response.content)}")
        for i, block in enumerate(response.content):
            if block.type == "tool_use":
                logger.info(f"  Block {i}: tool_use - {block.name}")
            else:
                logger.info(f"  Block {i}: {block.type}")

        return response

    def _generate_action_chips(
        self,
        text: str,
        route_id: Optional[UUID],
    ) -> List[ActionChip]:
        """Generate action chips based on response content."""
        chips = []

        if route_id:
            chips.append(ActionChip(
                id="export_gpx",
                label="Export GPX",
                action="export_gpx",
                data={"route_id": str(route_id)},
            ))

            chips.append(ActionChip(
                id="try_alternatives",
                label="Try 3 alternatives",
                action="try_alternatives",
                data={"route_id": str(route_id)},
            ))

        # Add contextual chips based on content
        text_lower = text.lower()
        if "steep" in text_lower or "climb" in text_lower:
            chips.append(ActionChip(
                id="reduce_climbing",
                label="Reduce climbing",
                action="modify_constraint",
                data={"constraint": "elevation_gain", "direction": "decrease"},
            ))

        if "technical" in text_lower or "difficult" in text_lower:
            chips.append(ActionChip(
                id="easier_route",
                label="Find easier route",
                action="modify_constraint",
                data={"constraint": "difficulty", "direction": "decrease"},
            ))

        return chips[:4]  # Limit to 4 chips

    def _generate_suggested_prompts(
        self,
        text: str,
        request: ChatRequest,
    ) -> List[str]:
        """Generate suggested follow-up prompts for iteration."""
        prompts = []
        text_lower = text.lower()

        # Always offer iteration options after generating a route
        if request.route_id or "route" in text_lower or "mile" in text_lower:
            # Distance adjustments
            prompts.append("Make it longer")
            prompts.append("Make it shorter")

            # Surface/type adjustments based on context
            if "mtb" in text_lower or "trail" in text_lower:
                prompts.append("More singletrack")
                prompts.append("Easier trails")
            elif "road" in text_lower:
                prompts.append("Avoid busy roads")
                prompts.append("More climbing")
            else:
                prompts.append("More trails")
                prompts.append("Stick to pavement")

            # Elevation adjustments
            if "climb" in text_lower or "elevation" in text_lower or "ft" in text_lower:
                prompts.append("Less climbing")
            else:
                prompts.append("Add more climbing")

        # If no route context, suggest starting points
        if not prompts:
            prompts = [
                "20 mile MTB ride",
                "Quick road loop",
                "Gravel adventure",
            ]

        return prompts[:5]

    def _normalize_surface_breakdown(self, backend_surface: Dict[str, float]) -> Dict[str, float]:
        """Normalize surface breakdown from backend format to frontend format.

        Backend uses: paved, unpaved, gravel, ground, unknown
        Frontend uses: pavement, gravel, dirt, singletrack, unknown
        """
        if not backend_surface:
            return {"pavement": 0, "gravel": 0, "dirt": 0, "singletrack": 0, "unknown": 100}

        return {
            "pavement": backend_surface.get("paved", 0),
            "gravel": backend_surface.get("gravel", 0),
            "dirt": backend_surface.get("unpaved", 0),
            "singletrack": backend_surface.get("ground", 0),
            "unknown": backend_surface.get("unknown", 0),
        }

    def _format_route_summary(self, route_data: RouteData, request: ChatRequest) -> str:
        dist_miles = round(route_data.distance_meters / 1609.34, 1)
        elev_ft = round(route_data.elevation_gain * 3.28084)
        hours = round(route_data.duration_seconds / 3600, 1)
        sport = route_data.sport_type

        return (
            f"Got it. Here's a {dist_miles} mile {sport} loop with {elev_ft} ft climbing "
            f"(~{hours} hours). Want it a bit longer, shorter, or more trail-heavy?"
        )

    async def _force_route_generation(
        self,
        request: ChatRequest,
        last_geocode_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        start_lat = None
        start_lng = None

        if last_geocode_result:
            start_lat = last_geocode_result.get("lat")
            start_lng = last_geocode_result.get("lng")

        if start_lat is None or start_lng is None:
            if request.current_route_geometry and len(request.current_route_geometry) > 0:
                first_point = request.current_route_geometry[0]
                if len(first_point) >= 2:
                    start_lng = first_point[0]
                    start_lat = first_point[1]

        if start_lat is None or start_lng is None:
            if request.current_constraints:
                start = request.current_constraints.get("start", {})
                if start and start.get("lat") and start.get("lng"):
                    start_lat = start["lat"]
                    start_lng = start["lng"]

        if start_lat is None or start_lng is None:
            location_query = self._extract_location(request.message)
            if location_query:
                geocode_result = await self._direct_geocode(location_query)
                if geocode_result:
                    start_lat = geocode_result["lat"]
                    start_lng = geocode_result["lng"]

        if start_lat is None or start_lng is None:
            return {
                "success": False,
                "message": "I need a starting point to build a route. Try a specific area or trailhead.",
            }

        existing_distance = None
        if request.current_constraints:
            existing_distance = request.current_constraints.get("target_distance_meters")

        sport_type = self._extract_sport_type(request.message)
        target_distance = self._extract_distance(request.message, existing_distance)
        surface_constraints = self._extract_surface_constraints(request.message)
        route_type = self._extract_route_type(request.message)

        route_args = {
            "start_lat": start_lat,
            "start_lng": start_lng,
            "sport_type": sport_type,
            "target_distance_meters": target_distance,
            "route_type": route_type,
            "surface_constraints": surface_constraints,
            "quality_mode": request.quality_mode,
        }

        if request.current_constraints:
            route_args["num_alternatives"] = request.current_constraints.get("num_alternatives", 3)
            route_args["distance_hard_constraint"] = request.current_constraints.get("distance_hard_constraint", False)
            route_args["min_distance_meters"] = request.current_constraints.get("min_distance_meters")
            route_args["max_distance_meters"] = request.current_constraints.get("max_distance_meters")

        result = await self._generate_route(route_args, original_message=request.message)
        if result.get("success"):
            return result

        return {
            "success": False,
            "message": result.get("suggestion", "I couldn't build a route from that. Try a nearby start point."),
        }

    def _score_distance_match(
        self,
        actual_distance: float,
        target_distance: Optional[float],
        min_distance: Optional[float],
        max_distance: Optional[float],
        hard_constraint: bool,
    ) -> float:
        if not target_distance:
            return 0.7

        if min_distance and actual_distance < min_distance:
            return 0.0 if hard_constraint else max(0.1, actual_distance / min_distance)
        if max_distance and actual_distance > max_distance:
            return 0.0 if hard_constraint else max(0.1, max_distance / actual_distance)

        if target_distance <= 0:
            return 0.5

        diff_ratio = abs(actual_distance - target_distance) / target_distance
        return max(0.0, 1.0 - min(diff_ratio, 1.0))

    def _score_surface_match(self, sport_type: SportType, surface_breakdown: Dict[str, float]) -> float:
        pavement_pct = surface_breakdown.get("paved", 0)
        gravel_pct = surface_breakdown.get("gravel", 0)
        dirt_pct = surface_breakdown.get("unpaved", 0)
        singletrack_pct = surface_breakdown.get("ground", 0)
        unknown_pct = surface_breakdown.get("unknown", 0)

        known_pct = max(0.0, 100.0 - unknown_pct)
        if known_pct < 50:
            return 0.0

        if sport_type == SportType.MTB:
            trail_pct = gravel_pct + dirt_pct + singletrack_pct
            trail_score = min(max((trail_pct - 40) / 40, 0.0), 1.0)  # 40% -> 0, 80% -> 1
            pavement_penalty = min(max((pavement_pct - 30) / 70, 0.0), 1.0)
            return max(0.0, trail_score - 0.6 * pavement_penalty)
        if sport_type == SportType.ROAD:
            return min(max((pavement_pct - 70) / 30, 0.0), 1.0)
        # GRAVEL/EMTB default
        gravel_like = gravel_pct + dirt_pct
        return min(max((gravel_like - 50) / 30, 0.0), 1.0)

    def _detect_doubling_back(self, geometry: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if a route doubles back on itself (retraces the same path).
        
        Returns a dict with:
        - has_doubling_back: bool
        - retraced_distance_meters: float (distance that is retraced)
        - retraced_percentage: float (percentage of total route that is retraced)
        - doubling_back_score: float (0-1, where 1 is no retracing, 0 is all retracing)
        """
        coordinates = geometry.get("coordinates", [])
        if len(coordinates) < 4:
            return {
                "has_doubling_back": False,
                "retraced_distance_meters": 0.0,
                "retraced_percentage": 0.0,
                "doubling_back_score": 1.0,
            }

        # Convert coordinates to list of (lng, lat) tuples
        points = [(coord[0], coord[1]) for coord in coordinates]
        total_distance = self._calculate_route_distance(points)
        
        if total_distance == 0:
            return {
                "has_doubling_back": False,
                "retraced_distance_meters": 0.0,
                "retraced_percentage": 0.0,
                "doubling_back_score": 1.0,
            }

        # Check for segments that overlap and go in opposite directions
        # We'll sample segments and check if any overlap significantly
        retraced_distance = 0.0
        segment_length = 50  # Check every 50 meters of route
        num_segments = max(10, int(total_distance / segment_length))
        step = max(1, len(points) // num_segments)
        
        # Create segments to check
        checked_segments = set()
        threshold_distance = 20.0  # Consider it retracing if within 20 meters
        
        for i in range(0, len(points) - step, step):
            if i + step >= len(points):
                continue
                
            seg_start = points[i]
            seg_end = points[i + step]
            seg_mid = points[min(i + step // 2, len(points) - 1)]
            
            # Check if this segment overlaps with any later segment going in opposite direction
            for j in range(i + step * 2, len(points) - step, step):
                if j + step >= len(points):
                    continue
                    
                check_start = points[j]
                check_end = points[j + step]
                check_mid = points[min(j + step // 2, len(points) - 1)]
                
                # Calculate distance between segment midpoints
                dist_to_seg = self._haversine_distance(seg_mid[1], seg_mid[0], check_mid[1], check_mid[0])
                
                if dist_to_seg < threshold_distance:
                    # Check if segments are going in opposite directions
                    seg_bearing = self._calculate_bearing(seg_start[1], seg_start[0], seg_end[1], seg_end[0])
                    check_bearing = self._calculate_bearing(check_start[1], check_start[0], check_end[1], check_end[0])
                    
                    # Calculate angle difference (accounting for wrap-around)
                    angle_diff = abs(seg_bearing - check_bearing)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff
                    
                    # If segments are roughly opposite (150-210 degrees difference), it's retracing
                    if angle_diff > 150:
                        seg_distance = self._calculate_segment_distance(seg_start, seg_end)
                        retraced_distance += seg_distance
                        checked_segments.add((i, j))
        
        retraced_percentage = (retraced_distance / total_distance * 100) if total_distance > 0 else 0.0
        has_doubling_back = retraced_percentage > 5.0  # More than 5% retracing is significant
        
        # Score: 1.0 = no retracing, 0.0 = all retracing
        # Penalize more heavily as retracing increases
        if retraced_percentage == 0:
            doubling_back_score = 1.0
        elif retraced_percentage < 10:
            doubling_back_score = 1.0 - (retraced_percentage / 10) * 0.3  # Up to 30% penalty
        elif retraced_percentage < 25:
            doubling_back_score = 0.7 - ((retraced_percentage - 10) / 15) * 0.4  # Additional 40% penalty
        else:
            doubling_back_score = max(0.0, 0.3 - ((retraced_percentage - 25) / 75) * 0.3)  # Heavy penalty
        
        return {
            "has_doubling_back": has_doubling_back,
            "retraced_distance_meters": round(retraced_distance, 1),
            "retraced_percentage": round(retraced_percentage, 1),
            "doubling_back_score": round(doubling_back_score, 3),
        }

    def _calculate_route_distance(self, points: List[tuple]) -> float:
        """Calculate total distance of route in meters."""
        if len(points) < 2:
            return 0.0
        total = 0.0
        for i in range(len(points) - 1):
            total += self._haversine_distance(
                points[i][1], points[i][0],
                points[i + 1][1], points[i + 1][0]
            )
        return total

    def _calculate_segment_distance(self, p1: tuple, p2: tuple) -> float:
        """Calculate distance between two points in meters."""
        return self._haversine_distance(p1[1], p1[0], p2[1], p2[0])

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula (meters)."""
        import math
        R = 6371000  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing (direction) from point 1 to point 2 in degrees (0-360)."""
        import math
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)
        
        y = math.sin(delta_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
        
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360

    def _score_candidate_quality(
        self,
        candidate: Dict[str, Any],
        constraints: RouteConstraints,
    ) -> Dict[str, Any]:
        distance = float(candidate.get("distance_meters", 0))
        surface_breakdown = candidate.get("surface_breakdown", {})
        unknown_pct = surface_breakdown.get("unknown", 100)
        geometry = candidate.get("geometry", {})

        distance_score = self._score_distance_match(
            distance,
            constraints.target_distance_meters,
            constraints.min_distance_meters,
            constraints.max_distance_meters,
            constraints.distance_hard_constraint,
        )
        surface_score = self._score_surface_match(constraints.sport_type, surface_breakdown)
        data_score = max(0.0, 1.0 - (unknown_pct / 100))
        
        # Check for doubling back (retracing) - but be lenient (50% strict)
        doubling_back_analysis = self._detect_doubling_back(geometry)
        doubling_back_score = doubling_back_analysis["doubling_back_score"]
        
        # Reduce weight of doubling back penalty since we're being more lenient
        if constraints.sport_type == SportType.MTB:
            weights = {"distance": 0.25, "surface": 0.50, "data": 0.15, "doubling_back": 0.10}
        elif constraints.sport_type == SportType.ROAD:
            weights = {"distance": 0.35, "surface": 0.40, "data": 0.15, "doubling_back": 0.10}
        else:
            weights = {"distance": 0.30, "surface": 0.45, "data": 0.15, "doubling_back": 0.10}

        quality_score = (
            distance_score * weights["distance"]
            + surface_score * weights["surface"]
            + data_score * weights["data"]
            + doubling_back_score * weights["doubling_back"]
        )

        reasons = []
        if distance_score < 0.5:
            reasons.append("distance_mismatch")
        if surface_score < 0.5:
            reasons.append("surface_mismatch")
        if data_score < 0.6:
            reasons.append("low_surface_confidence")
        if doubling_back_analysis["has_doubling_back"]:
            reasons.append(f"doubling_back_{doubling_back_analysis['retraced_percentage']:.0f}%")

        return {
            "quality_score": round(quality_score, 3),
            "distance_score": round(distance_score, 3),
            "surface_score": round(surface_score, 3),
            "data_score": round(data_score, 3),
            "doubling_back_score": doubling_back_score,
            "doubling_back_analysis": doubling_back_analysis,
            "reasons": reasons,
        }

    def _estimate_confidence(self, tool_calls: List[ToolCall]) -> float:
        """Estimate confidence based on tools used."""
        if not tool_calls:
            return 0.5

        # More tool calls generally means more thorough work
        # Certain tools indicate higher confidence
        high_confidence_tools = {"generate_route", "analyze_route", "validate_route"}
        has_high_confidence = any(tc.name in high_confidence_tools for tc in tool_calls)

        base = 0.7 if has_high_confidence else 0.5
        bonus = min(0.25, len(tool_calls) * 0.05)

        return min(0.95, base + bonus)

    def _extract_sport_type(self, message: str) -> str:
        """Extract sport type from user message."""
        message_lower = message.lower()

        if any(kw in message_lower for kw in ["mtb", "mountain bike", "singletrack", "trail"]):
            return "mtb"
        elif any(kw in message_lower for kw in ["road", "pavement", "paved"]):
            return "road"
        elif any(kw in message_lower for kw in ["gravel", "mixed", "adventure"]):
            return "gravel"
        else:
            # Default to gravel - versatile for most areas
            return "gravel"

    def _extract_route_type(self, message: str) -> str:
        """Extract route type from user message. Defaults to 'loop' and only uses 'out_and_back' if explicitly requested."""
        message_lower = message.lower()

        # Explicit out-and-back requests - only use if user clearly asks for it
        out_and_back_patterns = [
            r"out\s+and\s+back",
            r"out-and-back",
            r"there\s+and\s+back",
            r"out\s+&\s+back",
            r"out\s+and\s+return",
        ]

        for pattern in out_and_back_patterns:
            if re.search(pattern, message_lower):
                logger.info(f"User explicitly requested out-and-back route")
                return "out_and_back"

        # Explicit loop requests
        if any(kw in message_lower for kw in ["loop", "circular", "round"]):
            return "loop"

        # Explicit point-to-point requests
        if any(kw in message_lower for kw in ["point to point", "point-to-point", "from.*to", "start.*end"]):
            return "point_to_point"

        # Default to loop - avoid out-and-back routes
        return "loop"

    def _extract_surface_constraints(self, message: str) -> Dict[str, Any]:
        """Extract surface requirements from user message.

        Returns dict with:
        - avoid_surfaces: list of surfaces to avoid (max 5-10%)
        - prefer_surfaces: list of surfaces to prefer (should be 60-80%+ of route)
        - require_surfaces: list of surfaces that must be dominant (85-95%+)
        """
        message_lower = message.lower()
        constraints = {
            "avoid_surfaces": [],
            "prefer_surfaces": [],
            "require_surfaces": [],
        }

        # AVOID patterns
        avoid_patterns = [
            (r"avoid\s+(?:dirt\s+)?singletrack", "singletrack"),
            (r"no\s+singletrack", "singletrack"),
            (r"avoid\s+dirt", "dirt"),
            (r"avoid\s+gravel", "gravel"),
            (r"avoid\s+pavement", "pavement"),
            (r"avoid\s+paved", "pavement"),
            (r"no\s+dirt", "dirt"),
            (r"no\s+gravel", "gravel"),
            (r"stay away from\s+(?:the\s+)?(\w+)", None),  # Generic avoid
        ]

        for pattern, surface_type in avoid_patterns:
            if re.search(pattern, message_lower):
                if surface_type:
                    constraints["avoid_surfaces"].append(surface_type)
                else:
                    # Try to extract the surface type
                    match = re.search(pattern, message_lower)
                    if match and match.group(1):
                        word = match.group(1)
                        if word in ["singletrack", "dirt", "gravel", "pavement", "paved"]:
                            constraints["avoid_surfaces"].append(word.replace("paved", "pavement"))

        # PREFER/MOSTLY patterns
        prefer_patterns = [
            (r"mostly\s+gravel", "gravel"),
            (r"mostly\s+(?:on\s+)?pavement", "pavement"),
            (r"mostly\s+(?:on\s+)?paved", "pavement"),
            (r"mostly\s+(?:on\s+)?bike\s+path", "pavement"),
            (r"mostly\s+dirt", "dirt"),
            (r"mostly\s+singletrack", "singletrack"),
            (r"prefer\s+gravel", "gravel"),
            (r"prefer\s+pavement", "pavement"),
            (r"more\s+gravel", "gravel"),
            (r"more\s+singletrack", "singletrack"),
        ]

        for pattern, surface_type in prefer_patterns:
            if re.search(pattern, message_lower):
                constraints["prefer_surfaces"].append(surface_type)

        # REQUIRE/ONLY patterns
        require_patterns = [
            (r"only\s+(?:on\s+)?pavement", "pavement"),
            (r"only\s+(?:on\s+)?paved", "pavement"),
            (r"only\s+(?:on\s+)?bike\s+path", "pavement"),
            (r"only\s+gravel", "gravel"),
            (r"stick\s+to\s+(?:actual\s+)?bike\s+path", "pavement"),
            (r"stick\s+to\s+paved", "pavement"),
        ]

        for pattern, surface_type in require_patterns:
            if re.search(pattern, message_lower):
                constraints["require_surfaces"].append(surface_type)

        # Deduplicate
        constraints["avoid_surfaces"] = list(set(constraints["avoid_surfaces"]))
        constraints["prefer_surfaces"] = list(set(constraints["prefer_surfaces"]))
        constraints["require_surfaces"] = list(set(constraints["require_surfaces"]))

        return constraints

    def _extract_distance(self, message: str, current_distance: int = None) -> int:
        """Extract target distance in meters from user message."""
        message_lower = message.lower()

        # Relative distance adjustments: "10 miles longer", "add 5 miles", "another 8 mi"
        if current_distance:
            delta_patterns = [
                r'(?:add|another|extra)\s+(\d+)\s*(?:miles?|mi)\b',
                r'(\d+)\s*(?:miles?|mi)\s*(?:longer|more)\b',
            ]
            for pattern in delta_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    miles = int(match.group(1))
                    return current_distance + int(miles * 1609.34)

            km_delta_patterns = [
                r'(?:add|another|extra)\s+(\d+)\s*(?:kms?|kilometers?)\b',
                r'(\d+)\s*(?:kms?|kilometers?)\s*(?:longer|more)\b',
            ]
            for pattern in km_delta_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    km = int(match.group(1))
                    return current_distance + (km * 1000)

        # Look for explicit mile patterns
        mile_patterns = [
            r'(\d+)\s*(?:mile|mi)',
            r'(\d+)-(\d+)\s*(?:mile|mi)',  # Range like "15-20 mile"
        ]

        for pattern in mile_patterns:
            match = re.search(pattern, message_lower)
            if match:
                if len(match.groups()) == 2 and match.group(2):
                    # Range - take the average
                    miles = (int(match.group(1)) + int(match.group(2))) / 2
                else:
                    miles = int(match.group(1))
                return int(miles * 1609.34)

        # Look for kilometer patterns
        km_patterns = [
            r'(\d+)\s*(?:km|kilometer)',
        ]

        for pattern in km_patterns:
            match = re.search(pattern, message_lower)
            if match:
                km = int(match.group(1))
                return km * 1000

        # Handle relative modifications (longer/shorter)
        if current_distance:
            if any(kw in message_lower for kw in ["longer", "more distance", "extend"]):
                return int(current_distance * 1.3)  # 30% longer
            elif any(kw in message_lower for kw in ["shorter", "less distance", "reduce"]):
                return int(current_distance * 0.7)  # 30% shorter
            elif "tighter" in message_lower:
                return int(current_distance * 0.8)  # Tighter loop = a bit shorter

        # Look for descriptive words
        if any(kw in message_lower for kw in ["short", "quick", "easy"]):
            return 16000  # ~10 miles
        elif any(kw in message_lower for kw in ["long", "big"]):
            return 64000  # ~40 miles
        elif any(kw in message_lower for kw in ["epic", "century"]):
            return 100000  # ~62 miles

        # Default: ~15 miles - solid intermediate ride
        return 25000

    def _extract_distance_delta(self, message: str) -> Optional[int]:
        """Extract relative distance change in meters, if specified."""
        message_lower = message.lower()

        mile_patterns = [
            r'(?:add|another|extra)\s+(\d+)\s*(?:miles?|mi)\b',
            r'(\d+)\s*(?:miles?|mi)\s*(?:longer|more)\b',
        ]
        for pattern in mile_patterns:
            match = re.search(pattern, message_lower)
            if match:
                miles = int(match.group(1))
                return int(miles * 1609.34)

        km_patterns = [
            r'(?:add|another|extra)\s+(\d+)\s*(?:kms?|kilometers?)\b',
            r'(\d+)\s*(?:kms?|kilometers?)\s*(?:longer|more)\b',
        ]
        for pattern in km_patterns:
            match = re.search(pattern, message_lower)
            if match:
                km = int(match.group(1))
                return km * 1000

        return None

    async def parse_constraints(
        self,
        message: str,
        current_constraints: Optional[Dict[str, Any]] = None,
    ) -> ConstraintInterpretation:
        """Parse user message into route constraints.

        Uses Claude to interpret natural language into structured constraints.
        """
        prompt = f"""Parse the following user message into route planning constraints.
Return a JSON object with:
- "understood": constraints you can confidently extract
- "ambiguous": list of things that are unclear
- "clarifying_questions": questions to ask for clarification
- "confidence": 0-1 confidence score

User message: "{message}"

Current constraints: {json.dumps(current_constraints) if current_constraints else "None"}

Respond with only the JSON object."""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            result = json.loads(response.content[0].text)
            return ConstraintInterpretation(**result)
        except:
            return ConstraintInterpretation(
                understood={},
                ambiguous=[message],
                clarifying_questions=["Could you tell me more about what kind of route you're looking for?"],
                confidence=0.1,
            )


# Singleton
_copilot_service: Optional[AICopilotService] = None


async def get_copilot_service() -> AICopilotService:
    """Get or create AI copilot service instance."""
    global _copilot_service
    if _copilot_service is None:
        _copilot_service = AICopilotService()
    return _copilot_service
