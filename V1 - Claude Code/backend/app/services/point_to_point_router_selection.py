"""Heuristics for choosing the best point-to-point route among ORS / BRouter / GraphHopper candidates."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def haversine_distance_meters(a: List[float], b: List[float]) -> float:
    """Great-circle distance between two [lng, lat] points in meters."""
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def haversine_endpoint_gap_meters(
    geometry_coords: List[List[float]],
    route_start: Optional[List[float]],
    route_end: Optional[List[float]],
) -> Optional[Dict[str, float]]:
    if (
        not geometry_coords
        or len(geometry_coords) < 2
        or route_start is None
        or route_end is None
    ):
        return None
    start_gap = haversine_distance_meters(route_start, geometry_coords[0])
    end_gap = haversine_distance_meters(route_end, geometry_coords[-1])
    return {"start_gap": start_gap, "end_gap": end_gap, "total_gap": start_gap + end_gap}


def is_two_point_long_segment(
    geometry_coords: List[List[float]],
    route_direct_distance: Optional[float],
    max_straight_line_meters: float = 30.48,
) -> bool:
    if route_direct_distance is None:
        return False
    return (
        len(geometry_coords) == 2 and route_direct_distance > max_straight_line_meters
    )


def is_unreasonable_detour(
    route_distance: float,
    route_direct_distance: Optional[float],
    detour_ratio: float = 1.6,
) -> bool:
    if route_direct_distance is None or route_direct_distance < 20:
        return False
    return route_distance > route_direct_distance * detour_ratio


def route_score(
    candidate: Dict[str, Any],
    route_direct_distance: Optional[float],
    endpoint_gap_meters: Optional[Dict[str, float]],
) -> float:
    route_distance = candidate.get("distance_meters") or float("inf")
    if route_direct_distance is None:
        return route_distance
    geometry_coords = candidate.get("geometry", {}).get("coordinates", [])
    gap_metrics = endpoint_gap_meters or {}
    ratio = route_distance / max(route_direct_distance, 1)
    penalty = 0.0
    if is_unreasonable_detour(route_distance, route_direct_distance):
        penalty += route_distance * 0.5
    if is_two_point_long_segment(geometry_coords, route_direct_distance):
        penalty += route_distance * 2
    total_gap = gap_metrics.get("total_gap", 0)
    if total_gap > 1:
        penalty += total_gap * 20
    return route_distance + penalty + ratio * 5
