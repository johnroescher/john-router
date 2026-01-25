"""
Trail Database Service using OpenStreetMap Overpass API

This service queries OSM for trails, singletrack, and gravel roads to enable
intelligent waypoint placement on desired surface types.

Based on OSM tagging standards:
- MTB trails: highway=path + bicycle=yes/designated + mtb:scale
- Singletrack: highway=path + width<1m or sac_scale
- Gravel roads: highway=* + surface=gravel/compacted/dirt/unpaved
- Dirt roads: highway=track/unclassified + surface=dirt/ground

References:
- https://wiki.openstreetmap.org/wiki/Mountain_biking
- https://wiki.openstreetmap.org/wiki/Tag:surface=gravel
- https://wiki.openstreetmap.org/wiki/Overpass_API
"""
from typing import List, Dict, Any, Optional, Tuple
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

from app.schemas.common import Coordinate, BoundingBox
from app.schemas.route import SportType
from app.services.cache_service import get_cache_service
import hashlib

logger = structlog.get_logger()


class TrailDatabaseService:
    """Service for querying trail and gravel road data from OpenStreetMap."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.overpass_url = "https://overpass-api.de/api/interpreter"

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def _create_bbox_from_center(
        self,
        center: Coordinate,
        radius_km: float = 10,
    ) -> BoundingBox:
        """Create a bounding box from center point and radius.

        Args:
            center: Center coordinate
            radius_km: Radius in kilometers

        Returns:
            BoundingBox around center
        """
        # Approximate: 1 degree lat = 111km, 1 degree lng varies by latitude
        import math
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * math.cos(math.radians(center.lat)))

        return BoundingBox(
            min_lat=center.lat - lat_delta,
            max_lat=center.lat + lat_delta,
            min_lng=center.lng - lng_delta,
            max_lng=center.lng + lng_delta,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def find_mtb_trails(
        self,
        location: Coordinate,
        radius_km: float = 10,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find MTB trails and singletrack near location.

        Args:
            location: Center point
            radius_km: Search radius in km
            limit: Max number of trails to return

        Returns:
            List of trail features with coordinates
        """
        # Check cache
        cache_service = await get_cache_service()
        cache_key = cache_service._make_key(
            "trail_db:mtb",
            lat=location.lat,
            lng=location.lng,
            radius=radius_km,
            limit=limit,
        )
        cached = await cache_service.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for MTB trails at {location.lat},{location.lng}")
            return cached
        
        bbox = self._create_bbox_from_center(location, radius_km)

        # Overpass QL query for MTB trails and singletrack
        # Searches for:
        # 1. Paths designated for bicycles (bicycle=yes/designated)
        # 2. MTB-specific trails (mtb:scale, mtb:type)
        # 3. Singletrack (highway=path + narrow)
        query = f"""
[out:json][timeout:25];
(
  // MTB designated paths
  way["highway"="path"]["bicycle"~"yes|designated"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"="path"]["mtb:scale"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});

  // Tracks suitable for MTB
  way["highway"="track"]["bicycle"~"yes|designated"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"="track"]["surface"~"dirt|ground|earth|mud"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});

  // Singletrack (narrow paths)
  way["highway"="path"]["sac_scale"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
);
out geom;
"""

        try:
            response = await self.client.post(
                self.overpass_url,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()

            data = response.json()
            trails = self._parse_overpass_response(data, "mtb")

            logger.info(f"Found {len(trails)} MTB trails within {radius_km}km of location")

            # Limit results
            result = trails[:limit]
            
            # Cache the result (24 hour TTL)
            await cache_service.set(cache_key, result, ttl_seconds=86400)
            
            return result

        except Exception as e:
            logger.error(f"Failed to query MTB trails from OSM: {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def find_gravel_roads(
        self,
        location: Coordinate,
        radius_km: float = 10,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find gravel and unpaved roads near location.

        Args:
            location: Center point
            radius_km: Search radius in km
            limit: Max number of roads to return

        Returns:
            List of road features with coordinates
        """
        # Check cache
        cache_service = await get_cache_service()
        cache_key = cache_service._make_key(
            "trail_db:gravel",
            lat=location.lat,
            lng=location.lng,
            radius=radius_km,
            limit=limit,
        )
        cached = await cache_service.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for gravel roads at {location.lat},{location.lng}")
            return cached
        
        bbox = self._create_bbox_from_center(location, radius_km)

        # Overpass QL query for gravel roads
        # Searches for roads with gravel/compacted/dirt/unpaved surfaces
        query = f"""
[out:json][timeout:25];
(
  // Gravel surfaced roads
  way["highway"]["surface"="gravel"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"]["surface"="compacted"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"]["surface"="fine_gravel"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});

  // Unpaved roads
  way["highway"]["surface"="unpaved"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"]["surface"="dirt"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});

  // Tracks (often gravel/dirt)
  way["highway"="track"]["tracktype"~"grade1|grade2"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
);
out geom;
"""

        try:
            response = await self.client.post(
                self.overpass_url,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()

            data = response.json()
            roads = self._parse_overpass_response(data, "gravel")

            logger.info(f"Found {len(roads)} gravel roads within {radius_km}km of location")

            # Limit results
            result = roads[:limit]
            
            # Cache the result
            await cache_service.set(cache_key, result, ttl_seconds=86400)
            
            return result

        except Exception as e:
            logger.error(f"Failed to query gravel roads from OSM: {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def find_paved_roads(
        self,
        location: Coordinate,
        radius_km: float = 10,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find paved roads suitable for road cycling near location.

        Args:
            location: Center point
            radius_km: Search radius in km
            limit: Max number of roads to return

        Returns:
            List of road features with coordinates
        """
        bbox = self._create_bbox_from_center(location, radius_km)

        # Overpass QL query for paved roads
        query = f"""
[out:json][timeout:25];
(
  // Paved roads suitable for cycling
  way["highway"~"cycleway|path"]["surface"~"paved|asphalt|concrete"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"~"residential|tertiary|secondary|primary"]["surface"~"paved|asphalt|concrete"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});

  // Bike-friendly roads even without explicit surface tag
  way["highway"="cycleway"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
  way["highway"]["bicycle"="designated"]({bbox.min_lat},{bbox.min_lng},{bbox.max_lat},{bbox.max_lng});
);
out geom;
"""

        try:
            response = await self.client.post(
                self.overpass_url,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()

            data = response.json()
            roads = self._parse_overpass_response(data, "paved")

            logger.info(f"Found {len(roads)} paved roads within {radius_km}km of location")

            # Limit results
            return roads[:limit]

        except Exception as e:
            logger.error(f"Failed to query paved roads from OSM: {e}")
            return []

    def _parse_overpass_response(
        self,
        data: Dict[str, Any],
        feature_type: str,
    ) -> List[Dict[str, Any]]:
        """Parse Overpass API response into trail/road features.

        Args:
            data: Raw Overpass API response
            feature_type: Type of feature (mtb, gravel, paved)

        Returns:
            List of parsed features
        """
        features = []

        for element in data.get("elements", []):
            if element.get("type") != "way":
                continue

            # Extract geometry (list of lat/lng coordinates)
            geometry = []
            if "geometry" in element:
                geometry = [
                    {"lat": node["lat"], "lng": node["lon"]}
                    for node in element["geometry"]
                ]

            # Skip if no geometry
            if not geometry:
                continue

            # Extract relevant tags
            tags = element.get("tags", {})

            feature = {
                "id": element.get("id"),
                "type": feature_type,
                "name": tags.get("name", f"Unnamed {feature_type}"),
                "geometry": geometry,
                "tags": {
                    "highway": tags.get("highway"),
                    "surface": tags.get("surface"),
                    "bicycle": tags.get("bicycle"),
                    "mtb_scale": tags.get("mtb:scale"),
                    "mtb_type": tags.get("mtb:type"),
                    "sac_scale": tags.get("sac_scale"),
                    "tracktype": tags.get("tracktype"),
                },
                "length_meters": self._estimate_length(geometry),
            }

            features.append(feature)

        return features

    def _estimate_length(self, geometry: List[Dict[str, float]]) -> float:
        """Estimate length of a trail/road in meters using Haversine distance.

        Args:
            geometry: List of coordinate dicts with lat/lng

        Returns:
            Estimated length in meters
        """
        if len(geometry) < 2:
            return 0

        import math

        total_length = 0
        for i in range(len(geometry) - 1):
            lat1 = geometry[i]["lat"]
            lng1 = geometry[i]["lng"]
            lat2 = geometry[i + 1]["lat"]
            lng2 = geometry[i + 1]["lng"]

            # Haversine distance
            R = 6371000  # Earth radius in meters
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lng2 - lng1)

            a = (
                math.sin(delta_phi / 2) ** 2 +
                math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

            total_length += R * c

        return total_length

    async def find_suitable_trails(
        self,
        location: Coordinate,
        sport_type: SportType,
        radius_km: float = 10,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find trails/roads suitable for the specified sport type.

        Args:
            location: Center point
            sport_type: Type of cycling (MTB, GRAVEL, ROAD)
            radius_km: Search radius in km
            limit: Max results

        Returns:
            List of suitable trails/roads
        """
        if sport_type == SportType.MTB:
            return await self.find_mtb_trails(location, radius_km, limit)
        elif sport_type == SportType.GRAVEL:
            return await self.find_gravel_roads(location, radius_km, limit)
        elif sport_type == SportType.ROAD:
            return await self.find_paved_roads(location, radius_km, limit)
        else:
            logger.warning(f"Unknown sport type: {sport_type}, defaulting to paved roads")
            return await self.find_paved_roads(location, radius_km, limit)

    def select_waypoints_from_trails(
        self,
        trails: List[Dict[str, Any]],
        start_location: Coordinate,
        target_distance_km: float = 20,
        num_waypoints: int = 4,
        strategy: Optional[str] = None,
    ) -> List[Coordinate]:
        """Select strategic waypoints from trail network to create a route.

        Enhanced strategy:
        1. Find trails closest to start location
        2. Select waypoints distributed around start to form a loop
        3. Prioritize based on strategy type (classic, explorer, hidden_gem)
        4. Ensure waypoints are spaced appropriately for target distance
        5. Create more natural loop shapes

        Args:
            trails: List of trail features from OSM
            start_location: Starting point
            target_distance_km: Desired route distance
            num_waypoints: Number of waypoints to place
            strategy: Route generation strategy (classic, explorer, hidden_gem)

        Returns:
            List of waypoint coordinates
        """
        if not trails:
            logger.warning("No trails found, cannot select waypoints")
            return []

        import math

        # Calculate distance from start to each trail
        trails_with_distance = []
        for trail in trails:
            if not trail.get("geometry"):
                continue

            # Find closest point on trail to start
            min_dist = float('inf')
            closest_point = None

            for point in trail["geometry"]:
                dist = self._haversine_distance(
                    start_location.lat, start_location.lng,
                    point["lat"], point["lng"]
                )
                if dist < min_dist:
                    min_dist = dist
                    closest_point = point

            if closest_point:
                trails_with_distance.append({
                    "trail": trail,
                    "distance_from_start": min_dist,
                    "closest_point": closest_point,
                })

        # Sort by distance from start
        trails_with_distance.sort(key=lambda x: x["distance_from_start"])

        # Select waypoints from different bearings to form a loop
        waypoints = []

        # Strategy: Divide circle into sectors, pick one trail from each sector
        num_sectors = num_waypoints
        sector_size = 360 / num_sectors

        for sector_idx in range(num_sectors):
            sector_start = sector_idx * sector_size
            sector_end = (sector_idx + 1) * sector_size

            # Find trails in this bearing sector
            sector_trails = []
            for item in trails_with_distance:
                point = item["closest_point"]
                bearing = self._calculate_bearing(
                    start_location.lat, start_location.lng,
                    point["lat"], point["lng"]
                )

                # Normalize bearing to 0-360
                bearing = (bearing + 360) % 360

                if sector_start <= bearing < sector_end:
                    sector_trails.append(item)

            # Pick the best trail in this sector (prioritize based on strategy)
            if sector_trails:
                # Score trails based on strategy
                for item in sector_trails:
                    trail = item["trail"]
                    score = trail.get("length_meters", 0)
                    
                    # Strategy-specific scoring
                    if strategy == "classic":
                        # Classic: prioritize named, popular, longer trails
                        if trail.get("name") and "Unnamed" not in trail["name"]:
                            score += 10000  # Large bonus for named trails
                        # Prefer trails with higher confidence (from ingredients)
                        confidence = trail.get("confidence", 0.5)
                        score += confidence * 5000
                    elif strategy == "explorer":
                        # Explorer: prioritize longer trails, less common ones
                        score += trail.get("length_meters", 0) * 0.5  # Length matters more
                        # Slight penalty for very common trails
                        if trail.get("confidence", 0.5) > 0.8:
                            score *= 0.8
                    elif strategy == "hidden_gem":
                        # Hidden gem: prefer medium confidence, named but less popular
                        if trail.get("name") and "Unnamed" not in trail["name"]:
                            score += 3000  # Moderate bonus for named
                        # Prefer trails with medium confidence (0.4-0.7)
                        confidence = trail.get("confidence", 0.5)
                        if 0.4 <= confidence <= 0.7:
                            score += 2000
                    else:
                        # Default: balanced approach
                        if trail.get("name") and "Unnamed" not in trail["name"]:
                            score += 5000
                    
                    item["score"] = score

                sector_trails.sort(key=lambda x: x["score"], reverse=True)
                best_trail = sector_trails[0]

                # Select waypoint from trail - improved selection
                geometry = best_trail["trail"]["geometry"]
                if not geometry:
                    continue
                
                # For better loop shapes, select waypoint based on distance from start
                # Aim for waypoints at ~40% of target distance from start
                target_waypoint_distance = (target_distance_km * 0.4) * 1000  # meters
                
                best_point = None
                best_distance_diff = float('inf')
                
                # Sample points along the trail
                sample_step = max(1, len(geometry) // 10)  # Sample ~10 points
                for idx in range(0, len(geometry), sample_step):
                    point = geometry[idx]
                    point_coord = Coordinate(lat=point["lat"], lng=point["lng"])
                    distance = self._haversine_distance(
                        start_location.lat, start_location.lng,
                        point_coord.lat, point_coord.lng
                    )
                    distance_diff = abs(distance - target_waypoint_distance)
                    
                    if distance_diff < best_distance_diff:
                        best_distance_diff = distance_diff
                        best_point = point_coord
                
                # If no good match found, use midpoint
                if not best_point:
                    mid_idx = len(geometry) // 2
                    mid_point = geometry[mid_idx]
                    best_point = Coordinate(lat=mid_point["lat"], lng=mid_point["lng"])

                waypoints.append(best_point)

        logger.info(f"Selected {len(waypoints)} waypoints from {len(trails)} trails")

        return waypoints

    def _calculate_bearing(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float,
    ) -> float:
        """Calculate bearing from point 1 to point 2 in degrees."""
        import math

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lng = math.radians(lng2 - lng1)

        x = math.sin(delta_lng) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - \
            math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lng)

        bearing = math.atan2(x, y)
        bearing_deg = math.degrees(bearing)

        return bearing_deg

    def _haversine_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float,
    ) -> float:
        """Calculate distance between two points in meters."""
        import math

        R = 6371000  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = (
            math.sin(delta_phi / 2) ** 2 +
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c


# Singleton
_trail_database: Optional[TrailDatabaseService] = None


async def get_trail_database() -> TrailDatabaseService:
    """Get or create trail database service instance."""
    global _trail_database
    if _trail_database is None:
        _trail_database = TrailDatabaseService()
    return _trail_database
