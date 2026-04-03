"""Surface matching and enrichment via Overpass + OSM tags."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
import math
import httpx

from app.core.config import settings
from app.schemas.route import SegmentedSurfaceData, SurfaceQualityMetrics, SurfaceSegment
from app.services.routing import get_routing_service
import structlog

logger = structlog.get_logger()


PAVED_SURFACES = {
    "paved", "asphalt", "concrete", "concrete:lanes", "concrete:plates",
    "paving_stones", "sett", "cobblestone", "cobblestone:flattened", "chipseal",
    "metal", "rubber",
}
GRAVEL_SURFACES = {
    "gravel", "fine_gravel", "pebblestone", "compacted", "crushed_limestone",
}
DIRT_SURFACES = {
    "dirt", "earth", "ground", "mud", "sand", "grass", "soil", "clay",
    "wood", "woodchips", "unpaved",
}

PAVED_HIGHWAY_TYPES = {
    "motorway", "trunk", "primary", "secondary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
}
VARIABLE_PAVED_HIGHWAY_TYPES = {
    "tertiary", "tertiary_link",
    "residential", "living_street", "service", "unclassified",
}
TRAIL_HIGHWAY_TYPES = {"path", "footway", "bridleway", "steps"}

TRACKTYPE_SURFACES = {
    "grade1": "gravel",
    "grade2": "gravel",
    "grade3": "dirt",
    "grade4": "dirt",
    "grade5": "dirt",
}


class OSMWay:
    def __init__(self, way_id: int, tags: Dict[str, str], geometry: List[Dict[str, float]]):
        self.id = way_id
        self.tags = tags
        self.geometry = geometry


def has_explicit_surface_tags(tags: Dict[str, str]) -> bool:
    return bool(tags.get("surface") or tags.get("tracktype") or tags.get("mtb:scale"))


def classify_way_surface(tags: Dict[str, str]) -> Tuple[str, float]:
    surface = tags.get("surface", "").lower() if tags.get("surface") else None
    highway = tags.get("highway", "").lower() if tags.get("highway") else None
    tracktype = tags.get("tracktype", "").lower() if tags.get("tracktype") else None
    mtb_scale = tags.get("mtb:scale")

    if surface:
        if surface in PAVED_SURFACES:
            return "pavement", 0.95
        if surface in GRAVEL_SURFACES:
            return "gravel", 0.95
        if surface in DIRT_SURFACES:
            return "dirt", 0.95
        if "paved" in surface:
            return "pavement", 0.8
        if "gravel" in surface or "compacted" in surface:
            return "gravel", 0.8

    if tracktype and tracktype in TRACKTYPE_SURFACES:
        return TRACKTYPE_SURFACES[tracktype], 0.85

    if mtb_scale:
        return "singletrack", 0.9

    if highway:
        if highway in PAVED_HIGHWAY_TYPES:
            return "pavement", 0.9 if highway in {"motorway", "trunk", "primary", "secondary"} else 0.8
        if highway in VARIABLE_PAVED_HIGHWAY_TYPES:
            return "unknown", 0.35
        if highway in TRAIL_HIGHWAY_TYPES:
            return "singletrack", 0.75
        if highway == "track":
            return "dirt", 0.7
        if highway == "cycleway":
            return "unknown", 0.4

    return "unknown", 0.3


def _haversine_distance_meters(a: List[float], b: List[float]) -> float:
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _calculate_cumulative_distances(geometry: List[List[float]]) -> List[float]:
    cumulative = [0.0]
    total = 0.0
    for i in range(1, len(geometry)):
        total += _haversine_distance_meters(geometry[i - 1], geometry[i])
        cumulative.append(total)
    return cumulative


def _point_to_line_segment_distance(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> float:
    lat_diff = x2 - x1
    lon_diff = y2 - y1
    point_lat_diff = px - x1
    point_lon_diff = py - y1

    dot = point_lat_diff * lat_diff + point_lon_diff * lon_diff
    len_sq = lat_diff * lat_diff + lon_diff * lon_diff
    param = 0.0
    if len_sq > 0:
        param = max(0.0, min(1.0, dot / len_sq))

    closest_lat = x1 + param * lat_diff
    closest_lon = y1 + param * lon_diff
    return _haversine_distance_meters([closest_lon, closest_lat], [py, px])


def _build_route_poly_string(geometry: List[List[float]], max_points: int) -> str:
    if not geometry:
        return ""
    total_points = len(geometry)
    step = max(1, total_points // max_points)
    points = []
    for i in range(0, total_points, step):
        lon, lat = geometry[i]
        points.append(f"{lat:.5f} {lon:.5f}")
    last_lon, last_lat = geometry[-1]
    last_point = f"{last_lat:.5f} {last_lon:.5f}"
    if points[-1] != last_point:
        points.append(last_point)
    return " ".join(points)


def _normalize_geometry_2d(geometry: List[List[float]]) -> List[List[float]]:
    normalized: List[List[float]] = []
    swap_candidates = 0
    for point in geometry:
        if len(point) < 2:
            raise SurfaceMatchError("Geometry points must include lon/lat", "invalid_geometry")
        lon, lat = point[0], point[1]
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            raise SurfaceMatchError("Geometry coordinates must be numeric", "invalid_geometry")
        if abs(lat) > 90 and abs(lon) <= 90:
            swap_candidates += 1
        normalized.append([lon, lat])

    if swap_candidates > len(normalized) / 2:
        logger.warning(
            "Surface match geometry appears lat/lon swapped; correcting.",
            swap_candidates=swap_candidates,
            point_count=len(normalized),
        )
        normalized = [[lat, lon] for lon, lat in normalized]

    return normalized


def _build_overpass_query(geometry: List[List[float]], sample_count: int, buffer_meters: int) -> str:
    poly_string = _build_route_poly_string(geometry, sample_count)
    if not poly_string:
        return ""
    way_query = f'way(around:{buffer_meters},poly:"{poly_string}")["highway"];'
    return f"[out:json][timeout:15];({way_query});out tags geom;"


async def _fetch_overpass_ways(query: str) -> List[OSMWay]:
    if not query:
        return []

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            settings.overpass_url,
            data={"data": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise SurfaceMatchError(
                f"Overpass error: {response.status_code}",
                "overpass_error",
            )
        data = response.json()

    ways: List[OSMWay] = []
    for element in data.get("elements", []):
        if element.get("type") != "way":
            continue
        way_id = element.get("id")
        tags = element.get("tags", {}) or {}
        geometry = element.get("geometry", []) or []
        if way_id and geometry:
            ways.append(OSMWay(int(way_id), {str(k): str(v) for k, v in tags.items()}, geometry))
    return ways


def _find_closest_way(
    lat: float,
    lon: float,
    ways: List[OSMWay],
    max_distance: float,
) -> Tuple[Optional[OSMWay], Optional[float]]:
    closest = None
    min_dist = max_distance
    for way in ways:
        geometry = way.geometry
        if not geometry:
            continue

        node_count = len(geometry)
        sample_step = max(1, node_count // 5)
        best_node_dist = float("inf")
        best_node_index = -1

        for idx in range(0, node_count, sample_step):
            node = geometry[idx]
            dist = _haversine_distance_meters([node["lon"], node["lat"]], [lon, lat])
            if dist < best_node_dist:
                best_node_dist = dist
                best_node_index = idx
            if dist < 8:
                best_node_dist = dist
                best_node_index = idx
                break

        if best_node_index != node_count - 1:
            last_node = geometry[-1]
            last_dist = _haversine_distance_meters([last_node["lon"], last_node["lat"]], [lon, lat])
            if last_dist < best_node_dist:
                best_node_dist = last_dist
                best_node_index = node_count - 1

        if best_node_dist < 40:
            check_range = 2
            start_idx = max(0, best_node_index - check_range)
            end_idx = min(node_count - 1, best_node_index + check_range)
            for i in range(start_idx, end_idx):
                node1 = geometry[i]
                node2 = geometry[i + 1]
                seg_dist = _point_to_line_segment_distance(
                    lat, lon,
                    node1["lat"], node1["lon"],
                    node2["lat"], node2["lon"],
                )
                if seg_dist < best_node_dist:
                    best_node_dist = seg_dist

        if best_node_dist < min_dist:
            min_dist = best_node_dist
            closest = way

    return closest, min_dist if closest else None


def _build_segmented_surface_data(
    geometry: List[List[float]],
    segments: List[SurfaceSegment],
    known_distance: float,
    confidence_sum: float,
    match_distance_sum: float,
) -> SegmentedSurfaceData:
    total_distance = _calculate_cumulative_distances(geometry)[-1] if geometry else 0.0
    if total_distance > 0:
        known_distance = min(known_distance, total_distance)
        coverage_percent = min(100.0, (known_distance / total_distance) * 100)
    else:
        coverage_percent = 0.0

    avg_confidence = (confidence_sum / known_distance) if known_distance > 0 else 0.0
    avg_match_distance = (match_distance_sum / known_distance) if known_distance > 0 else None

    return SegmentedSurfaceData(
        segments=segments,
        knownDistanceMeters=known_distance,
        totalDistanceMeters=total_distance,
        dataQuality=coverage_percent,
        qualityMetrics=SurfaceQualityMetrics(
            coveragePercent=coverage_percent,
            avgConfidence=avg_confidence,
            avgMatchDistanceMeters=avg_match_distance,
        ),
        lastUpdated=datetime.now(timezone.utc).isoformat(),
        enrichmentSource="overpass",
    )


@dataclass
class SurfaceMatchError(Exception):
    message: str
    code: str


class SurfaceMatchService:
    async def match_geometry(self, geometry: List[List[float]]) -> SegmentedSurfaceData:
        if len(geometry) < 2:
            raise SurfaceMatchError("Geometry must have at least 2 points", "invalid_geometry")

        geometry_2d = _normalize_geometry_2d(geometry)
        logger.info(
            "surface_match_geometry",
            point_count=len(geometry_2d),
            sample_points=geometry_2d[:3],
            last_point=geometry_2d[-1] if geometry_2d else None,
        )
        total_distance = _calculate_cumulative_distances(geometry_2d)[-1]
        adaptive_sample_count = 30 if total_distance < 5000 else 50 if total_distance < 20000 else 70
        buffer_meters = 25 if total_distance < 5000 else 40 if total_distance < 20000 else 50

        if settings.valhalla_api_key:
            try:
                routing_service = await get_routing_service()
                logger.info("surface_match_valhalla_attempt", point_count=len(geometry_2d))
                segmented, _ = await routing_service._get_valhalla_surface_data(geometry_2d, "bicycle")
                logger.info(
                    "surface_match_valhalla",
                    segments=len(segmented.segments),
                    data_quality=segmented.dataQuality,
                    enrichment_source=segmented.enrichmentSource,
                )
                return segmented
            except Exception as exc:
                logger.warning(
                    "Valhalla surface match failed, falling back to Overpass",
                    error=str(exc),
                    sample_points=geometry_2d[:3],
                    last_point=geometry_2d[-1] if geometry_2d else None,
                )

        query = _build_overpass_query(geometry_2d, adaptive_sample_count, buffer_meters)
        try:
            ways = await _fetch_overpass_ways(query)
        except SurfaceMatchError as exc:
            if exc.code == "overpass_error":
                unknown_segment = SurfaceSegment(
                    startIndex=0,
                    endIndex=len(geometry) - 1,
                    startDistanceMeters=0.0,
                    endDistanceMeters=total_distance,
                    distanceMeters=total_distance,
                    surfaceType="unknown",
                    confidence=0.0,
                    source="default",
                )
                return _build_segmented_surface_data(
                    geometry_2d,
                    [unknown_segment],
                    known_distance=0.0,
                    confidence_sum=0.0,
                    match_distance_sum=0.0,
                )
            raise

        if not ways:
            unknown_segment = SurfaceSegment(
                startIndex=0,
                endIndex=len(geometry) - 1,
                startDistanceMeters=0.0,
                endDistanceMeters=total_distance,
                distanceMeters=total_distance,
                surfaceType="unknown",
                confidence=0.0,
                source="default",
            )
            return _build_segmented_surface_data(
                geometry_2d,
                [unknown_segment],
                known_distance=0.0,
                confidence_sum=0.0,
                match_distance_sum=0.0,
            )

        cumulative = _calculate_cumulative_distances(geometry_2d)
        avg_point_spacing = total_distance / len(geometry_2d) if geometry_2d else 1
        target_sample_distance = 50 if total_distance < 5000 else 75 if total_distance < 20000 else 100
        sample_step = max(1, int(target_sample_distance / avg_point_spacing))

        segments: List[SurfaceSegment] = []
        current: Optional[SurfaceSegment] = None
        known_distance = 0.0
        confidence_sum = 0.0
        match_distance_sum = 0.0

        for i in range(0, len(geometry_2d) - 1, sample_step):
            lon, lat = geometry_2d[i]
            closest_way, match_distance = _find_closest_way(lat, lon, ways, buffer_meters)

            surface_type = "unknown"
            confidence = 0.0
            osm_way_id = None
            source = "default"

            if closest_way:
                surface_type, confidence = classify_way_surface(closest_way.tags)
                osm_way_id = closest_way.id
                source = "overpass" if has_explicit_surface_tags(closest_way.tags) else "map_inference"

            end_idx = min(i + sample_step, len(geometry_2d) - 1)
            segment_start_distance = cumulative[i]
            segment_end_distance = cumulative[end_idx]
            segment_distance = max(0.0, segment_end_distance - segment_start_distance)
            if segment_distance <= 0:
                continue

            segment = SurfaceSegment(
                startIndex=i,
                endIndex=end_idx,
                startDistanceMeters=segment_start_distance,
                endDistanceMeters=segment_end_distance,
                distanceMeters=segment_distance,
                surfaceType=surface_type,
                confidence=confidence,
                matchDistanceMeters=match_distance,
                source=source,
                osmWayId=osm_way_id,
            )

            if current and current.surfaceType == segment.surfaceType:
                current.endIndex = segment.endIndex
                current.endDistanceMeters = segment.endDistanceMeters
                current.distanceMeters += segment.distanceMeters
                if match_distance is not None:
                    current.matchDistanceMeters = min(
                        current.matchDistanceMeters or match_distance,
                        match_distance,
                    )
                current.confidence = max(current.confidence, segment.confidence)
            else:
                if current:
                    segments.append(current)
                current = segment

            if surface_type != "unknown":
                known_distance += segment_distance
                confidence_sum += confidence * segment_distance
                if match_distance is not None:
                    match_distance_sum += match_distance * segment_distance

        if current:
            segments.append(current)

        return _build_segmented_surface_data(
            geometry_2d,
            segments,
            known_distance=known_distance,
            confidence_sum=confidence_sum,
            match_distance_sum=match_distance_sum,
        )


_surface_match_service: Optional[SurfaceMatchService] = None


async def get_surface_match_service() -> SurfaceMatchService:
    global _surface_match_service
    if _surface_match_service is None:
        _surface_match_service = SurfaceMatchService()
    return _surface_match_service
