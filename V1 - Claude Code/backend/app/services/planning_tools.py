"""Tool implementations for the Ride Brief Loop."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json

import httpx
import structlog

from app.schemas.common import Coordinate
from app.schemas.route import RouteConstraints, SportType, RouteType, RoutingService, SurfacePreferences
from app.services.geocoding import get_geocoding_service
from app.services.routing import get_routing_service
from app.services.analysis import get_analysis_service
from app.services.validation import get_validation_service

logger = structlog.get_logger()


def _coords_from_latlon(value: Dict[str, Any]) -> Coordinate:
    return Coordinate(lat=float(value["lat"]), lng=float(value["lng"]))


async def geocode_place(query: str) -> Dict[str, Any]:
    """Geocode a place name to coordinates and bbox."""
    # Cache geocode results to reduce repeated lookups
    from app.services.cache_service import get_cache_service
    cache_service = await get_cache_service()
    cache_key = cache_service._make_key("geocode:place", query=query.strip().lower())
    cached = await cache_service.get(cache_key)
    if cached:
        return cached

    service = await get_geocoding_service()
    url = f"{service.nominatim_url}/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "JohnRouter/1.0 (contact@johnrouter.app)"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
    if not results:
        return {"point": None, "bbox": None, "confidence": 0.0}

    result = results[0]
    point = {"lat": float(result["lat"]), "lng": float(result["lon"])}
    bbox_vals = result.get("boundingbox")
    bbox_geojson = None
    if bbox_vals and len(bbox_vals) == 4:
        min_lat, max_lat, min_lng, max_lng = map(float, bbox_vals)
        bbox_geojson = {
            "type": "Polygon",
            "coordinates": [[
                [min_lng, min_lat],
                [max_lng, min_lat],
                [max_lng, max_lat],
                [min_lng, max_lat],
                [min_lng, min_lat],
            ]],
        }

    result = {
        "point": point,
        "bbox": bbox_geojson,
        "confidence": float(result.get("importance", 0)),
    }
    await cache_service.set(cache_key, result, ttl_seconds=86400)
    return result


async def overpass_query(query: str) -> Dict[str, Any]:
    """Run an Overpass query and return GeoJSON features."""
    # Check cache first
    from app.services.cache_service import get_cache_service
    import hashlib
    import structlog
    
    logger = structlog.get_logger()
    cache_service = await get_cache_service()
    query_hash = hashlib.md5(query.encode()).hexdigest()
    cache_key = f"overpass:query:{query_hash}"
    
    cached = await cache_service.get(cache_key)
    if cached:
        logger.debug("Cache hit for Overpass query")
        return cached
    
    overpass_url = "https://overpass-api.de/api/interpreter"
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            overpass_url,
            data={"data": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        data = response.json()

    features = []
    for element in data.get("elements", []):
        element_type = element.get("type")
        tags = element.get("tags", {})

        if element_type == "node":
            geometry = {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
        elif element_type == "way":
            coords = []
            for node in element.get("geometry", []):
                coords.append([node["lon"], node["lat"]])
            if len(coords) < 2:
                continue
            geometry = {"type": "LineString", "coordinates": coords}
        else:
            continue

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": element.get("id"),
                "type": element_type,
                "tags": tags,
            },
        })
    result = {
        "features": features,
        "meta": {
            "count": len(features),
            "source": "OSM",
            "timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        },
    }
    await cache_service.set(cache_key, result, ttl_seconds=7200)
    return result


async def poi_search(
    center: Optional[Dict[str, Any]] = None,
    bbox: Optional[Dict[str, Any]] = None,
    types: Optional[List[str]] = None,
    constraints: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Search for POIs around a center or within a bbox."""
    from app.services.cache_service import get_cache_service
    cache_service = await get_cache_service()
    cache_payload = {
        "center": center,
        "bbox": bbox,
        "types": types or [],
        "constraints": constraints or {},
    }
    cache_key = cache_service._make_key(
        "poi_search",
        payload=json.dumps(cache_payload, sort_keys=True),
    )
    cached = await cache_service.get(cache_key)
    if cached:
        return cached

    service = await get_geocoding_service()
    query = " ".join(types) if types else "poi"
    bbox_obj = None
    if bbox:
        coords = bbox.get("coordinates", [[]])[0]
        if len(coords) >= 4:
            min_lng = min(c[0] for c in coords)
            max_lng = max(c[0] for c in coords)
            min_lat = min(c[1] for c in coords)
            max_lat = max(c[1] for c in coords)
            from app.schemas.common import BoundingBox
            bbox_obj = BoundingBox(
                min_lat=min_lat,
                max_lat=max_lat,
                min_lng=min_lng,
                max_lng=max_lng,
            )
    if not bbox_obj and center:
        from app.schemas.common import BoundingBox
        lat = float(center.get("lat"))
        lng = float(center.get("lng"))
        radius_km = float(constraints.get("radius_km", 5)) if constraints else 5
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / 111.0
        bbox_obj = BoundingBox(
            min_lat=lat - lat_delta,
            max_lat=lat + lat_delta,
            min_lng=lng - lng_delta,
            max_lng=lng + lng_delta,
        )

    results = await service.search_places(query=query, bbox=bbox_obj, limit=12)
    pois = []
    for item in results:
        coordinate = item.get("coordinate")
        if not coordinate:
            continue
        pois.append({
            "type": "poi",
            "name": item.get("name", ""),
            "point": {"lat": coordinate.lat, "lng": coordinate.lng},
            "confidence": float(item.get("importance", 0.5)),
        })
    await cache_service.set(cache_key, pois, ttl_seconds=3600)
    return pois


async def route_generate(
    profile: str,
    waypoints: List[Dict[str, Any]],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a route geometry from waypoints and options."""
    if not waypoints:
        raise ValueError("waypoints required")
    options = options or {}
    target_time_seconds = options.get("target_time_seconds")
    target_distance_km = options.get("target_distance_km")

    if not target_distance_km and target_time_seconds:
        # Derive distance from time using profile-specific speeds.
        speed_kmh_by_profile = {
            "road": 24.0,
            "gravel": 18.0,
            "mtb": 14.0,
            "emtb": 16.0,
            "urban": 16.0,
        }
        speed_kmh = speed_kmh_by_profile.get(profile, 18.0)
        target_distance_km = max(5.0, (target_time_seconds / 3600) * speed_kmh)

    route_type = options.get("route_type", "loop")
    if route_type not in ["loop", "out_and_back", "point_to_point"]:
        route_type = "loop"
    sport_profile = profile if profile in ["road", "gravel", "mtb", "urban", "emtb"] else "gravel"
    sport_type = SportType.MTB if sport_profile in ["mtb", "emtb"] else SportType.GRAVEL
    if sport_profile == "road":
        sport_type = SportType.ROAD

    start = _coords_from_latlon(waypoints[0])
    end = None
    via_points = []
    if route_type == "point_to_point" and len(waypoints) > 1:
        end = _coords_from_latlon(waypoints[-1])
        if len(waypoints) > 2:
            via_points = [_coords_from_latlon(wp) for wp in waypoints[1:-1]]
    else:
        if len(waypoints) > 1:
            via_points = [_coords_from_latlon(wp) for wp in waypoints[1:]]

    avoid_areas = []
    for area in options.get("avoid_areas", []) if options else []:
        if isinstance(area, dict) and area.get("type") == "Polygon":
            ring = area.get("coordinates", [[]])[0]
            polygon = [Coordinate(lat=pt[1], lng=pt[0]) for pt in ring]
            if polygon:
                avoid_areas.append(polygon)

    routing_service_raw = options.get("routing_service")
    routing_service = RoutingService.AUTO
    if routing_service_raw:
        try:
            routing_service = RoutingService(str(routing_service_raw).lower())
        except ValueError:
            routing_service = RoutingService.AUTO

    surface_preferences = None
    surface_pref_raw = options.get("surface_preferences")
    if isinstance(surface_pref_raw, dict):
        try:
            surface_preferences = SurfacePreferences(**surface_pref_raw)
        except Exception:
            surface_preferences = None

    constraints = RouteConstraints(
        start=start,
        end=end,
        via_points=via_points,
        route_type=RouteType(route_type),
        sport_type=sport_type,
        target_distance_meters=(target_distance_km or 0) * 1000 if target_distance_km else None,
        min_distance_meters=(options.get("min_distance_km") or 0) * 1000 if options.get("min_distance_km") else None,
        max_distance_meters=(options.get("max_distance_km") or 0) * 1000 if options.get("max_distance_km") else None,
        target_time_seconds=target_time_seconds,
        target_elevation_gain_meters=options.get("target_elevation_gain_m"),
        avoid_areas=avoid_areas,
        routing_service=routing_service,
        routing_profile=options.get("routing_profile"),
        avoid_highways=bool(options.get("avoid_highways", False)),
        climb_emphasis=float(options.get("climb_emphasis", 0)) if options.get("climb_emphasis") is not None else 0,
        surface_preferences=surface_preferences or SurfacePreferences(),
        quality_mode=bool(options.get("quality_mode", True)),
        num_alternatives=max(1, int(options.get("num_alternatives", 1))),
    )

    routing_service = await get_routing_service()

    # Preflight routing service availability for explicit service requests
    if constraints.routing_service == RoutingService.ORS and not routing_service.ors_api_key:
        return {
            "geometry": None,
            "legs": [],
            "meta": {
                "success": False,
                "error": "ORS_API_KEY not configured. Please set ORS_API_KEY in .env",
                "requested_service": "ors",
            }
        }
    if constraints.routing_service == RoutingService.GRAPHHOPPER and not routing_service.graphhopper_api_key:
        return {
            "geometry": None,
            "legs": [],
            "meta": {
                "success": False,
                "error": "GRAPHHOPPER_API_KEY not configured. Please set GRAPHHOPPER_API_KEY in .env",
                "requested_service": "graphhopper",
            }
        }
    if constraints.routing_service == RoutingService.VALHALLA and not routing_service.valhalla_api_key:
        return {
            "geometry": None,
            "legs": [],
            "meta": {
                "success": False,
                "error": "VALHALLA_API_KEY not configured. Please set VALHALLA_API_KEY in .env",
                "requested_service": "valhalla",
            }
        }

    # Cache route generation results for identical requests
    from app.services.cache_service import get_cache_service
    cache_service = await get_cache_service()
    try:
        cache_payload = {
            "profile": profile,
            "waypoints": [
                {"lat": round(float(wp.get("lat")), 6), "lng": round(float(wp.get("lng")), 6)}
                for wp in waypoints
            ],
            "options": options,
        }
        cache_key = cache_service._make_key("route:generate", payload=str(cache_payload))
        cached = await cache_service.get(cache_key)
        if cached:
            return cached
    except Exception:
        cache_key = None
    
    # Check service availability before attempting
    has_ors = bool(routing_service.ors_api_key)
    has_graphhopper = bool(routing_service.graphhopper_api_key)
    has_brouter = True  # BRouter is public, always available
    
    if not has_ors and not has_graphhopper and not has_brouter:
        logger.error("No routing services available")
        return {
            "geometry": None,
            "legs": [],
            "meta": {
                "success": False,
                "error": "No routing services configured. Please set ORS_API_KEY or GRAPHHOPPER_API_KEY in .env",
                "available_services": {
                    "brouter": has_brouter,
                    "ors": has_ors,
                    "graphhopper": has_graphhopper,
                }
            }
        }
    
    try:
        candidates = await routing_service.generate_route(constraints)
        if not candidates:
            logger.warning(
                "Route generation returned no candidates",
                route_type=constraints.route_type.value,
                sport_type=constraints.sport_type.value,
                target_distance=constraints.target_distance_meters,
            )
            return {
                "geometry": None,
                "legs": [],
                "meta": {
                    "success": False,
                    "error": "No valid route candidates found. This may be due to: route constraints too strict, all candidates rejected for doubling back, or insufficient routing data in this area.",
                }
            }
    except ValueError as e:
        error_msg = str(e)
        if "not configured" in error_msg.lower() or "api key" in error_msg.lower():
            logger.error(f"Routing service configuration error: {error_msg}")
            return {
                "geometry": None,
                "legs": [],
                "meta": {
                    "success": False,
                    "error": f"Routing service configuration error: {error_msg}. Please check your API keys in .env",
                }
            }
        raise
    except Exception as e:
        logger.error(f"Route generation exception: {e}", exc_info=True)
        return {
            "geometry": None,
            "legs": [],
            "meta": {
                "success": False,
                "error": f"Route generation failed: {str(e)}",
            }
        }

    candidate = candidates[0]
    result = {
        "geometry": candidate.get("geometry"),
        "legs": candidate.get("legs", []),
        "meta": {
            "success": True,
            "distance_meters": candidate.get("distance_meters"),
            "duration_seconds": candidate.get("duration_seconds"),
            "elevation_gain": candidate.get("elevation_gain"),
            "surface_breakdown": candidate.get("surface_breakdown", {}),
            "source": candidate.get("source", "router"),
            "transition_segments": candidate.get("transition_segments", []),
        },
        "transition_segments": candidate.get("transition_segments", []),
    }
    if cache_key:
        await cache_service.set(cache_key, result, ttl_seconds=900)
    return result


async def route_analyze(geometry: Dict[str, Any]) -> Dict[str, Any]:
    analysis_service = await get_analysis_service()
    analysis = await analysis_service.analyze_route(geometry)
    return analysis.model_dump()


async def route_validate(geometry: Dict[str, Any], profile: str) -> Dict[str, Any]:
    validation_service = await get_validation_service()
    validation = await validation_service.validate_route(geometry)
    return validation.model_dump()


async def apply_avoidance(route_request: Dict[str, Any], polygons: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach avoidance polygons to a route request."""
    options = route_request.get("options", {}) if route_request else {}
    options["avoid_areas"] = options.get("avoid_areas", []) + polygons
    updated = dict(route_request or {})
    updated["options"] = options
    return updated
