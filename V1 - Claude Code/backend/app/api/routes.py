"""Route management API endpoints."""
from typing import List, Optional, Dict, Any
import asyncio
import contextlib
import time
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
import gpxpy
import gpxpy.gpx
from io import BytesIO
import structlog
import httpx

from app.core.database import get_db
from app.models.route import Route, RouteWaypoint, RouteSegment
from app.schemas.route import (
    RouteCreate,
    RouteUpdate,
    RouteResponse,
    RouteListResponse,
    RouteConstraints,
    SportType,
    RouteCandidateResponse,
    RouteAnalysis,
    RouteValidation,
    ValidationIssue,
    GPXExport,
    GPXImport,
    SurfaceBreakdown,
    MTBDifficultyBreakdown,
    PointToPointRequest,
    PointToPointResponse,
    SurfaceBreakdownResponse,
    GeometryAnalysisRequest,
    WaypointResponse,
    SurfaceMatchRequest,
    SurfaceMatchResponse,
)
from app.schemas.common import GeoJSONLineString, Coordinate
from app.services.routing import get_routing_service
from app.services.point_to_point_router_selection import (
    haversine_endpoint_gap_meters,
    is_two_point_long_segment,
    is_unreasonable_detour,
    route_score,
)
from app.api.routing_errors import http_exception_from_routing_error
from app.services.analysis import get_analysis_service
from app.services.validation import get_validation_service
from app.services.route_metadata import get_route_metadata_service
from app.services.surface_match import get_surface_match_service, SurfaceMatchError

routes_router = APIRouter()
logger = structlog.get_logger()

MIN_TURN_DEGREES = 50
MIN_WAYPOINT_SPACING_M = 800
MAX_WAYPOINT_SPACING_M = 5000
MIN_WAYPOINT_END_BUFFER_M = 400

HIGH_SPEED_HIGHWAYS = {"motorway", "trunk", "primary", "secondary"}
UNPAVED_SURFACES = {"unpaved", "gravel", "dirt", "ground", "sand", "mud"}


def _haversine_distance_meters(a: List[float], b: List[float]) -> float:
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _nearest_coordinate_on_linestring(coords: List[List[float]], target: List[float]) -> Optional[List[float]]:
    if not coords:
        return None
    best = None
    best_distance = float("inf")
    for coord in coords:
        distance = _haversine_distance_meters(coord, target)
        if distance < best_distance:
            best_distance = distance
            best = coord
    return best


async def _snap_point_to_highway(
    point: Coordinate,
    highway_filter: str,
    radius_meters: int,
) -> Optional[List[float]]:
    lat = point.lat
    lng = point.lng
    query = f"""
[out:json][timeout:25];
(
  way["highway"~"{highway_filter}"](around:{radius_meters},{lat},{lng});
);
out geom;
"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None
    best_point = None
    best_distance = float("inf")
    for feature in data.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "LineString":
            continue
        candidate = _nearest_coordinate_on_linestring(geometry.get("coordinates", []), [lng, lat])
        if not candidate:
            continue
        distance = _haversine_distance_meters(candidate, [lng, lat])
        if distance < best_distance:
            best_distance = distance
            best_point = candidate
    return best_point


async def _snap_coords_to_network(
    coordinates: List[Coordinate],
    highway_filter: str,
    max_radius_meters: int = 150,
) -> Optional[List[List[float]]]:
    if not coordinates:
        return None
    snapped: List[List[float]] = []
    for coord in coordinates:
        snapped_point = None
        for radius in (50, max_radius_meters):
            snapped_point = await _snap_point_to_highway(coord, highway_filter, radius)
            if snapped_point:
                break
        if not snapped_point:
            return None
        snapped.append(snapped_point)
    return snapped


def _max_connector_distance_meters(sport_type: SportType) -> int:
    if sport_type in [SportType.MTB, SportType.GRAVEL, SportType.EMTB]:
        return 250
    return 100


def _apply_connector_segments(
    geometry: List[List[float]],
    original_start: List[float],
    original_end: List[float],
    snapped_start: List[float],
    snapped_end: List[float],
    max_connector_distance_meters: int,
) -> Optional[Dict[str, Any]]:
    if not geometry or len(geometry) < 2:
        return None
    updated = geometry[:]
    reasons: List[str] = []

    start_distance = _haversine_distance_meters(original_start, snapped_start)
    if start_distance > 1:
        if start_distance > max_connector_distance_meters:
            return None
        if _haversine_distance_meters(updated[0], original_start) > 1:
            updated = [original_start] + updated
            reasons.append("start_connector")

    end_distance = _haversine_distance_meters(original_end, snapped_end)
    if end_distance > 1:
        if end_distance > max_connector_distance_meters:
            return None
        if _haversine_distance_meters(updated[-1], original_end) > 1:
            updated = updated + [original_end]
            reasons.append("end_connector")

    return {"geometry": updated, "reasons": reasons}


def _bearing_degrees(a: List[float], b: List[float]) -> Optional[float]:
    distance = _haversine_distance_meters(a, b)
    if distance < 1:
        return None
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _turn_angle_degrees(prev_bearing: float, next_bearing: float) -> float:
    delta = (next_bearing - prev_bearing + 540) % 360 - 180
    return abs(delta)


def _generate_auto_waypoints(coords: List[List[float]]) -> List[List[float]]:
    if len(coords) < 3:
        return []

    cumulative = [0.0]
    for i in range(1, len(coords)):
        cumulative.append(cumulative[-1] + _haversine_distance_meters(coords[i - 1], coords[i]))

    total_distance = cumulative[-1]
    if total_distance <= 0:
        return []

    waypoints: List[List[float]] = []
    distance_since_last = 0.0

    for i in range(1, len(coords) - 1):
        segment_distance = _haversine_distance_meters(coords[i - 1], coords[i])
        distance_since_last += segment_distance

        remaining = total_distance - cumulative[i]
        if remaining < MIN_WAYPOINT_END_BUFFER_M:
            break

        if distance_since_last >= MAX_WAYPOINT_SPACING_M:
            waypoints.append(coords[i])
            distance_since_last = 0.0
            continue

        if distance_since_last < MIN_WAYPOINT_SPACING_M:
            continue

        prev_bearing = _bearing_degrees(coords[i - 1], coords[i])
        next_bearing = _bearing_degrees(coords[i], coords[i + 1])
        if prev_bearing is None or next_bearing is None:
            continue

        if _turn_angle_degrees(prev_bearing, next_bearing) >= MIN_TURN_DEGREES:
            waypoints.append(coords[i])
            distance_since_last = 0.0

    return waypoints


def _estimate_duration_seconds(distance_meters: float, sport_type: str) -> float:
    average_speed_mps = {
        "road": 7.0,   # ~25 km/h
        "gravel": 5.5, # ~20 km/h
        "mtb": 4.2,    # ~15 km/h
        "emtb": 5.5,   # ~20 km/h
    }.get(sport_type, 5.0)
    return distance_meters / average_speed_mps if average_speed_mps > 0 else 0


def _fallback_point_to_point_response(
    coords: List[List[float]],
    sport_type: str,
    reason: Optional[str] = None,
) -> PointToPointResponse:
    if len(coords) < 2:
        raise HTTPException(status_code=400, detail="At least two coordinates are required")

    distance_meters = 0.0
    for i in range(1, len(coords)):
        distance_meters += _haversine_distance_meters(coords[i - 1], coords[i])

    return PointToPointResponse(
        geometry=GeoJSONLineString(
            type="LineString",
            coordinates=coords,
        ),
        distance_meters=distance_meters,
        duration_seconds=_estimate_duration_seconds(distance_meters, sport_type),
        elevation_gain=0,
        surface_breakdown=SurfaceBreakdownResponse(
            paved=0,
            unpaved=0,
            gravel=0,
            ground=0,
            unknown=100,
        ),
        degraded=True,
        degraded_reason=reason,
    )


@routes_router.get("", response_model=List[RouteListResponse])
async def list_routes(
    sport_type: Optional[str] = None,
    tags: Optional[List[str]] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List routes with optional filtering."""
    query = select(Route)

    if sport_type:
        query = query.where(Route.sport_type == sport_type)

    if tags:
        query = query.where(Route.tags.overlap(tags))

    query = query.offset(skip).limit(limit).order_by(Route.updated_at.desc())

    result = await db.execute(query)
    routes = result.scalars().all()

    return [
        RouteListResponse(
            id=r.id,
            name=r.name,
            sport_type=r.sport_type,
            distance_meters=r.distance_meters,
            elevation_gain_meters=r.elevation_gain_meters,
            estimated_time_seconds=r.estimated_time_seconds,
            surface_breakdown=SurfaceBreakdown(**r.surface_breakdown) if r.surface_breakdown else SurfaceBreakdown(),
            overall_difficulty=r.overall_difficulty,
            confidence_score=r.confidence_score,
            tags=r.tags,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in routes
    ]


@routes_router.post("", response_model=RouteResponse)
async def create_route(
    route: RouteCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new route."""
    from geoalchemy2.shape import from_shape
    from shapely.geometry import LineString

    # Convert GeoJSON to PostGIS geometry
    coords = route.geometry.coordinates
    line = LineString([(c[0], c[1]) for c in coords])

    db_route = Route(
        name=route.name,
        description=route.description,
        sport_type=route.sport_type,
        geometry=from_shape(line, srid=4326),
        tags=route.tags,
        is_public=route.is_public,
    )

    db.add(db_route)
    await db.commit()
    await db.refresh(db_route)

    # Analyze the route
    analysis_service = await get_analysis_service()
    analysis = await analysis_service.analyze_route({"type": "LineString", "coordinates": coords})

    # Update route with analysis results
    db_route.distance_meters = analysis.distance_meters
    db_route.elevation_gain_meters = analysis.elevation_gain_meters
    db_route.elevation_loss_meters = analysis.elevation_loss_meters
    db_route.estimated_time_seconds = analysis.estimated_time_seconds
    db_route.max_elevation_meters = analysis.max_elevation_meters
    db_route.min_elevation_meters = analysis.min_elevation_meters
    db_route.surface_breakdown = analysis.surface_breakdown.model_dump()
    db_route.mtb_difficulty_breakdown = analysis.mtb_difficulty_breakdown.model_dump()
    db_route.physical_difficulty = analysis.physical_difficulty
    db_route.technical_difficulty = analysis.technical_difficulty
    db_route.risk_rating = analysis.risk_rating
    db_route.overall_difficulty = analysis.overall_difficulty
    db_route.confidence_score = analysis.confidence_score

    await db.commit()
    await db.refresh(db_route)

    return _route_to_response(db_route, coords)


@routes_router.get("/{route_id}", response_model=RouteResponse)
async def get_route(
    route_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single route by ID."""
    result = await db.execute(select(Route).where(Route.id == route_id))
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Convert geometry to coordinates
    coords = _geometry_to_coords(route.geometry)

    return _route_to_response(route, coords)


@routes_router.put("/{route_id}", response_model=RouteResponse)
async def update_route(
    route_id: UUID,
    update: RouteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing route."""
    result = await db.execute(select(Route).where(Route.id == route_id))
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Update fields
    if update.name is not None:
        route.name = update.name
    if update.description is not None:
        route.description = update.description
    if update.sport_type is not None:
        route.sport_type = update.sport_type
    if update.tags is not None:
        route.tags = update.tags
    if update.is_public is not None:
        route.is_public = update.is_public

    if update.geometry is not None:
        from geoalchemy2.shape import from_shape
        from shapely.geometry import LineString

        coords = update.geometry.coordinates
        line = LineString([(c[0], c[1]) for c in coords])
        route.geometry = from_shape(line, srid=4326)

        # Re-analyze
        analysis_service = await get_analysis_service()
        analysis = await analysis_service.analyze_route({"type": "LineString", "coordinates": coords})

        route.distance_meters = analysis.distance_meters
        route.elevation_gain_meters = analysis.elevation_gain_meters
        route.confidence_score = analysis.confidence_score
        route.surface_breakdown = analysis.surface_breakdown.model_dump()

    await db.commit()
    await db.refresh(route)

    coords = _geometry_to_coords(route.geometry)
    return _route_to_response(route, coords)


@routes_router.delete("/{route_id}")
async def delete_route(
    route_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a route."""
    result = await db.execute(select(Route).where(Route.id == route_id))
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    await db.delete(route)
    await db.commit()

    return {"message": "Route deleted"}


@routes_router.post("/generate", response_model=List[RouteCandidateResponse])
async def generate_routes(
    constraints: RouteConstraints,
    db: AsyncSession = Depends(get_db),
):
    """Generate route candidates based on constraints."""
    try:
        constraints = _normalize_constraints_for_generation(constraints)
        routing_service = await get_routing_service()
        analysis_service = await get_analysis_service()
        validation_service = await get_validation_service()
        metadata_service = await get_route_metadata_service()

        # Generate candidates
        candidates = await routing_service.generate_route(constraints)
    except Exception as e:
        raise http_exception_from_routing_error(e)

    if not candidates:
        raise HTTPException(status_code=400, detail="No routes could be generated with these constraints. Try adjusting the start location or distance.")

    responses = []
    extra_scores: List[Dict[str, float]] = []

    for i, candidate in enumerate(candidates):
        geometry = candidate["geometry"]
        coords = geometry["coordinates"]

        segment_metadata = await metadata_service.build_segment_metadata(geometry)

        # Analyze
        analysis = await analysis_service.analyze_route(
            geometry,
            routing_data=candidate,
            segment_metadata=segment_metadata,
        )

        # Validate
        validation = await validation_service.validate_route(
            geometry,
            segments=segment_metadata,
            constraints=constraints,
        )
        if candidate.get("data_quality_warning"):
            validation.warnings.append(ValidationIssue(
                type="data_quality",
                severity="warning",
                message=candidate.get("warning_message", "Surface data incomplete; verify surfaces before riding."),
            ))

        metrics = _compute_segment_metrics(segment_metadata)
        is_valid, rejection_reasons = _candidate_satisfies_constraints(
            analysis,
            validation,
            constraints,
            metrics,
        )

        logger.info(
            "route_candidate_analysis",
            candidate_index=i + 1,
            distance_meters=analysis.distance_meters,
            elevation_gain_meters=analysis.elevation_gain_meters,
            surface_breakdown=analysis.surface_breakdown.model_dump(),
            confidence_score=analysis.confidence_score,
            validation_status=validation.status,
            rejection_reasons=rejection_reasons if not is_valid else None,
        )

        if not is_valid:
            continue

        preference_scores = {
            "bike_lane": metrics.get("bike_lane_share", 0.0),
            "designated_mtb": metrics.get("designated_mtb_share", 0.0),
            "mtb_features": _mtb_feature_score(metrics, constraints),
        }
        extra_scores.append(preference_scores)

        # Create temporary route response
        route_response = RouteResponse(
            id=UUID("00000000-0000-0000-0000-000000000000"),  # Temporary
            user_id=None,
            name=f"Candidate {i + 1}",
            description=None,
            sport_type=constraints.sport_type,
            geometry=GeoJSONLineString(type="LineString", coordinates=coords),
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
            validation_results=validation,
            waypoints=[],
            created_at=None,
            updated_at=None,
        )

        # Generate explanation
        explanation = _generate_candidate_explanation(analysis, validation, i)

        responses.append(RouteCandidateResponse(
            route=route_response,
            analysis=analysis,
            validation=validation,
            rank=i + 1,
            explanation=explanation,
            tradeoffs=_generate_tradeoffs(analysis, constraints),
        ))

    # Order candidates based on constraint match (best first)
    if not responses:
        raise HTTPException(
            status_code=400,
            detail="No routes could be generated with these constraints. Try relaxing constraints or adjusting your start location."
        )

    responses = _rank_candidates_by_constraints(responses, constraints, extra_scores=extra_scores)
    return responses


@routes_router.post("/point-to-point", response_model=PointToPointResponse)
async def route_point_to_point(
    request: PointToPointRequest,
    http_request: Request,
):
    """Route between a list of coordinates using optimal paths.

    This endpoint takes a list of coordinates and returns a routed path
    between them, using trails, roads, and paths as appropriate for the
    sport type. Used for manual route building where users click waypoints.
    """
    import structlog
    logger = structlog.get_logger()

    start_ts = time.monotonic()
    request_id = http_request.headers.get("x-request-id")
    logger.info(
        "route_point_to_point_start",
        request_id=request_id,
        sport_type=request.sport_type.value,
        point_count=len(request.coordinates),
        start=request.coordinates[0].to_list() if request.coordinates else None,
        end=request.coordinates[-1].to_list() if request.coordinates else None,
    )
    try:
        routing_service = await get_routing_service()

        # Convert coordinates to list format for routing
        coords = [coord.to_list() for coord in request.coordinates]
        direct_distance = None
        if len(coords) >= 2:
            direct_distance = _haversine_distance_meters(coords[0], coords[-1])
            if direct_distance < 1:
                return PointToPointResponse(
                    geometry=GeoJSONLineString(
                        type="LineString",
                        coordinates=[coords[0], coords[-1]],
                    ),
                    distance_meters=direct_distance,
                    duration_seconds=_estimate_duration_seconds(direct_distance, request.sport_type.value),
                    elevation_gain=0,
                    surface_breakdown=SurfaceBreakdownResponse(
                        paved=0,
                        unpaved=0,
                        gravel=0,
                        ground=0,
                        unknown=100,
                    ),
                    degraded=False,
                    degraded_reason=None,
                )

        # Determine which router to use based on sport type
        from app.schemas.route import SportType
        # Use trail-capable routing for off-road sports; for road, allow mixed routing
        use_brouter = request.sport_type in [SportType.MTB, SportType.GRAVEL, SportType.EMTB]
        parsed = None

        # Maximum allowed straight-line distance for trail-to-road transitions (100 feet = 30.48 meters)
        MAX_STRAIGHT_LINE_DISTANCE_METERS = 30.48

        def _highway_filter_for_sport(sport_type: SportType) -> str:
            if sport_type in [SportType.MTB, SportType.GRAVEL, SportType.EMTB]:
                return "path|track|cycleway|bridleway|footway|service|residential|unclassified|tertiary|secondary|primary"
            return "cycleway|service|residential|unclassified|tertiary|secondary|primary|trunk|motorway"

        async def _route_with_coords(route_coords: List[List[float]]) -> Dict[str, Any]:
            route_direct_distance = None
            if len(route_coords) >= 2:
                route_direct_distance = _haversine_distance_meters(route_coords[0], route_coords[-1])
            route_start = route_coords[0] if route_coords else None
            route_end = route_coords[-1] if route_coords else None

            def _is_geometry_too_simple(geometry_coords: List[List[float]]) -> bool:
                if not geometry_coords or len(geometry_coords) < 2:
                    return True
                # Allow short 2-point segments (≤100 ft) for trail-to-road transitions
                # Reject longer 2-point segments (>100 ft) as they don't follow the network
                if len(geometry_coords) == 2:
                    if route_direct_distance is None:
                        return True
                    return route_direct_distance > MAX_STRAIGHT_LINE_DISTANCE_METERS
                return False

            def _is_two_point_long_segment(geometry_coords: List[List[float]]) -> bool:
                if route_direct_distance is None:
                    return False
                # Check if 2-point segment exceeds 100 ft threshold
                return len(geometry_coords) == 2 and route_direct_distance > MAX_STRAIGHT_LINE_DISTANCE_METERS

            def _is_unreasonable_detour_route(route_distance: float) -> bool:
                return is_unreasonable_detour(route_distance, route_direct_distance)

            async def _try_brouter(profile: str) -> Dict[str, Any]:
                result = await routing_service._call_brouter_interactive(route_coords, profile)
                parsed = routing_service._parse_brouter_response(result)
                geometry_coords = parsed.get("geometry", {}).get("coordinates", [])
                if _is_geometry_too_simple(geometry_coords):
                    raise ValueError("BRouter returned overly simple geometry")
                return parsed

            async def _try_graphhopper(profile: str) -> Dict[str, Any]:
                result = await routing_service._call_graphhopper_route_interactive(route_coords, profile)
                parsed = routing_service._parse_graphhopper_response(result)
                geometry_coords = parsed.get("geometry", {}).get("coordinates", [])
                if _is_geometry_too_simple(geometry_coords):
                    raise ValueError("GraphHopper returned overly simple geometry")
                return parsed

            async def _try_ors(profile: str) -> Dict[str, Any]:
                result = await routing_service._call_ors_directions_interactive(
                    route_coords,
                    profile,
                    None,
                    preference="shortest",
                )
                parsed = routing_service._parse_ors_response(result)
                geometry_coords = parsed.get("geometry", {}).get("coordinates", [])
                if _is_geometry_too_simple(geometry_coords):
                    raise ValueError("ORS returned overly simple geometry")
                return parsed

            # Mixed routing: always try ORS + BRouter, then pick best.
            ors_profile = routing_service.ORS_PROFILES.get(request.sport_type, "cycling-road")
            brouter_profile = routing_service.BROUTER_PROFILES.get(request.sport_type, "fastbike")
            parsed_candidates: Dict[str, Dict[str, Any]] = {}

            async def _try_and_record(name: str, coro):
                try:
                    start = time.monotonic()
                    result = await coro
                    parsed_candidates[name] = result
                    geometry_coords = result.get("geometry", {}).get("coordinates", [])
                    gap_metrics = haversine_endpoint_gap_meters(
                        geometry_coords, route_start, route_end
                    ) or {}
                    logger.info(
                        "route_attempt",
                        router=name,
                        elapsed_ms=int((time.monotonic() - start) * 1000),
                    )
                    logger.info(
                        "route_candidate_metrics",
                        router=name,
                        point_count=len(geometry_coords),
                        start_gap_meters=round(gap_metrics.get("start_gap", 0), 1),
                        end_gap_meters=round(gap_metrics.get("end_gap", 0), 1),
                        total_gap_meters=round(gap_metrics.get("total_gap", 0), 1),
                        route_distance_meters=round(result.get("distance_meters", 0), 1),
                        direct_distance_meters=round(route_direct_distance or 0, 1),
                        two_point_long=_is_two_point_long_segment(geometry_coords),
                    )
                except Exception as exc:
                    logger.warning(f"{name} routing failed: {exc}")

            tasks = []
            tasks.append(asyncio.create_task(_try_and_record("ors", _try_ors(ors_profile))))
            tasks.append(asyncio.create_task(_try_and_record("brouter", _try_brouter(brouter_profile))))
            if use_brouter and routing_service.graphhopper_api_key:
                graphhopper_profile = routing_service.GRAPHOPPER_PROFILES.get(request.sport_type, "mtb")
                tasks.append(asyncio.create_task(_try_and_record("graphhopper", _try_graphhopper(graphhopper_profile))))

            await asyncio.gather(*tasks)

            def _route_score(candidate: Dict[str, Any]) -> float:
                geometry_coords = candidate.get("geometry", {}).get("coordinates", [])
                gap_metrics = haversine_endpoint_gap_meters(
                    geometry_coords, route_start, route_end
                )
                return route_score(candidate, route_direct_distance, gap_metrics)

            if not parsed_candidates:
                raise RuntimeError("All routers failed to produce a route")

            parsed = parsed_candidates.get("ors") or next(iter(parsed_candidates.values()))

            if "brouter" in parsed_candidates:
                ors_candidate = parsed_candidates.get("ors")
                brouter_candidate = parsed_candidates["brouter"]
                brouter_distance = brouter_candidate.get("distance_meters") or float("inf")
                if ors_candidate:
                    ors_distance = ors_candidate.get("distance_meters") or float("inf")
                    if _is_two_point_long_segment(ors_candidate.get("geometry", {}).get("coordinates", [])) or _is_unreasonable_detour_route(ors_distance):
                        parsed = brouter_candidate
                    elif request.sport_type == SportType.ROAD and brouter_distance <= ors_distance * 1.1:
                        parsed = brouter_candidate
                    elif _route_score(brouter_candidate) < _route_score(ors_candidate):
                        parsed = brouter_candidate
                else:
                    parsed = brouter_candidate

            parsed = await routing_service._attach_valhalla_surface(
                parsed,
                routing_service.VALHALLA_PROFILES.get(request.sport_type, "bicycle"),
            )
            return parsed

        parsed = await _route_with_coords(coords)

        geometry = parsed.get("geometry", {}).get("coordinates", [])
        if not geometry or len(geometry) < 2:
            raise RuntimeError("Router returned insufficient geometry (<2 coordinates)")

        surface_data = parsed.get("surface_breakdown", {})
        surface_response = SurfaceBreakdownResponse(
            paved=surface_data.get("paved", 0),
            unpaved=surface_data.get("unpaved", 0),
            gravel=surface_data.get("gravel", 0),
            ground=surface_data.get("ground", 0),
            unknown=surface_data.get("unknown", 0),
        )
        logger.info(
            "route_point_to_point_success",
            request_id=request_id,
            degraded=False,
            elapsed_ms=int((time.monotonic() - start_ts) * 1000),
            surface_breakdown_raw=surface_data,
            surface_breakdown_response={
                "paved": surface_response.paved,
                "unpaved": surface_response.unpaved,
                "gravel": surface_response.gravel,
                "ground": surface_response.ground,
                "unknown": surface_response.unknown,
            },
            surface_info_source=parsed.get("surface_info", {}).get("source"),
        )
        return PointToPointResponse(
            geometry=GeoJSONLineString(
                type="LineString",
                coordinates=geometry
            ),
            distance_meters=parsed.get("distance_meters", 0),
            duration_seconds=parsed.get("duration_seconds", 0),
            elevation_gain=parsed.get("elevation_gain", 0),
            surface_breakdown=surface_response,
            degraded=False,
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(
            "route_point_to_point_failed",
            request_id=request_id,
            error=error_msg,
        )
        try:
            highway_filter = _highway_filter_for_sport(request.sport_type)
            try:
                snapped_coords = await asyncio.wait_for(
                    _snap_coords_to_network(request.coordinates, highway_filter),
                    timeout=4.0,
                )
            except asyncio.TimeoutError:
                snapped_coords = None
            if snapped_coords:
                logger.info(
                    "route_snap_attempt",
                    request_id=request_id,
                    start=coords[0] if coords else None,
                    end=coords[-1] if coords else None,
                )
                parsed = await _route_with_coords(snapped_coords)
                geometry = parsed.get("geometry", {}).get("coordinates", [])
                if geometry and len(geometry) >= 2:
                    max_connector_distance = _max_connector_distance_meters(request.sport_type)
                    connector_result = _apply_connector_segments(
                        geometry=geometry,
                        original_start=coords[0],
                        original_end=coords[-1],
                        snapped_start=snapped_coords[0],
                        snapped_end=snapped_coords[-1],
                        max_connector_distance_meters=max_connector_distance,
                    )
                    if connector_result:
                        geometry = connector_result["geometry"]
                        connector_reasons = connector_result["reasons"]
                    else:
                        connector_reasons = []
                    surface_data = parsed.get("surface_breakdown", {})
                    degraded_reason = "snapped_to_network"
                    if connector_reasons:
                        degraded_reason = f"{degraded_reason};{','.join(connector_reasons)}"
                    logger.info(
                        "route_point_to_point_success",
                        request_id=request_id,
                        degraded=True,
                        degraded_reason=degraded_reason,
                        elapsed_ms=int((time.monotonic() - start_ts) * 1000),
                    )
                    return PointToPointResponse(
                        geometry=GeoJSONLineString(
                            type="LineString",
                            coordinates=geometry
                        ),
                        distance_meters=parsed.get("distance_meters", 0),
                        duration_seconds=parsed.get("duration_seconds", 0),
                        elevation_gain=parsed.get("elevation_gain", 0),
                        surface_breakdown=SurfaceBreakdownResponse(
                            paved=surface_data.get("paved", 0),
                            unpaved=surface_data.get("unpaved", 0),
                            gravel=surface_data.get("gravel", 0),
                            ground=surface_data.get("ground", 0),
                            unknown=surface_data.get("unknown", 0),
                        ),
                        degraded=True,
                        degraded_reason=degraded_reason,
                    )
        except Exception as snap_error:
            logger.warning(
                "route_snap_failed",
                request_id=request_id,
                error=str(snap_error),
            )

        # NEVER return a straight-line fallback - routes must follow network
        # Raise error so frontend can show proper error message
        raise HTTPException(
            status_code=503,
            detail=f"Routing failed: Unable to find a valid route following roads/trails. {error_msg}"
        )
    finally:
        logger.info("route_point_to_point_total", elapsed_ms=int((time.monotonic() - start_ts) * 1000))


@routes_router.get("/{route_id}/analyze", response_model=RouteAnalysis)
async def analyze_route(
    route_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed analysis for a route."""
    result = await db.execute(select(Route).where(Route.id == route_id))
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    coords = _geometry_to_coords(route.geometry)
    analysis_service = await get_analysis_service()

    return await analysis_service.analyze_route({"type": "LineString", "coordinates": coords})


@routes_router.post("/analyze-geometry", response_model=RouteAnalysis)
async def analyze_geometry(
    request: GeometryAnalysisRequest,
):
    """Analyze a route from geometry without saving."""
    analysis_service = await get_analysis_service()
    geometry = request.geometry.model_dump()
    return await analysis_service.analyze_route(geometry)


@routes_router.post("/surface-match", response_model=SurfaceMatchResponse)
async def surface_match(
    request: SurfaceMatchRequest,
    surface_match_service = Depends(get_surface_match_service),
) -> SurfaceMatchResponse:
    geometry = request.geometry.coordinates
    logger.info(
        "surface_match_request",
        point_count=len(geometry) if geometry else 0,
        sample_points=geometry[:3] if geometry else [],
        last_point=geometry[-1] if geometry else None,
    )
    if not geometry or len(geometry) < 2:
        return SurfaceMatchResponse(status="invalid_geometry", message="Geometry must have at least 2 points")

    try:
        segmented = await surface_match_service.match_geometry(geometry)
        logger.info(
            "surface_match_result",
            segments=len(segmented.segments),
            data_quality=segmented.dataQuality,
            enrichment_source=segmented.enrichmentSource,
        )
        return SurfaceMatchResponse(
            status="ok",
            message=f"source:{segmented.enrichmentSource};quality:{segmented.dataQuality:.1f}",
            segmentedSurface=segmented,
        )
    except SurfaceMatchError as exc:
        return SurfaceMatchResponse(status=exc.code, message=exc.message)
    except Exception as exc:
        logger.exception("Surface matching failed")
        raise HTTPException(status_code=500, detail=str(exc))


@routes_router.get("/{route_id}/validate", response_model=RouteValidation)
async def validate_route(
    route_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Validate a route for safety and legality."""
    result = await db.execute(select(Route).where(Route.id == route_id))
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    coords = _geometry_to_coords(route.geometry)
    validation_service = await get_validation_service()

    return await validation_service.validate_route({"type": "LineString", "coordinates": coords})


@routes_router.get("/{route_id}/export/gpx")
async def export_gpx(
    route_id: UUID,
    include_waypoints: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Export route as GPX file."""
    result = await db.execute(select(Route).where(Route.id == route_id))
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    coords = _geometry_to_coords(route.geometry)

    # Create GPX
    gpx = gpxpy.gpx.GPX()
    gpx.name = route.name
    gpx.description = route.description

    # Create track
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx_track.name = route.name
    gpx.tracks.append(gpx_track)

    # Create segment
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    # Add points
    for coord in coords:
        elevation = coord[2] if len(coord) > 2 else None
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(
                latitude=coord[1],
                longitude=coord[0],
                elevation=elevation,
            )
        )

    # Add waypoints if requested
    if include_waypoints:
        waypoints_result = await db.execute(
            select(RouteWaypoint).where(RouteWaypoint.route_id == route_id)
        )
        waypoints = waypoints_result.scalars().all()

        for wp in waypoints:
            wp_coords = _point_to_coords(wp.point)
            gpx_waypoint = gpxpy.gpx.GPXWaypoint(
                latitude=wp_coords[1],
                longitude=wp_coords[0],
                name=wp.name or wp.waypoint_type,
            )
            gpx.waypoints.append(gpx_waypoint)

    # Generate GPX content
    gpx_content = gpx.to_xml()

    # Return as downloadable file
    return StreamingResponse(
        BytesIO(gpx_content.encode()),
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": f"attachment; filename={route.name.replace(' ', '_')}.gpx"
        },
    )


@routes_router.post("/import/gpx", response_model=GPXImport)
async def import_gpx(
    file: UploadFile = File(...),
    name: Optional[str] = None,
    sport_type: str = "mtb",
    db: AsyncSession = Depends(get_db),
):
    """Import a route from GPX file."""
    content = await file.read()

    try:
        gpx = gpxpy.parse(content.decode())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid GPX file: {e}")

    # Extract coordinates from tracks
    all_coords = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                coord = [point.longitude, point.latitude]
                if point.elevation:
                    coord.append(point.elevation)
                all_coords.append(coord)

    if not all_coords:
        raise HTTPException(status_code=400, detail="GPX file contains no track points")

    # Create route
    route_name = name or gpx.name or file.filename.replace(".gpx", "")

    from geoalchemy2.shape import from_shape
    from shapely.geometry import LineString

    line = LineString([(c[0], c[1]) for c in all_coords])

    db_route = Route(
        name=route_name,
        description=gpx.description,
        sport_type=sport_type,
        geometry=from_shape(line, srid=4326),
    )

    db.add(db_route)
    await db.commit()
    await db.refresh(db_route)

    # Analyze
    analysis_service = await get_analysis_service()
    analysis = await analysis_service.analyze_route({"type": "LineString", "coordinates": all_coords})

    db_route.distance_meters = analysis.distance_meters
    db_route.elevation_gain_meters = analysis.elevation_gain_meters
    db_route.confidence_score = analysis.confidence_score

    # Import waypoints
    waypoints_imported = 0
    for wp in gpx.waypoints:
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        point = Point(wp.longitude, wp.latitude)
        db_waypoint = RouteWaypoint(
            route_id=db_route.id,
            idx=waypoints_imported,
            waypoint_type="poi",
            point=from_shape(point, srid=4326),
            name=wp.name,
        )
        db.add(db_waypoint)
        waypoints_imported += 1

    # If GPX contains no explicit waypoints, infer turn-based waypoints
    if waypoints_imported == 0:
        auto_waypoints = _generate_auto_waypoints(all_coords)
        for coord in auto_waypoints:
            from geoalchemy2.shape import from_shape
            from shapely.geometry import Point

            point = Point(coord[0], coord[1])
            db_waypoint = RouteWaypoint(
                route_id=db_route.id,
                idx=waypoints_imported,
                waypoint_type="via",
                point=from_shape(point, srid=4326),
                name=None,
            )
            db.add(db_waypoint)
            waypoints_imported += 1

    await db.commit()

    # Reload with waypoints eagerly loaded to avoid async lazy-load
    result = await db.execute(
        select(Route).options(selectinload(Route.waypoints)).where(Route.id == db_route.id)
    )
    db_route = result.scalar_one()

    return GPXImport(
        route=_route_to_response(db_route, all_coords),
        waypoints_imported=waypoints_imported,
        tracks_imported=len(gpx.tracks),
        warnings=[],
    )


def _geometry_to_coords(geometry) -> List[List[float]]:
    """Convert PostGIS geometry to coordinate list."""
    if geometry is None:
        return []

    from geoalchemy2.shape import to_shape

    shape = to_shape(geometry)
    return [[c[0], c[1]] + ([c[2]] if len(c) > 2 else []) for c in shape.coords]


def _point_to_coords(point) -> List[float]:
    """Convert PostGIS point to coordinates."""
    from geoalchemy2.shape import to_shape

    shape = to_shape(point)
    return [shape.x, shape.y]


def _route_to_response(route: Route, coords: List[List[float]]) -> RouteResponse:
    """Convert database route to response schema."""
    waypoints = []
    for wp in sorted(route.waypoints or [], key=lambda w: w.idx):
        lng, lat = _point_to_coords(wp.point)
        waypoints.append(
            WaypointResponse(
                id=wp.id,
                idx=wp.idx,
                waypoint_type=wp.waypoint_type,
                point=Coordinate(lat=lat, lng=lng),
                name=wp.name,
                lock_strength=wp.lock_strength,
                metadata=wp.waypoint_metadata or {},
            )
        )
    return RouteResponse(
        id=route.id,
        user_id=route.user_id,
        name=route.name,
        description=route.description,
        sport_type=route.sport_type,
        geometry=GeoJSONLineString(type="LineString", coordinates=coords) if coords else None,
        distance_meters=route.distance_meters,
        elevation_gain_meters=route.elevation_gain_meters,
        elevation_loss_meters=route.elevation_loss_meters,
        estimated_time_seconds=route.estimated_time_seconds,
        max_elevation_meters=route.max_elevation_meters,
        min_elevation_meters=route.min_elevation_meters,
        surface_breakdown=SurfaceBreakdown(**route.surface_breakdown) if route.surface_breakdown else SurfaceBreakdown(),
        mtb_difficulty_breakdown=MTBDifficultyBreakdown(**route.mtb_difficulty_breakdown) if route.mtb_difficulty_breakdown else MTBDifficultyBreakdown(),
        physical_difficulty=route.physical_difficulty,
        technical_difficulty=route.technical_difficulty,
        risk_rating=route.risk_rating,
        overall_difficulty=route.overall_difficulty,
        tags=route.tags or [],
        is_public=route.is_public,
        confidence_score=route.confidence_score,
        validation_status=route.validation_status,
        validation_results=RouteValidation(
            status=route.validation_status,
            errors=route.validation_results.get("errors", []),
            warnings=route.validation_results.get("warnings", []),
            info=route.validation_results.get("info", []),
            confidence_score=route.confidence_score,
        ),
        waypoints=waypoints,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def _generate_candidate_explanation(
    analysis: RouteAnalysis,
    validation: RouteValidation,
    index: int,
) -> str:
    """Generate explanation for why this candidate was generated."""
    parts = []

    if index == 0:
        parts.append("Best match for your constraints")
    else:
        parts.append(f"Alternative {index}")

    if analysis.surface_breakdown.singletrack > 50:
        parts.append("heavy singletrack")
    elif analysis.surface_breakdown.pavement > 50:
        parts.append("mostly paved")

    if validation.status == "valid":
        parts.append("no issues detected")
    elif validation.warnings:
        parts.append(f"{len(validation.warnings)} warning(s)")

    return "; ".join(parts)


def _generate_tradeoffs(
    analysis: RouteAnalysis,
    constraints: RouteConstraints,
) -> dict:
    """Generate tradeoff information."""
    tradeoffs = {}

    # Distance tradeoff
    if constraints.target_distance_meters:
        diff = analysis.distance_meters - constraints.target_distance_meters
        diff_pct = abs(diff) / constraints.target_distance_meters * 100
        if diff_pct > 10:
            direction = "longer" if diff > 0 else "shorter"
            tradeoffs["distance"] = f"{diff_pct:.0f}% {direction} than target"

    # Difficulty tradeoff
    if analysis.technical_difficulty > 3:
        tradeoffs["difficulty"] = "Higher technical difficulty for better trails"

    return tradeoffs


def _normalize_constraints_for_generation(constraints: RouteConstraints) -> RouteConstraints:
    """Normalize constraints for generation (derive distance from time if needed)."""
    normalized = constraints.model_copy(deep=True)

    if not normalized.target_distance_meters and normalized.target_time_seconds:
        # Estimate distance from target time by sport type
        avg_speed_mps = {
            "road": 7.0,   # ~25 km/h
            "gravel": 5.5, # ~20 km/h
            "mtb": 4.2,    # ~15 km/h
            "emtb": 5.5,   # ~20 km/h
        }.get(normalized.sport_type.value, 5.0)
        normalized.target_distance_meters = normalized.target_time_seconds * avg_speed_mps

    return normalized


def _compute_segment_metrics(segment_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_distance = sum(seg.get("distance_meters", 0) for seg in segment_metadata)
    if total_distance <= 0:
        return {
            "total_distance": 0,
            "bike_lane_share": 0,
            "designated_mtb_share": 0,
            "high_speed_share": 0,
            "unpaved_share": 0,
            "private_share": 0,
            "hazard_shares": {},
            "feature_shares": {},
        }

    def share(distance: float) -> float:
        return distance / total_distance if total_distance > 0 else 0

    bike_lane_dist = 0.0
    designated_mtb_dist = 0.0
    high_speed_dist = 0.0
    unpaved_dist = 0.0
    private_dist = 0.0

    hazard_totals: Dict[str, float] = {}
    feature_totals: Dict[str, float] = {}

    for seg in segment_metadata:
        distance = seg.get("distance_meters", 0)
        if seg.get("cycleway"):
            bike_lane_dist += distance
        if seg.get("designated_mtb"):
            designated_mtb_dist += distance
        if seg.get("highway_type") in HIGH_SPEED_HIGHWAYS:
            high_speed_dist += distance
        surface = seg.get("surface")
        if surface in UNPAVED_SURFACES:
            unpaved_dist += distance
        access = seg.get("bicycle_access", "unknown")
        if access in {"no", "private"}:
            private_dist += distance

        hazards = seg.get("hazards", {}) or {}
        for key, value in hazards.items():
            if value:
                hazard_totals[key] = hazard_totals.get(key, 0) + distance

        features = seg.get("mtb_features", {}) or {}
        for key, value in features.items():
            if value:
                feature_totals[key] = feature_totals.get(key, 0) + distance

    hazard_shares = {key: share(dist) for key, dist in hazard_totals.items()}
    feature_shares = {key: share(dist) for key, dist in feature_totals.items()}

    return {
        "total_distance": total_distance,
        "bike_lane_share": share(bike_lane_dist),
        "designated_mtb_share": share(designated_mtb_dist),
        "high_speed_share": share(high_speed_dist),
        "unpaved_share": share(unpaved_dist),
        "private_share": share(private_dist),
        "hazard_shares": hazard_shares,
        "feature_shares": feature_shares,
    }


def _candidate_satisfies_constraints(
    analysis: RouteAnalysis,
    validation: RouteValidation,
    constraints: RouteConstraints,
    metrics: Dict[str, Any],
) -> tuple[bool, List[str]]:
    reasons: List[str] = []
    quality_multiplier = 0.5 if constraints.quality_mode else 1.0

    distance_tolerance = 0.05 if constraints.quality_mode else 0.1
    time_tolerance = 0.1 if constraints.quality_mode else 0.15
    elevation_tolerance = 0.1 if constraints.quality_mode else 0.15

    if constraints.distance_hard_constraint:
        if constraints.min_distance_meters and analysis.distance_meters < constraints.min_distance_meters:
            reasons.append("below_min_distance")
        if constraints.max_distance_meters and analysis.distance_meters > constraints.max_distance_meters:
            reasons.append("above_max_distance")
        if constraints.target_distance_meters and not constraints.min_distance_meters and not constraints.max_distance_meters:
            diff_pct = abs(analysis.distance_meters - constraints.target_distance_meters) / max(constraints.target_distance_meters, 1)
            if diff_pct > distance_tolerance:
                reasons.append("distance_outside_target")

    if constraints.time_hard_constraint and constraints.target_time_seconds:
        diff_pct = abs(analysis.estimated_time_seconds - constraints.target_time_seconds) / max(constraints.target_time_seconds, 1)
        if diff_pct > time_tolerance:
            reasons.append("time_outside_target")

    if constraints.max_elevation_gain_meters is not None and analysis.elevation_gain_meters > constraints.max_elevation_gain_meters:
        reasons.append("above_max_elevation")

    if constraints.elevation_hard_constraint and constraints.target_elevation_gain_meters:
        diff_pct = abs(analysis.elevation_gain_meters - constraints.target_elevation_gain_meters) / max(constraints.target_elevation_gain_meters, 1)
        if diff_pct > elevation_tolerance:
            reasons.append("elevation_outside_target")

    if constraints.avoid_unpaved_when_road and constraints.sport_type.value == "road":
        if metrics.get("unpaved_share", 0) > (0.05 * quality_multiplier):
            reasons.append("unpaved_surface_present")

    if constraints.avoid_highways:
        if metrics.get("high_speed_share", 0) > (0.05 * quality_multiplier):
            reasons.append("high_speed_highways_present")

    if constraints.avoid_private:
        if metrics.get("private_share", 0) > 0:
            reasons.append("private_access_present")

    if constraints.require_bicycle_legal:
        if any(issue.type == "legality" and issue.severity == "error" for issue in validation.errors):
            reasons.append("illegal_access_present")

    if not constraints.allow_hike_a_bike:
        if analysis.hike_a_bike_distance_meters > 0:
            reasons.append("hike_a_bike_required")

    hazard_avoidances = constraints.hazard_avoidances.model_dump() if hasattr(constraints.hazard_avoidances, "model_dump") else {}
    hazard_threshold = 0.02 * quality_multiplier
    for hazard, enabled in hazard_avoidances.items():
        if enabled and metrics.get("hazard_shares", {}).get(hazard, 0) > hazard_threshold:
            reasons.append(f"hazard_{hazard}")

    return len(reasons) == 0, reasons


def _mtb_feature_score(metrics: Dict[str, Any], constraints: RouteConstraints) -> float:
    selected = [
        key for key, enabled in (
            constraints.mtb_features.model_dump() if hasattr(constraints.mtb_features, "model_dump") else {}
        ).items()
        if enabled
    ]
    if not selected:
        return 0.0
    shares = metrics.get("feature_shares", {})
    return sum(shares.get(feature, 0.0) for feature in selected) / len(selected)


def _rank_candidates_by_constraints(
    responses: List[RouteCandidateResponse],
    constraints: RouteConstraints,
    extra_scores: Optional[List[Dict[str, float]]] = None,
) -> List[RouteCandidateResponse]:
    if len(responses) <= 1:
        return responses

    scored = []
    for idx, response in enumerate(responses):
        score = _score_candidate(
            response.analysis,
            constraints,
            extra_scores[idx] if extra_scores and idx < len(extra_scores) else None,
        )
        scored.append((score, response))

    scored.sort(key=lambda item: item[0], reverse=True)

    ranked = []
    for idx, (_, response) in enumerate(scored):
        ranked.append(RouteCandidateResponse(
            route=response.route,
            analysis=response.analysis,
            validation=response.validation,
            rank=idx + 1,
            explanation=response.explanation,
            tradeoffs=response.tradeoffs,
        ))

    return ranked


def _score_candidate(
    analysis: RouteAnalysis,
    constraints: RouteConstraints,
    extra_scores: Optional[Dict[str, float]] = None,
) -> float:
    weights = {}
    scores = {}

    if constraints.target_distance_meters:
        diff = abs(analysis.distance_meters - constraints.target_distance_meters)
        scores["distance"] = max(0, 1 - diff / max(constraints.target_distance_meters, 1))
        weights["distance"] = 0.35

    if constraints.target_time_seconds:
        diff = abs(analysis.estimated_time_seconds - constraints.target_time_seconds)
        scores["time"] = max(0, 1 - diff / max(constraints.target_time_seconds, 1))
        weights["time"] = 0.1

    if constraints.target_elevation_gain_meters:
        diff = abs(analysis.elevation_gain_meters - constraints.target_elevation_gain_meters)
        scores["elevation"] = max(0, 1 - diff / max(constraints.target_elevation_gain_meters, 1))
        weights["elevation"] = 0.1

    # Penalize candidates that exceed grade limits
    grade_limit = min(constraints.max_downhill_grade_percent, constraints.max_uphill_grade_percent)
    if grade_limit > 0:
        grade_over = max(0, analysis.max_grade_percent - grade_limit)
        scores["grade"] = max(0, 1 - grade_over / max(grade_limit, 1))
        weights["grade"] = 0.1

    scores["surface"] = _surface_preference_score(analysis, constraints)
    weights["surface"] = 0.25

    if constraints.climb_emphasis:
        climb_ratio = analysis.elevation_gain_meters / max(analysis.distance_meters, 1)
        climb_score = min(1.0, climb_ratio / 0.15)
        if constraints.climb_emphasis < 0:
            climb_score = 1 - climb_score
        scores["climb_emphasis"] = climb_score
        weights["climb_emphasis"] = 0.05 + (abs(constraints.climb_emphasis) * 0.05)

    if extra_scores:
        if constraints.prefer_bike_lanes:
            scores["bike_lanes"] = extra_scores.get("bike_lane", 0.0)
            weights["bike_lanes"] = 0.05
        if constraints.prefer_designated_mtb_trails:
            scores["designated_trails"] = extra_scores.get("designated_mtb", 0.0)
            weights["designated_trails"] = 0.05

        selected_features = [k for k, v in (constraints.mtb_features.model_dump() if hasattr(constraints.mtb_features, "model_dump") else {}).items() if v]
        if selected_features:
            scores["mtb_features"] = extra_scores.get("mtb_features", 0.0)
            weights["mtb_features"] = 0.07

    if constraints.sport_type.value in ["mtb", "emtb"]:
        scores["difficulty"] = _difficulty_preference_score(analysis, constraints)
        weights["difficulty"] = 0.2

    total_weight = sum(weights.values()) or 1
    return sum(scores[key] * weights[key] for key in weights) / total_weight


def _surface_preference_score(analysis: RouteAnalysis, constraints: RouteConstraints) -> float:
    prefs = constraints.surface_preferences
    if not prefs:
        return 0.5

    # Combine dirt into singletrack for preference matching
    actual = {
        "pavement": analysis.surface_breakdown.pavement / 100,
        "gravel": analysis.surface_breakdown.gravel / 100,
        "singletrack": (analysis.surface_breakdown.singletrack + analysis.surface_breakdown.dirt) / 100,
    }

    diff_sum = (
        abs(prefs.pavement - actual["pavement"]) +
        abs(prefs.gravel - actual["gravel"]) +
        abs(prefs.singletrack - actual["singletrack"])
    )
    score = max(0, 1 - (diff_sum / 2))  # diff_sum max is 2

    # Penalize very high unknown surfaces
    if analysis.surface_breakdown.unknown > 60:
        score *= 0.6

    return score


def _difficulty_preference_score(analysis: RouteAnalysis, constraints: RouteConstraints) -> float:
    target = constraints.mtb_difficulty_target.value
    breakdown = analysis.mtb_difficulty_breakdown

    # Difficulty order from easy to hard
    order = ["green", "blue", "black", "double_black"]
    target_idx = {
        "easy": 0,
        "moderate": 1,
        "hard": 2,
        "very_hard": 3,
    }.get(target, 1)

    above_pct = 0
    for idx, level in enumerate(order):
        if idx > target_idx:
            above_pct += getattr(breakdown, level)

    return max(0, 1 - (above_pct / 100))
