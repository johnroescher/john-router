"""Route metadata enrichment using OpenStreetMap data."""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
import math

import structlog

from app.schemas.common import Coordinate
from app.services.planning_tools import overpass_query
from app.services.elevation import get_elevation_service

logger = structlog.get_logger()


class RouteMetadataService:
    """Enrich route segments with OSM-derived metadata."""

    def __init__(self):
        self.search_radius_m = 35

    async def build_segment_metadata(self, geometry: Dict[str, Any]) -> List[Dict[str, Any]]:
        coordinates = geometry.get("coordinates", [])
        if len(coordinates) < 2:
            return []

        ways = await self._fetch_osm_ways(coordinates)
        elevation_profile = await self._get_elevation_profile(coordinates)

        segments: List[Dict[str, Any]] = []
        for idx in range(1, len(coordinates)):
            start = coordinates[idx - 1]
            end = coordinates[idx]
            distance_meters = self._haversine_distance(start[1], start[0], end[1], end[0])
            midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]

            tags = self._nearest_way_tags(ways, midpoint)
            segment_grade = self._grade_for_index(elevation_profile, idx)

            segment = self._build_segment_metadata(tags, distance_meters, segment_grade)
            segments.append(segment)

        return segments

    async def _fetch_osm_ways(self, coordinates: List[List[float]]) -> List[Dict[str, Any]]:
        min_lat, min_lng, max_lat, max_lng = self._bounds(coordinates, padding_m=80)
        query = f"""
[out:json][timeout:25];
(
  way["highway"]({min_lat},{min_lng},{max_lat},{max_lng});
);
out tags geom;
"""
        data = await overpass_query(query)
        features = data.get("features", [])
        ways = []
        for feature in features:
            geometry = feature.get("geometry", {})
            if geometry.get("type") != "LineString":
                continue
            ways.append({
                "geometry": geometry.get("coordinates", []),
                "tags": feature.get("properties", {}).get("tags", {}),
            })
        logger.info("route_metadata_osm_ways", way_count=len(ways))
        return ways

    async def _get_elevation_profile(self, coordinates: List[List[float]]) -> List[Dict[str, Any]]:
        elevation_service = await get_elevation_service()
        return await elevation_service.get_elevation_profile(coordinates)

    def _nearest_way_tags(self, ways: List[Dict[str, Any]], point: List[float]) -> Dict[str, Any]:
        best_tags: Dict[str, Any] = {}
        best_distance = self.search_radius_m

        for way in ways:
            coords = way.get("geometry", [])
            if not coords:
                continue
            if not self._point_within_way_bounds(coords, point, self.search_radius_m):
                continue

            dist = self._min_distance_to_way(coords, point)
            if dist < best_distance:
                best_distance = dist
                best_tags = way.get("tags", {}) or {}

        return best_tags

    def _build_segment_metadata(
        self,
        tags: Dict[str, Any],
        distance_meters: float,
        grade_percent: float,
    ) -> Dict[str, Any]:
        highway_type = tags.get("highway", "") if tags else ""
        surface = tags.get("surface") if tags else None
        tracktype = tags.get("tracktype") if tags else None
        if not surface:
            surface = self._surface_from_tracktype(tracktype)
        if not surface:
            surface = self._surface_from_highway(highway_type, tags)

        bicycle_access = tags.get("bicycle") if tags else None
        if not bicycle_access:
            bicycle_access = tags.get("access") if tags else None

        mtb_scale = self._parse_float(tags.get("mtb:scale")) if tags else None
        if mtb_scale is None:
            mtb_scale = self._parse_float(tags.get("mtb:scale:imba")) if tags else None

        segment = {
            "distance_meters": distance_meters,
            "highway_type": highway_type,
            "surface": surface or "unknown",
            "bicycle_access": bicycle_access or "unknown",
            "mtb_scale": mtb_scale,
            "sac_scale": tags.get("sac_scale") if tags else None,
            "trail_visibility": tags.get("trail_visibility") if tags else None,
            "smoothness": tags.get("smoothness") if tags else None,
            "cycleway": self._has_bike_lane(tags),
            "designated_mtb": self._is_designated_mtb(tags),
            "max_grade": max(grade_percent, 0),
            "min_grade": min(grade_percent, 0),
        }

        features = self._detect_mtb_features(tags)
        hazards = self._detect_hazards(tags, highway_type, surface)
        segment["mtb_features"] = features
        segment["hazards"] = hazards
        return segment

    def _detect_mtb_features(self, tags: Optional[Dict[str, Any]]) -> Dict[str, bool]:
        if not tags:
            return {
                "flow": False,
                "berms": False,
                "jumps": False,
                "drops": False,
                "rock_gardens": False,
                "roots": False,
                "technical_climbs": False,
                "chunk": False,
            }

        text = " ".join([str(v).lower() for v in tags.values()])
        return {
            "flow": "flow" in text,
            "berms": "berm" in text,
            "jumps": "jump" in text,
            "drops": "drop" in text,
            "rock_gardens": "rock" in text or "garden" in text,
            "roots": "root" in text,
            "technical_climbs": "technical" in text or "tech" in text,
            "chunk": "chunk" in text,
        }

    def _detect_hazards(
        self,
        tags: Optional[Dict[str, Any]],
        highway_type: str,
        surface: Optional[str],
    ) -> Dict[str, bool]:
        text = " ".join([str(v).lower() for v in (tags or {}).values()])
        sac_scale = (tags or {}).get("sac_scale") if tags else None
        trail_visibility = (tags or {}).get("trail_visibility") if tags else None
        smoothness = (tags or {}).get("smoothness") if tags else None
        lit = (tags or {}).get("lit") if tags else None

        exposure = "exposure" in text or (sac_scale in {"T4", "T5", "T6"})
        cliff_edges = "cliff" in text or "precipice" in text
        loose_terrain = any(token in text for token in ["loose", "scree", "rock", "sand", "gravel"]) or (
            smoothness in {"bad", "very_bad", "horrible", "very_horrible", "impassable"}
        )
        water_crossings = "ford" in text or "waterway" in text
        high_speed = highway_type in {"primary", "secondary", "trunk", "motorway"}
        night_unsafe = lit == "no" or trail_visibility in {"bad", "horrible"}

        return {
            "exposure": exposure,
            "cliff_edges": cliff_edges,
            "loose_terrain": loose_terrain or (surface in {"sand", "gravel", "mud"} if surface else False),
            "water_crossings": water_crossings,
            "high_speed_road_crossings": high_speed,
            "night_unsafe": night_unsafe,
        }

    def _surface_from_tracktype(self, tracktype: Optional[str]) -> Optional[str]:
        if not tracktype:
            return None
        mapping = {
            "grade1": "paved",
            "grade2": "gravel",
            "grade3": "dirt",
            "grade4": "dirt",
            "grade5": "ground",
        }
        return mapping.get(tracktype, None)

    def _surface_from_highway(
        self,
        highway_type: Optional[str],
        tags: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if not highway_type:
            return None
        highway = str(highway_type).lower()

        if highway in {"path", "footway", "bridleway", "steps", "trail"}:
            return "ground"

        if highway == "track":
            tracktype = tags.get("tracktype") if tags else None
            return self._surface_from_tracktype(tracktype) or "gravel"

        if highway == "cycleway":
            return "paved"

        return None

    def _has_bike_lane(self, tags: Optional[Dict[str, Any]]) -> bool:
        if not tags:
            return False
        cycleway_keys = [
            "cycleway",
            "cycleway:left",
            "cycleway:right",
            "cycleway:both",
        ]
        for key in cycleway_keys:
            if tags.get(key) and str(tags.get(key)).lower() != "no":
                return True
        return False

    def _is_designated_mtb(self, tags: Optional[Dict[str, Any]]) -> bool:
        if not tags:
            return False
        if tags.get("mtb") in {"yes", "designated"}:
            return True
        if tags.get("bicycle") == "designated":
            return True
        if tags.get("mtb:scale") or tags.get("mtb:scale:imba"):
            return True
        return False

    def _grade_for_index(self, profile: List[Dict[str, Any]], index: int) -> float:
        if not profile or index >= len(profile):
            return 0.0
        grade = profile[index].get("grade_percent")
        return float(grade) if grade is not None else 0.0

    def _point_within_way_bounds(
        self,
        coordinates: List[List[float]],
        point: List[float],
        padding_m: float,
    ) -> bool:
        min_lat, min_lng, max_lat, max_lng = self._bounds(coordinates, padding_m=padding_m)
        return min_lng <= point[0] <= max_lng and min_lat <= point[1] <= max_lat

    def _min_distance_to_way(self, coordinates: List[List[float]], point: List[float]) -> float:
        min_dist = float("inf")
        for coord in coordinates:
            dist = self._haversine_distance(point[1], point[0], coord[1], coord[0])
            if dist < min_dist:
                min_dist = dist
        return min_dist

    def _bounds(self, coordinates: List[List[float]], padding_m: float = 0) -> Tuple[float, float, float, float]:
        lats = [c[1] for c in coordinates]
        lngs = [c[0] for c in coordinates]
        min_lat = min(lats)
        max_lat = max(lats)
        min_lng = min(lngs)
        max_lng = max(lngs)

        if padding_m > 0:
            lat_pad = padding_m / 111000
            lng_pad = padding_m / (111000 * math.cos(math.radians((min_lat + max_lat) / 2)))
            min_lat -= lat_pad
            max_lat += lat_pad
            min_lng -= lng_pad
            max_lng += lng_pad

        return min_lat, min_lng, max_lat, max_lng

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2) ** 2 +
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


_route_metadata_service: Optional[RouteMetadataService] = None


async def get_route_metadata_service() -> RouteMetadataService:
    global _route_metadata_service
    if _route_metadata_service is None:
        _route_metadata_service = RouteMetadataService()
    return _route_metadata_service
