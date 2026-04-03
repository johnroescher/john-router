"""Routing service for generating cycling routes."""
import math
import random
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
import httpx
import polyline
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.schemas.route import (
    RouteConstraints,
    SportType,
    RouteType,
    MTBDifficulty,
    RoutingService as RoutingServiceType,
    SegmentedSurfaceData,
    SurfaceSegment,
    SurfaceQualityMetrics,
)
from app.schemas.common import Coordinate, GeoJSONLineString
import structlog

logger = structlog.get_logger()

# Highway filters for detecting road vs trail networks
TRAIL_HIGHWAY_FILTER = "path|track|cycleway|bridleway|footway|trail"
ROAD_HIGHWAY_FILTER = "residential|unclassified|tertiary|secondary|primary|trunk|motorway|service"


class RoutingService:
    """Service for generating cycling routes using external routing APIs.

    Uses BRouter for MTB/gravel/trail routing (better path support)
    Uses OpenRouteService for road cycling
    """

    # OpenRouteService profile mapping (used for road cycling)
    ORS_PROFILES = {
        # Use driving-car for shortest road routing (cycling profiles bias away from highways)
        SportType.ROAD: "driving-car",
        SportType.GRAVEL: "cycling-regular",
        SportType.MTB: "cycling-mountain",
        SportType.EMTB: "cycling-electric",
    }

    # BRouter profile mapping (better for trails/paths)
    BROUTER_PROFILES = {
        SportType.ROAD: "fastbike",
        SportType.GRAVEL: "trekking",
        SportType.MTB: "mtb",
        SportType.EMTB: "mtb",
    }

    GRAPHOPPER_PROFILES = {
        SportType.ROAD: "bike",
        SportType.GRAVEL: "bike",
        SportType.MTB: "mtb",
        SportType.EMTB: "mtb",
    }

    VALHALLA_PROFILES = {
        SportType.ROAD: "bicycle",
        SportType.GRAVEL: "bicycle",
        SportType.MTB: "bicycle",
        SportType.EMTB: "bicycle",
    }

    VALHALLA_POLYLINE_PRECISION = 6

    VALHALLA_PAVED_SURFACES = {
        "paved", "paved_smooth", "paved_rough", "paved_good", "paved_fair",
        "asphalt", "concrete", "paving_stones", "cobblestone", "sett", "chipseal",
    }
    VALHALLA_GRAVEL_SURFACES = {
        "gravel", "fine_gravel", "pebblestone", "compacted", "crushed_limestone",
    }
    VALHALLA_GROUND_SURFACES = {
        "dirt", "earth", "ground", "mud", "sand", "grass", "soil", "clay", "wood", "woodchips",
    }
    VALHALLA_UNPAVED_SURFACES = {"unpaved"}
    VALHALLA_TRAIL_USES = {
        "path", "track", "footway", "bridleway", "cycleway", "trail", "mountain_bike",
    }

    # MTB difficulty to avoid features mapping
    MTB_DIFFICULTY_AVOID = {
        MTBDifficulty.EASY: ["fords", "steps"],
        MTBDifficulty.MODERATE: ["fords"],
        MTBDifficulty.HARD: [],
        MTBDifficulty.VERY_HARD: [],
    }

    def __init__(self):
        self.ors_api_key = settings.ors_api_key
        self.graphhopper_api_key = settings.graphhopper_api_key
        self.valhalla_api_key = settings.valhalla_api_key
        self.ors_base_url = "https://api.openrouteservice.org/v2"
        self.brouter_base_url = "https://brouter.de/brouter"
        self.graphhopper_base_url = "https://graphhopper.com/api/1"
        self.valhalla_base_url = settings.valhalla_base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=60.0)  # Increased timeout for BRouter
        self.interactive_timeout = httpx.Timeout(4.0)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_ors_directions(
        self,
        coordinates: List[List[float]],
        profile: str,
        options: Optional[Dict[str, Any]] = None,
        preference: str = "shortest",
    ) -> Dict[str, Any]:
        """Call OpenRouteService directions API."""
        if not self.ors_api_key:
            raise ValueError("ORS_API_KEY not configured")

        url = f"{self.ors_base_url}/directions/{profile}/geojson"
        headers = {
            "Authorization": self.ors_api_key,
            "Content-Type": "application/json",
        }

        body = {
            "coordinates": coordinates,
            "elevation": True,
            "instructions": True,
            "extra_info": ["surface", "steepness"],
            "preference": preference,
        }

        if options:
            body["options"] = options

        logger.info(f"Calling ORS: {profile} with {len(coordinates)} coordinates")

        response = await self.client.post(url, json=body, headers=headers)

        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"ORS API error {response.status_code}: {error_detail}")

        response.raise_for_status()
        return response.json()

    async def _call_ors_directions_interactive(
        self,
        coordinates: List[List[float]],
        profile: str,
        options: Optional[Dict[str, Any]] = None,
        preference: str = "shortest",
    ) -> Dict[str, Any]:
        """Call OpenRouteService directions API with shorter timeout."""
        if not self.ors_api_key:
            raise ValueError("ORS_API_KEY not configured")

        url = f"{self.ors_base_url}/directions/{profile}/geojson"
        headers = {
            "Authorization": self.ors_api_key,
            "Content-Type": "application/json",
        }
        body = {
            "coordinates": coordinates,
            "elevation": True,
            "instructions": True,
            "extra_info": ["surface", "steepness"],
            "preference": preference,
        }
        if options:
            body["options"] = options

        logger.info(f"Calling ORS (interactive): {profile} with {len(coordinates)} coordinates")
        response = await self.client.post(url, json=body, headers=headers, timeout=self.interactive_timeout)
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"ORS API error {response.status_code}: {error_detail}")
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_brouter(
        self,
        coordinates: List[List[float]],
        profile: str,
    ) -> Dict[str, Any]:
        """Call BRouter API for trail-aware routing.

        BRouter is better for MTB/gravel as it routes on paths, trails, and tracks
        that ORS may not prioritize.
        """
        # BRouter expects lon,lat pairs separated by |
        lonlats = "|".join([f"{coord[0]},{coord[1]}" for coord in coordinates])

        params = {
            "lonlats": lonlats,
            "profile": profile,
            "alternativeidx": 0,
            "format": "geojson",
        }

        logger.info(f"Calling BRouter: {profile} with {len(coordinates)} coordinates")

        response = await self.client.get(self.brouter_base_url, params=params)

        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"BRouter API error {response.status_code}: {error_detail}")
            response.raise_for_status()

        data = response.json()

        # Log response structure for debugging
        if data.get("features"):
            feature = data["features"][0]
            props = feature.get("properties", {})
            logger.info(f"BRouter response: distance={props.get('track-length')}m, time={props.get('total-time')}s")
        else:
            logger.warning(f"BRouter response has no features: {str(data)[:200]}")

        return data

    async def _call_brouter_interactive(
        self,
        coordinates: List[List[float]],
        profile: str,
    ) -> Dict[str, Any]:
        """Call BRouter API with shorter timeout (interactive)."""
        lonlats = "|".join([f"{coord[0]},{coord[1]}" for coord in coordinates])
        params = {
            "lonlats": lonlats,
            "profile": profile,
            "alternativeidx": 0,
            "format": "geojson",
        }
        logger.info(f"Calling BRouter (interactive): {profile} with {len(coordinates)} coordinates")
        response = await self.client.get(self.brouter_base_url, params=params, timeout=self.interactive_timeout)
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"BRouter API error {response.status_code}: {error_detail}")
            response.raise_for_status()
        data = response.json()
        if data.get("features"):
            feature = data["features"][0]
            props = feature.get("properties", {})
            logger.info(f"BRouter response: distance={props.get('track-length')}m, time={props.get('total-time')}s")
        else:
            logger.warning(f"BRouter response has no features: {str(data)[:200]}")
        return data

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=1, max=4),
        retry=retry_if_exception_type(httpx.HTTPError),
    )
    async def _call_graphhopper_route(
        self,
        coordinates: List[List[float]],
        profile: str,
    ) -> Dict[str, Any]:
        """Call GraphHopper Routing API for fast trail routing."""
        if not self.graphhopper_api_key:
            raise ValueError("GRAPHOPPER_API_KEY not configured")

        url = f"{self.graphhopper_base_url}/route"
        headers = {
            "Content-Type": "application/json",
        }
        params = {"key": self.graphhopper_api_key}
        body = {
            "profile": profile,
            "points": coordinates,
            "points_encoded": False,
            "instructions": False,
            "elevation": False,
            "weighting": "shortest",
        }

        logger.info(f"Calling GraphHopper: {profile} with {len(coordinates)} coordinates")
        response = await self.client.post(url, json=body, headers=headers, params=params)
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"GraphHopper API error {response.status_code}: {error_detail}")
        response.raise_for_status()
        return response.json()

    async def _call_graphhopper_route_interactive(
        self,
        coordinates: List[List[float]],
        profile: str,
    ) -> Dict[str, Any]:
        """Call GraphHopper Routing API with shorter timeout (interactive)."""
        if not self.graphhopper_api_key:
            raise ValueError("GRAPHOPPER_API_KEY not configured")

        url = f"{self.graphhopper_base_url}/route"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.graphhopper_api_key}
        body = {
            "profile": profile,
            "points": coordinates,
            "points_encoded": False,
            "instructions": False,
            "elevation": False,
            "weighting": "shortest",
        }

        logger.info(f"Calling GraphHopper (interactive): {profile} with {len(coordinates)} coordinates")
        response = await self.client.post(url, json=body, headers=headers, params=params, timeout=self.interactive_timeout)
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"GraphHopper API error {response.status_code}: {error_detail}")
        response.raise_for_status()
        return response.json()

    def _valhalla_headers(self) -> Dict[str, str]:
        if not self.valhalla_api_key:
            raise ValueError("VALHALLA_API_KEY not configured")
        return {
            "Authorization": f"Stadia-Auth {self.valhalla_api_key}",
            "Content-Type": "application/json",
        }

    def _valhalla_params(self) -> Dict[str, str]:
        if not self.valhalla_api_key:
            raise ValueError("VALHALLA_API_KEY not configured")
        return {"api_key": self.valhalla_api_key}

    def _encode_polyline(self, coordinates: List[List[float]]) -> str:
        lat_lon = [(coord[1], coord[0]) for coord in coordinates]
        return polyline.encode(lat_lon, precision=self.VALHALLA_POLYLINE_PRECISION)

    def _decode_polyline(self, encoded: str) -> List[List[float]]:
        lat_lon = polyline.decode(encoded, precision=self.VALHALLA_POLYLINE_PRECISION)
        return [[lng, lat] for lat, lng in lat_lon]

    def _normalize_valhalla_surface(self, surface: Any) -> Optional[str]:
        if surface is None:
            return None
        if isinstance(surface, str):
            return surface.strip().lower()
        if isinstance(surface, (int, float)):
            # Unknown numeric surface mapping; treat as unknown to avoid misclassification.
            return None
        return None

    def _normalize_valhalla_use(self, use: Any) -> Optional[str]:
        if use is None:
            return None
        if isinstance(use, str):
            return use.strip().lower()
        return None

    def _coerce_bool(self, value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return None

    def _map_valhalla_edge_surface(self, edge: Dict[str, Any]) -> Tuple[str, str, float]:
        surface_raw = edge.get("surface")
        unpaved_raw = edge.get("unpaved")
        use_raw = edge.get("use")

        surface = self._normalize_valhalla_surface(surface_raw)
        unpaved = self._coerce_bool(unpaved_raw)
        use = self._normalize_valhalla_use(use_raw)

        base_surface = "unknown"
        confidence = 0.3

        if surface in self.VALHALLA_PAVED_SURFACES or (surface and surface.startswith("paved")):
            base_surface = "paved"
            confidence = 0.9
        elif surface in self.VALHALLA_GRAVEL_SURFACES:
            base_surface = "gravel"
            confidence = 0.9
        elif surface in self.VALHALLA_GROUND_SURFACES:
            base_surface = "ground"
            confidence = 0.9
        elif surface in self.VALHALLA_UNPAVED_SURFACES:
            base_surface = "unpaved"
            confidence = 0.8
        elif unpaved is True:
            base_surface = "unpaved"
            confidence = 0.7

        if base_surface == "unknown" and unpaved is False:
            base_surface = "paved"
            confidence = max(confidence, 0.6)

        if base_surface == "unknown" and use in self.VALHALLA_TRAIL_USES:
            base_surface = "unpaved"
            confidence = max(confidence, 0.6)

        if base_surface in {"unpaved", "ground"} and use in self.VALHALLA_TRAIL_USES:
            detailed_surface = "singletrack"
        elif base_surface == "paved":
            detailed_surface = "pavement"
        elif base_surface == "gravel":
            detailed_surface = "gravel"
        elif base_surface in {"unpaved", "ground"}:
            detailed_surface = "dirt"
        else:
            detailed_surface = "unknown"
            if use in self.VALHALLA_TRAIL_USES:
                detailed_surface = "singletrack"
                confidence = max(confidence, 0.6)

        return detailed_surface, base_surface, confidence

    def _calculate_cumulative_distances(self, geometry: List[List[float]]) -> List[float]:
        cumulative = [0.0]
        total = 0.0
        for i in range(1, len(geometry)):
            total += self._haversine_distance(
                geometry[i - 1][1], geometry[i - 1][0],
                geometry[i][1], geometry[i][0],
            )
            cumulative.append(total)
        return cumulative

    def _index_for_distance(self, cumulative: List[float], target_distance: float, start_idx: int = 0) -> int:
        idx = start_idx
        while idx < len(cumulative) - 1 and cumulative[idx] < target_distance:
            idx += 1
        return idx

    async def _call_valhalla_route(
        self,
        coordinates: List[List[float]],
        profile: str,
    ) -> Dict[str, Any]:
        """Call Valhalla route API via Stadia Maps."""
        url = f"{self.valhalla_base_url}/route/v1"
        locations = []
        for idx, coord in enumerate(coordinates):
            loc = {"lat": coord[1], "lon": coord[0]}
            if idx == 0 or idx == len(coordinates) - 1:
                loc["type"] = "break"
            else:
                loc["type"] = "via"
            locations.append(loc)

        body = {
            "locations": locations,
            "costing": profile,
            "shape_format": "polyline6",
            "directions_options": {"units": "kilometers"},
        }

        headers = self._valhalla_headers()
        logger.info(f"Calling Valhalla: {profile} with {len(coordinates)} coordinates")
        response = await self.client.post(url, json=body, headers=headers, params=self._valhalla_params())
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"Valhalla route API error {response.status_code}: {error_detail}")
        response.raise_for_status()
        return response.json()

    async def _call_valhalla_trace_attributes(
        self,
        coordinates: List[List[float]],
        profile: str,
        shape_match: str = "map_snap",
        use_shape: bool = False,
    ) -> Dict[str, Any]:
        """Call Valhalla trace_attributes API via Stadia Maps."""
        url = f"{self.valhalla_base_url}/trace_attributes/v1"
        body = {
            "id": "surface_trace",
            "shape_match": shape_match,
            "costing": profile,
        }
        if use_shape:
            body["shape"] = [{"lat": coord[1], "lon": coord[0]} for coord in coordinates]
        else:
            encoded = self._encode_polyline(coordinates)
            body["encoded_polyline"] = encoded
            body["shape_format"] = "polyline6"
        headers = self._valhalla_headers()
        response = await self.client.post(url, json=body, headers=headers, params=self._valhalla_params())
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "No response body"
            logger.error(f"Valhalla trace_attributes API error {response.status_code}: {error_detail}")
        response.raise_for_status()
        return response.json()

    def _parse_valhalla_route_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Valhalla route response into standardized format."""
        trip = response.get("trip")
        if not trip:
            raise ValueError("No trip found in Valhalla response")

        legs = trip.get("legs", [])
        if not legs:
            raise ValueError("No legs found in Valhalla response")

        decoded_coords: List[List[float]] = []
        for leg in legs:
            shape = leg.get("shape")
            if not shape:
                continue
            leg_coords = self._decode_polyline(shape)
            if decoded_coords:
                decoded_coords.extend(leg_coords[1:])
            else:
                decoded_coords.extend(leg_coords)

        summary = trip.get("summary", {}) or {}
        distance_km = summary.get("length", 0) or 0
        distance_meters = float(distance_km) * 1000
        duration_seconds = float(summary.get("time", 0) or 0)

        return {
            "geometry": {
                "type": "LineString",
                "coordinates": decoded_coords,
            },
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "elevation_gain": self._calculate_elevation_gain(decoded_coords),
            "elevation_loss": self._calculate_elevation_loss(decoded_coords),
            "segments": [],
            "surface_breakdown": {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100},
            "surface_info": {},
            "instructions": [],
            "source": "valhalla",
        }

    def _build_segmented_surface_data(
        self,
        geometry: List[List[float]],
        segments: List[SurfaceSegment],
        known_distance: float,
        confidence_sum: float,
    ) -> SegmentedSurfaceData:
        total_distance = self._calculate_cumulative_distances(geometry)[-1] if geometry else 0.0
        if total_distance > 0:
            known_distance = min(known_distance, total_distance)
            coverage_percent = min(100.0, (known_distance / total_distance) * 100)
        else:
            coverage_percent = 0.0

        avg_confidence = (confidence_sum / known_distance) if known_distance > 0 else 0.0

        return SegmentedSurfaceData(
            segments=segments,
            knownDistanceMeters=known_distance,
            totalDistanceMeters=total_distance,
            dataQuality=coverage_percent,
            qualityMetrics=SurfaceQualityMetrics(
                coveragePercent=coverage_percent,
                avgConfidence=avg_confidence,
                avgMatchDistanceMeters=None,
            ),
            lastUpdated=datetime.now(timezone.utc).isoformat(),
            enrichmentSource="routing_api",
        )

    def _parse_valhalla_trace_attributes(
        self,
        response: Dict[str, Any],
        geometry: List[List[float]],
    ) -> Tuple[SegmentedSurfaceData, Dict[str, float]]:
        edges = response.get("edges", []) or []
        if not edges:
            unknown_segment = SurfaceSegment(
                startIndex=0,
                endIndex=max(0, len(geometry) - 1),
                startDistanceMeters=0.0,
                endDistanceMeters=self._calculate_cumulative_distances(geometry)[-1] if geometry else 0.0,
                distanceMeters=self._calculate_cumulative_distances(geometry)[-1] if geometry else 0.0,
                surfaceType="unknown",
                confidence=0.0,
                matchDistanceMeters=None,
                source="routing_api",
            )
            segmented = self._build_segmented_surface_data(
                geometry,
                [unknown_segment],
                known_distance=0.0,
                confidence_sum=0.0,
            )
            return segmented, {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}

        cumulative = self._calculate_cumulative_distances(geometry)
        total_distance = cumulative[-1] if cumulative else 0.0

        segments: List[SurfaceSegment] = []
        current: Optional[SurfaceSegment] = None
        known_distance = 0.0
        confidence_sum = 0.0
        breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 0}

        running_distance = 0.0
        current_index = 0

        for edge in edges:
            edge_length_km = edge.get("length", 0) or 0
            edge_length = float(edge_length_km) * 1000
            if edge_length <= 0:
                continue

            start_distance = running_distance
            end_distance = min(running_distance + edge_length, total_distance)
            start_idx = self._index_for_distance(cumulative, start_distance, current_index)
            end_idx = self._index_for_distance(cumulative, end_distance, start_idx)
            current_index = end_idx
            running_distance = end_distance

            detailed_surface, base_surface, confidence = self._map_valhalla_edge_surface(edge)
            
            # Log edge surface mapping for debugging
            if edge.get("surface") or edge.get("unpaved") is not None:
                logger.debug(
                    "valhalla_edge_surface_mapping",
                    edge_surface=edge.get("surface"),
                    edge_unpaved=edge.get("unpaved"),
                    edge_use=edge.get("use"),
                    mapped_detailed=detailed_surface,
                    mapped_base=base_surface,
                    confidence=confidence,
                    edge_length_m=round(edge_length, 1),
                )

            segment = SurfaceSegment(
                startIndex=start_idx,
                endIndex=end_idx,
                startDistanceMeters=start_distance,
                endDistanceMeters=end_distance,
                distanceMeters=max(0.0, end_distance - start_distance),
                surfaceType=detailed_surface,
                confidence=confidence,
                matchDistanceMeters=None,
                source="routing_api",
            )

            if current and current.surfaceType == segment.surfaceType:
                current.endIndex = segment.endIndex
                current.endDistanceMeters = segment.endDistanceMeters
                current.distanceMeters += segment.distanceMeters
                current.confidence = max(current.confidence, segment.confidence)
            else:
                if current:
                    segments.append(current)
                current = segment

            if detailed_surface != "unknown":
                known_distance += segment.distanceMeters
                confidence_sum += confidence * segment.distanceMeters

            breakdown[base_surface] += segment.distanceMeters

        if current:
            segments.append(current)

        if total_distance > 0:
            for key in breakdown:
                breakdown[key] = (breakdown[key] / total_distance) * 100
        else:
            breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}

        logger.info(
            "valhalla_surface_breakdown_calculated",
            total_distance_m=round(total_distance, 1),
            known_distance_m=round(known_distance, 1),
            breakdown_raw=breakdown,
            segments_count=len(segments),
            coverage_pct=round((known_distance / total_distance * 100) if total_distance > 0 else 0, 1),
        )

        segmented = self._build_segmented_surface_data(
            geometry,
            segments,
            known_distance=known_distance,
            confidence_sum=confidence_sum,
        )

        return segmented, breakdown

    async def _get_valhalla_surface_data(
        self,
        geometry: List[List[float]],
        profile: str,
    ) -> Tuple[SegmentedSurfaceData, Dict[str, float]]:
        try:
            trace = await self._call_valhalla_trace_attributes(geometry, profile, shape_match="map_snap")
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 400:
                try:
                    trace = await self._call_valhalla_trace_attributes(geometry, profile, shape_match="walk_or_snap")
                except httpx.HTTPStatusError:
                    trace = await self._call_valhalla_trace_attributes(
                        geometry,
                        profile,
                        shape_match="walk_or_snap",
                        use_shape=True,
                    )
            else:
                raise
        return self._parse_valhalla_trace_attributes(trace, geometry)

    async def _attach_valhalla_surface(
        self,
        route: Dict[str, Any],
        profile: str,
    ) -> Dict[str, Any]:
        if not self.valhalla_api_key:
            logger.debug("valhalla_surface_attach_skipped", reason="no_api_key")
            return route
        geometry = route.get("geometry", {}).get("coordinates", [])
        if not geometry:
            logger.debug("valhalla_surface_attach_skipped", reason="no_geometry")
            return route
        try:
            logger.info(
                "valhalla_surface_attach_start",
                geometry_points=len(geometry),
                profile=profile,
            )
            segmented, breakdown = await self._get_valhalla_surface_data(geometry, profile)
            logger.info(
                "valhalla_surface_attach_success",
                segments_count=len(segmented.segments),
                breakdown=breakdown,
                data_quality=segmented.dataQuality,
                enrichment_source=segmented.enrichmentSource,
            )
            route["surface_breakdown"] = breakdown
            route["surface_info"] = {"source": "valhalla_trace"}
            # Convert Pydantic model to dict for JSON serialization
            try:
                route["segmented_surface"] = segmented.model_dump()
            except AttributeError:
                # Fallback for Pydantic v1
                route["segmented_surface"] = segmented.dict()
        except Exception as exc:
            logger.warning(
                "valhalla_surface_attach_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return route

    def _parse_brouter_response(self, data: Dict[str, Any], profile: str = "trekking") -> Dict[str, Any]:
        """Parse BRouter GeoJSON response into our standard format."""
        if not data.get("features"):
            logger.error(f"BRouter response has no features. Keys: {data.keys()}")
            if "error" in str(data).lower():
                logger.error(f"BRouter error response: {str(data)[:500]}")
            raise ValueError("No route found in BRouter response")

        feature = data["features"][0]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        logger.debug(f"BRouter properties keys: {properties.keys()}")

        # Extract coordinates (BRouter returns [lon, lat, elevation])
        coordinates = geometry.get("coordinates", [])

        # BRouter provides track-length in meters, total-time in seconds
        distance_meters = float(properties.get("track-length", 0))
        duration_seconds = float(properties.get("total-time", 0))

        # Calculate elevation from coordinates if available
        elevations = [c[2] for c in coordinates if len(c) > 2]
        elevation_gain = 0
        if elevations:
            for i in range(1, len(elevations)):
                diff = elevations[i] - elevations[i-1]
                if diff > 0:
                    elevation_gain += diff

        # Parse surface data from BRouter messages
        # BRouter messages format: [lon, lat, elevation, distance, time, message]
        # Message contains surface info like "unpaved" or surface type
        surface_segments = []
        messages = properties.get("messages", [])

        # BRouter messages contain waypoint info with surface
        # Format varies but typically includes surface in the message text
        surface_breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 0}

        # Estimate surface from profile and route characteristics
        # BRouter doesn't always give detailed surface, so we estimate based on profile
        if messages:
            # Try to parse messages for surface hints
            # Skip header rows and handle various formats defensively
            for msg in messages:
                try:
                    if isinstance(msg, list) and len(msg) > 5:
                        # Skip if msg[3] looks like a header (non-numeric)
                        dist_val = msg[3]
                        if dist_val is None or (isinstance(dist_val, str) and not dist_val.replace('.', '').replace('-', '').isdigit()):
                            continue

                        msg_text = str(msg[5]).lower() if msg[5] else ""
                        segment_dist = float(dist_val)

                        if "paved" in msg_text or "asphalt" in msg_text:
                            surface_breakdown["paved"] += segment_dist
                        elif "gravel" in msg_text:
                            surface_breakdown["gravel"] += segment_dist
                        elif "unpaved" in msg_text or "track" in msg_text:
                            surface_breakdown["unpaved"] += segment_dist
                        elif "ground" in msg_text or "earth" in msg_text or "dirt" in msg_text:
                            surface_breakdown["ground"] += segment_dist
                        else:
                            surface_breakdown["unknown"] += segment_dist
                except (ValueError, TypeError, IndexError) as e:
                    # Skip malformed message entries
                    continue

        # Convert to percentages
        total_surface_dist = sum(surface_breakdown.values())
        known_surface_dist = total_surface_dist - surface_breakdown.get("unknown", 0)

        # CRITICAL FIX: Be strict about surface data quality
        # If we have insufficient surface data, mark it clearly as unknown
        # This will trigger validation failure and force alternative routes
        if known_surface_dist < total_surface_dist * 0.1:  # Less than 10% is known
            logger.warning(f"BRouter surface data insufficient: {known_surface_dist/total_surface_dist*100:.1f}% known")
            logger.warning("Marking route as having poor surface data (will trigger validation rejection)")
            # Don't use estimates - mark as unknown to fail validation
            surface_breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}
        elif total_surface_dist > 0:
            surface_breakdown = {k: (v / total_surface_dist) * 100 for k, v in surface_breakdown.items()}
            logger.info(f"BRouter surface data: {surface_breakdown}")
        else:
            # Fallback if no messages at all - mark as completely unknown
            logger.error("BRouter returned no surface messages - no surface data available")
            surface_breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}

        return {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "elevation_gain": elevation_gain,
            "surface_breakdown": surface_breakdown,
            "source": "brouter",
        }

    def _parse_graphhopper_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse GraphHopper response into our standard format."""
        paths = data.get("paths", [])
        if not paths:
            raise ValueError("No route found in GraphHopper response")

        path = paths[0]
        points = path.get("points", {})
        coordinates = points.get("coordinates", []) if isinstance(points, dict) else []

        distance_meters = float(path.get("distance", 0))
        duration_seconds = float(path.get("time", 0)) / 1000 if path.get("time") else 0
        elevation_gain = float(path.get("ascend", 0)) if path.get("ascend") is not None else 0
        elevation_loss = float(path.get("descend", 0)) if path.get("descend") is not None else 0

        surface_breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}
        return {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "elevation_gain": elevation_gain,
            "elevation_loss": elevation_loss,
            "segments": [],
            "surface_breakdown": surface_breakdown,
            "surface_info": {},
            "instructions": [],
            "source": "graphhopper",
        }

    def _build_ors_options(self, constraints: RouteConstraints, profile: str) -> Dict[str, Any]:
        """Build ORS options from constraints."""
        options = {}

        # Avoid highways when supported by the profile.
        # Some ORS profiles do not support avoid_features; skip when unsupported.
        avoid_features_supported = profile in {"driving-car", "cycling-regular", "cycling-mountain", "cycling-electric"}
        if constraints.avoid_highways and avoid_features_supported:
            options["avoid_features"] = ["highways"]

        # Avoid areas (polygons) - this should work for all profiles
        if constraints.avoid_areas:
            options["avoid_polygons"] = {
                "type": "MultiPolygon",
                "coordinates": [
                    [[coord.to_list() for coord in area] + [area[0].to_list()]]
                    for area in constraints.avoid_areas
                ],
            }

        return options if options else None

    async def _generate_direct_route_valhalla(
        self,
        constraints: RouteConstraints,
        profile: str,
    ) -> Dict[str, Any]:
        """Generate a direct point-to-point route using Valhalla."""
        coordinates = [constraints.start.to_list()]
        for via in constraints.via_points:
            coordinates.append(via.to_list())
        if constraints.end:
            coordinates.append(constraints.end.to_list())
        else:
            raise ValueError("End point required for point-to-point route")

        result = await self._call_valhalla_route(coordinates, profile)
        parsed = self._parse_valhalla_route_response(result)
        return await self._attach_valhalla_surface(parsed, profile)

    async def _generate_out_and_back_valhalla(
        self,
        constraints: RouteConstraints,
        profile: str,
    ) -> Dict[str, Any]:
        """Generate an out-and-back route using Valhalla."""
        target_distance = constraints.target_distance_meters or 16000
        one_way_distance = target_distance / 2

        bearing = random.uniform(0, 360)
        dest = self._point_at_distance(constraints.start, one_way_distance, bearing)

        coordinates = [constraints.start.to_list()]
        for via in constraints.via_points:
            coordinates.append(via.to_list())
        coordinates.append(dest.to_list())

        outbound = await self._call_valhalla_route(coordinates, profile)

        return_coords = [dest.to_list(), constraints.start.to_list()]
        inbound = await self._call_valhalla_route(return_coords, profile)

        combined = self._combine_routes(
            self._parse_valhalla_route_response(outbound),
            self._parse_valhalla_route_response(inbound),
        )
        return await self._attach_valhalla_surface(combined, profile)

    async def _generate_loop_candidates_valhalla(
        self,
        constraints: RouteConstraints,
        profile: str,
        num_candidates: int = 3,
    ) -> List[Dict[str, Any]]:
        """Generate loop route candidates using Valhalla."""
        candidates = []
        target_distance = constraints.target_distance_meters or 25000

        if target_distance > 60000:
            routing_overhead = 2.0
        elif target_distance > 40000:
            routing_overhead = 1.85
        else:
            routing_overhead = 1.7

        waypoint_distance = target_distance / 3 / routing_overhead
        starting_bearings = [45, 90, 135, 0, 180]

        for i, primary_bearing in enumerate(starting_bearings[:num_candidates * 2]):
            try:
                secondary_bearing = (primary_bearing + 110) % 360

                waypoint1 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    primary_bearing
                )
                waypoint2 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    secondary_bearing
                )

                coordinates = [
                    constraints.start.to_list(),
                    waypoint1.to_list(),
                    waypoint2.to_list(),
                    constraints.start.to_list()
                ]

                result = await self._call_valhalla_route(coordinates, profile)
                candidate = self._parse_valhalla_route_response(result)
                candidate = await self._attach_valhalla_surface(candidate, profile)
                candidate["candidate_index"] = i
                candidate["generation_params"] = {
                    "primary_bearing": primary_bearing,
                    "secondary_bearing": secondary_bearing,
                    "waypoint_distance": waypoint_distance,
                    "target_distance": target_distance,
                }
                candidates.append(candidate)
                if len(candidates) >= num_candidates:
                    return candidates
            except Exception as e:
                logger.warning(f"Failed to generate Valhalla loop candidate {i} (bearing={primary_bearing}): {e}")
                continue

        return candidates

    async def generate_route(
        self,
        constraints: RouteConstraints,
    ) -> List[Dict[str, Any]]:
        """Generate route candidates based on constraints.

        Uses BRouter for MTB/gravel (better trail support)
        Uses ORS for road cycling

        Returns a list of candidate routes with geometry and metadata.
        """
        logger.info(
            "=== ROUTE GENERATION START ===",
            route_type=constraints.route_type.value,
            sport_type=constraints.sport_type.value,
            target_distance_m=constraints.target_distance_meters,
            start_lat=constraints.start.lat,
            start_lng=constraints.start.lng,
            num_alternatives=constraints.num_alternatives,
            ors_api_key_configured=bool(self.ors_api_key),
            graphhopper_api_key_configured=bool(self.graphhopper_api_key),
            valhalla_api_key_configured=bool(self.valhalla_api_key),
        )

        original_constraints = constraints
        transition_plan = await self._build_transition_plan(constraints)
        if transition_plan:
            constraints = transition_plan["constraints"]
            logger.info(
                "transition_plan_applied",
                transition_segments=len(transition_plan.get("transition_segments", [])),
                start=constraints.start.model_dump() if hasattr(constraints.start, "model_dump") else None,
            )
        
        candidates = []

        # Decide which routing engine to use
        # BRouter is better for trails/paths (MTB, gravel)
        # ORS is fine for road cycling
        selected_service = constraints.routing_service or RoutingServiceType.AUTO
        use_brouter = constraints.sport_type in [SportType.MTB, SportType.GRAVEL, SportType.EMTB]

        if selected_service == RoutingServiceType.BROUTER:
            use_brouter = True
        elif selected_service == RoutingServiceType.ORS:
            use_brouter = False
        elif selected_service == RoutingServiceType.GRAPHOPPER:
            use_brouter = False
        elif selected_service == RoutingServiceType.VALHALLA:
            use_brouter = False

        brouter_profile = self.BROUTER_PROFILES.get(constraints.sport_type, "trekking")
        ors_profile = self.ORS_PROFILES.get(constraints.sport_type, "cycling-road")
        graphhopper_profile = self.GRAPHOPPER_PROFILES.get(constraints.sport_type, "bike")
        valhalla_profile = self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle")

        if constraints.routing_profile:
            if selected_service == RoutingServiceType.BROUTER:
                brouter_profile = constraints.routing_profile
            elif selected_service == RoutingServiceType.ORS:
                ors_profile = constraints.routing_profile
            elif selected_service == RoutingServiceType.GRAPHOPPER:
                graphhopper_profile = constraints.routing_profile
            elif selected_service == RoutingServiceType.VALHALLA:
                valhalla_profile = constraints.routing_profile

        ors_options = self._build_ors_options(constraints, ors_profile)

        if selected_service == RoutingServiceType.GRAPHOPPER:
            if not self.graphhopper_api_key:
                raise ValueError("GRAPHOPPER_API_KEY not configured")
            logger.info(f"Using GraphHopper with profile: {graphhopper_profile}")
        elif selected_service == RoutingServiceType.VALHALLA:
            if not self.valhalla_api_key:
                raise ValueError("VALHALLA_API_KEY not configured")
            logger.info(f"Using Valhalla with profile: {valhalla_profile}")
        elif use_brouter:
            logger.info(f"Using BRouter with profile: {brouter_profile}")
        else:
            logger.info(f"Using ORS with profile: {ors_profile}")

        if constraints.route_type == RouteType.POINT_TO_POINT:
            if selected_service == RoutingServiceType.GRAPHOPPER:
                candidates.append(
                    await self._generate_direct_route_graphhopper(constraints, graphhopper_profile)
                )
            elif selected_service == RoutingServiceType.VALHALLA:
                candidates.append(
                    await self._generate_direct_route_valhalla(constraints, valhalla_profile)
                )
            elif use_brouter:
                try:
                    candidates.append(
                        await self._generate_direct_route_brouter(constraints, brouter_profile)
                    )
                except Exception as e:
                    if selected_service != RoutingServiceType.AUTO:
                        raise
                    logger.warning(f"BRouter direct route failed: {e}, falling back to ORS")
                    ors_direct = await self._generate_direct_route(constraints, ors_profile, ors_options)
                    ors_direct["fallback_reason"] = "auto_brouter_exception_to_ors"
                    candidates.append(ors_direct)
            else:
                candidates.append(
                    await self._generate_direct_route(constraints, ors_profile, ors_options)
                )
        elif constraints.route_type == RouteType.OUT_AND_BACK:
            if selected_service == RoutingServiceType.GRAPHOPPER:
                candidates.append(
                    await self._generate_out_and_back_graphhopper(constraints, graphhopper_profile)
                )
            elif selected_service == RoutingServiceType.VALHALLA:
                candidates.append(
                    await self._generate_out_and_back_valhalla(constraints, valhalla_profile)
                )
            elif use_brouter:
                try:
                    candidates.append(
                        await self._generate_out_and_back_brouter(constraints, brouter_profile)
                    )
                except Exception as e:
                    if selected_service != RoutingServiceType.AUTO:
                        raise
                    logger.warning(f"BRouter out-and-back failed: {e}, falling back to ORS")
                    ors_oab = await self._generate_out_and_back(constraints, ors_profile, ors_options)
                    ors_oab["fallback_reason"] = "auto_brouter_exception_to_ors"
                    candidates.append(ors_oab)
            else:
                candidates.append(
                    await self._generate_out_and_back(constraints, ors_profile, ors_options)
                )
        else:
            # Loop route - generate multiple candidates
            logger.info(
                f"Generating loop candidates",
                use_brouter=use_brouter,
                num_alternatives=constraints.num_alternatives,
                target_distance=constraints.target_distance_meters,
            )
            
            if selected_service == RoutingServiceType.GRAPHOPPER:
                try:
                    loop_candidates = await self._generate_loop_candidates_graphhopper(
                        constraints, graphhopper_profile, num_candidates=constraints.num_alternatives
                    )
                    logger.info(f"GraphHopper generated {len(loop_candidates)} loop candidates")
                except Exception as graphhopper_error:
                    logger.error(f"GraphHopper loop generation failed: {graphhopper_error}", exc_info=True)
                    loop_candidates = []
            elif selected_service == RoutingServiceType.VALHALLA:
                try:
                    loop_candidates = await self._generate_loop_candidates_valhalla(
                        constraints, valhalla_profile, num_candidates=constraints.num_alternatives
                    )
                    logger.info(f"Valhalla generated {len(loop_candidates)} loop candidates")
                except Exception as valhalla_error:
                    logger.error(f"Valhalla loop generation failed: {valhalla_error}", exc_info=True)
                    loop_candidates = []
            elif use_brouter:
                try:
                    loop_candidates = await self._generate_loop_candidates_brouter(
                        constraints, brouter_profile, num_candidates=constraints.num_alternatives
                    )
                    logger.info(f"BRouter generated {len(loop_candidates)} loop candidates")
                except Exception as brouter_error:
                    logger.error(f"BRouter loop generation failed: {brouter_error}", exc_info=True)
                    loop_candidates = []
                
                # FALLBACK: If BRouter fails, try ORS
                if not loop_candidates and selected_service == RoutingServiceType.AUTO:
                    logger.warning("BRouter returned no candidates, falling back to ORS for loop generation")
                    try:
                        logger.info(f"Trying ORS with profile: {ors_profile}")
                        loop_candidates = await self._generate_loop_candidates(
                            constraints, ors_profile, ors_options, num_candidates=constraints.num_alternatives
                        )
                        for lc in loop_candidates:
                            lc["fallback_reason"] = "auto_brouter_empty_to_ors"
                        if loop_candidates:
                            logger.info(f"ORS fallback succeeded with {len(loop_candidates)} candidates")
                        else:
                            logger.error("ORS fallback also returned no candidates")
                    except Exception as ors_error:
                        logger.error(f"ORS fallback failed with error: {ors_error}", exc_info=True)
            else:
                try:
                    loop_candidates = await self._generate_loop_candidates(
                        constraints, ors_profile, ors_options, num_candidates=constraints.num_alternatives
                    )
                    logger.info(f"ORS generated {len(loop_candidates)} loop candidates")
                except Exception as ors_error:
                    logger.error(f"ORS loop generation failed: {ors_error}", exc_info=True)
                    loop_candidates = []
            
            candidates.extend(loop_candidates)
            logger.info(f"Total candidates after loop generation: {len(candidates)}")
        
        logger.info(
            f"=== CANDIDATE GENERATION COMPLETE ===",
            total_candidates=len(candidates),
            route_type=constraints.route_type.value,
        )

        # Apply transition connectors (road ↔ trail) if needed
        if transition_plan:
            start_connector = transition_plan.get("start_connector")
            end_connector = transition_plan.get("end_connector")
            transition_segments = list(transition_plan.get("transition_segments", []))

            def _coords_from_segment(seg: Optional[Dict[str, Any]]) -> List[List[float]]:
                if not seg:
                    return []
                geom = seg.get("geometry", {}) or {}
                return geom.get("coordinates", []) or []

            def _distance_from_coords(coords: List[List[float]]) -> float:
                if len(coords) < 2:
                    return 0.0
                total = 0.0
                for i in range(1, len(coords)):
                    total += self._haversine_distance(coords[i - 1][1], coords[i - 1][0], coords[i][1], coords[i][0])
                return total

            start_coords = _coords_from_segment(start_connector)
            end_coords = _coords_from_segment(end_connector)

            # For loops, return to the original start using the same connector in reverse if needed
            if constraints.route_type in [RouteType.LOOP, RouteType.OUT_AND_BACK] and start_coords and not end_coords:
                end_coords = list(reversed(start_coords))
                transition_segments.append({
                    "type": "return_connector",
                    "source": start_connector.get("source") if start_connector else "connector_reverse",
                    "distance_meters": start_connector.get("distance_meters") if start_connector else None,
                    "geometry": {"type": "LineString", "coordinates": end_coords},
                })

            for candidate in candidates:
                geometry = candidate.get("geometry", {}) or {}
                core_coords = geometry.get("coordinates", []) or []
                if not core_coords:
                    continue

                merged_coords = self._merge_line_coords([start_coords, core_coords, end_coords])
                candidate["geometry"] = {"type": "LineString", "coordinates": merged_coords}

                core_distance = candidate.get("distance_meters") or _distance_from_coords(core_coords)
                start_distance = start_connector.get("distance_meters") if start_connector else _distance_from_coords(start_coords)
                end_distance = end_connector.get("distance_meters") if end_connector else _distance_from_coords(end_coords)
                connector_distance = (start_distance or 0) + (end_distance or 0)

                candidate["distance_meters"] = core_distance + connector_distance
                if candidate.get("duration_seconds") is not None:
                    connector_duration = 0.0
                    if start_connector and start_connector.get("duration_seconds"):
                        connector_duration += start_connector.get("duration_seconds") or 0
                    elif start_distance:
                        connector_duration += (start_distance / 5.0)
                    if end_connector and end_connector.get("duration_seconds"):
                        connector_duration += end_connector.get("duration_seconds") or 0
                    elif end_distance:
                        connector_duration += (end_distance / 5.0)
                    candidate["duration_seconds"] = (candidate.get("duration_seconds") or 0) + connector_duration

                if candidate.get("surface_breakdown"):
                    candidate["surface_breakdown"] = self._apply_connector_surface_breakdown(
                        candidate.get("surface_breakdown", {}),
                        core_distance,
                        connector_distance,
                    )

                candidate["transition_segments"] = transition_segments

        # Validate surface data quality before returning candidates.
        # Use sport-aware thresholds so MTB/Gravel are not rejected too aggressively.
        max_unknown_pct = self._surface_unknown_threshold(constraints)
        valid_candidates = []
        rejection_reasons = {
            "doubling_back": 0,
            "surface_quality": 0,
            "exceptions": 0,
        }
        
        logger.info(
            f"Validating {len(candidates)} candidates",
            route_type=constraints.route_type.value,
            sport_type=constraints.sport_type.value,
            max_unknown_pct=max_unknown_pct,
        )
        
        for i, candidate in enumerate(candidates):
            try:
                # Check for doubling back - reject routes with >35% retracing (50% strict)
                geometry = candidate.get("geometry", {})
                if geometry and constraints.route_type == RouteType.LOOP:
                    try:
                        doubling_back_analysis = self._detect_doubling_back(geometry)
                        retraced_pct = doubling_back_analysis.get("retraced_percentage", 0.0)
                        
                        logger.info(
                            f"Candidate {i} doubling back analysis",
                            retraced_percentage=retraced_pct,
                            retraced_distance_m=doubling_back_analysis.get("retraced_distance_meters", 0),
                            has_doubling_back=doubling_back_analysis.get("has_doubling_back", False),
                            threshold=15.0,
                        )
                        
                        # Reject routes with >35% retracing (50% strict = reject at 35% instead of 15%)
                        # This allows some retracing but still penalizes significant out-and-back segments
                        if retraced_pct > 35.0:
                            logger.warning(
                                f"Rejecting candidate {i} due to excessive doubling back: "
                                f"{retraced_pct:.1f}% retraced "
                                f"({doubling_back_analysis.get('retraced_distance_meters', 0):.0f}m)"
                            )
                            rejection_reasons["doubling_back"] += 1
                            continue  # Skip this candidate
                        elif retraced_pct > 20.0:
                            logger.info(
                                f"Candidate {i} has {retraced_pct:.1f}% retracing (moderate, but acceptable)"
                            )
                    except Exception as db_error:
                        logger.error(
                            f"Doubling back detection failed for candidate {i}: {db_error}",
                            exc_info=True,
                        )
                        rejection_reasons["exceptions"] += 1
                        # Don't reject on detection failure - allow candidate through
                        logger.warning(f"Allowing candidate {i} through despite doubling back detection error")
                
                is_valid, reason = self._validate_surface_data_quality(candidate, max_unknown_pct)
                if is_valid:
                    valid_candidates.append(candidate)
                    logger.info(f"Candidate {i} accepted")
                else:
                    logger.warning(
                        f"Rejecting candidate {i} due to poor surface data: {reason}",
                        surface_breakdown=candidate.get("surface_breakdown", {}),
                    )
                    rejection_reasons["surface_quality"] += 1
            except Exception as e:
                logger.error(
                    f"Exception while validating candidate {i}: {e}",
                    exc_info=True,
                )
                rejection_reasons["exceptions"] += 1
                continue
        
        logger.info(
            f"=== CANDIDATE VALIDATION COMPLETE ===",
            total_candidates=len(candidates),
            valid_candidates=len(valid_candidates),
            rejection_reasons=rejection_reasons,
        )
        
        if valid_candidates:
            logger.info(f"=== ROUTE GENERATION SUCCESS: {len(valid_candidates)} valid candidate(s) ===")
        else:
            logger.error(f"=== ROUTE GENERATION FAILED: No valid candidates ===")

        # If all candidates rejected, try fallback strategy
        if not valid_candidates and candidates:
            logger.warning("All candidates rejected - may be due to surface quality, doubling back, or other quality issues")

            # IMPROVED FALLBACK: Try ORS if BRouter failed
            if use_brouter and constraints.sport_type in [SportType.MTB, SportType.GRAVEL]:
                logger.info("BRouter failed surface quality - trying ORS as fallback")
                try:
                    ors_profile = self.ORS_PROFILES.get(
                        constraints.sport_type, "cycling-road"
                    )
                    ors_options = self._build_ors_options(constraints, ors_profile)

                    if constraints.route_type == RouteType.LOOP:
                        ors_candidates = await self._generate_loop_candidates(
                            constraints, ors_profile, ors_options, num_candidates=3
                        )
                    elif constraints.route_type == RouteType.OUT_AND_BACK:
                        ors_candidates = [await self._generate_out_and_back(
                            constraints, ors_profile, ors_options
                        )]
                    else:
                        ors_candidates = [await self._generate_direct_route(
                            constraints, ors_profile, ors_options
                        )]

                    # Validate ORS candidates
                    for candidate in ors_candidates:
                        candidate["fallback_reason"] = "surface_quality_ors_retry"
                        is_valid, reason = self._validate_surface_data_quality(candidate, max_unknown_pct)
                        if is_valid:
                            valid_candidates.append(candidate)
                            logger.info(f"ORS fallback succeeded with valid surface data")
                        else:
                            logger.warning(f"ORS candidate also failed: {reason}")

                except Exception as e:
                    logger.error(f"ORS fallback failed: {e}")

        # If still no valid candidates, return empty list (force route generation failure)
        if not valid_candidates:
            logger.error(
                "ALL CANDIDATES REJECTED - Route generation failed",
                total_candidates=len(candidates),
                rejection_reasons=rejection_reasons,
                route_type=constraints.route_type.value,
                sport_type=constraints.sport_type.value,
                target_distance=constraints.target_distance_meters,
            )
            
            # If we have candidates but they were all rejected, log details about why
            if candidates:
                logger.error(
                    "All candidates rejected - diagnostic info",
                    first_candidate_keys=list(candidates[0].keys()) if candidates else [],
                    first_candidate_has_geometry=bool(candidates[0].get("geometry")) if candidates else False,
                )
            
            # Don't return best-effort candidates - return empty list to force failure
            # This ensures the caller knows routing actually failed
            return []

        return valid_candidates

    def _surface_unknown_threshold(self, constraints: RouteConstraints) -> float:
        """Pick an unknown-surface threshold based on sport and preferences.
        
        Made more lenient - routes can have significant unknown surface data.
        """
        if constraints.sport_type in [SportType.ROAD]:
            base_threshold = 70  # Increased from 30 - allow 70% unknown for road
        elif constraints.sport_type in [SportType.MTB, SportType.GRAVEL, SportType.EMTB]:
            base_threshold = 85  # Increased from 60 - allow 85% unknown for MTB/Gravel
        else:
            base_threshold = 80  # Increased from 40

        # If user strongly prefers a surface, be slightly stricter but still lenient
        prefs = constraints.surface_preferences
        if prefs and max(prefs.pavement, prefs.gravel, prefs.singletrack) >= 0.6:
            return min(base_threshold, 75)  # Still allow 75% unknown even with preferences

        return base_threshold

    def _validate_surface_data_quality(self, route: Dict[str, Any], max_unknown_pct: float) -> tuple[bool, str]:
        """Validate surface data quality.

        Returns:
            (is_valid, reason) tuple

        Made more lenient - allows routes with significant unknown surface data.
        Only rejects routes that exceed the max threshold.
        """
        surface_breakdown = route.get("surface_breakdown", {})
        
        if not surface_breakdown:
            # Even if no surface data, allow the route through (just warn)
            logger.warning("Route has no surface data, but allowing through due to lenient validation")
            return True, "No surface data (lenient validation)"

        unknown_pct = surface_breakdown.get("unknown", 100)

        # Threshold: reject only if unknown exceeds max threshold (now much higher)
        if unknown_pct > max_unknown_pct:
            return False, (
                f"Surface data insufficient ({unknown_pct:.0f}% unknown, "
                f"max {max_unknown_pct:.0f}% allowed)"
            )

        # Be lenient - don't require minimum known surfaces
        # Routes with mostly unknown surface are acceptable
        return True, "Surface data quality acceptable"

    async def _generate_direct_route(
        self,
        constraints: RouteConstraints,
        profile: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a direct point-to-point route."""
        coordinates = [constraints.start.to_list()]

        # Add via points
        for via in constraints.via_points:
            coordinates.append(via.to_list())

        if constraints.end:
            coordinates.append(constraints.end.to_list())
        else:
            raise ValueError("End point required for point-to-point route")

        result = await self._call_ors_directions(coordinates, profile, options)
        parsed = self._parse_ors_response(result)
        return await self._attach_valhalla_surface(parsed, self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"))

    async def _generate_out_and_back(
        self,
        constraints: RouteConstraints,
        profile: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate an out-and-back route."""
        # Calculate target one-way distance
        target_distance = constraints.target_distance_meters or 16000  # Default 10 miles
        one_way_distance = target_distance / 2

        # Generate a destination point in a random direction
        bearing = random.uniform(0, 360)
        dest = self._point_at_distance(constraints.start, one_way_distance, bearing)

        coordinates = [constraints.start.to_list()]

        # Add via points
        for via in constraints.via_points:
            coordinates.append(via.to_list())

        coordinates.append(dest.to_list())

        # Route out
        outbound = await self._call_ors_directions(coordinates, profile, options)

        # Route back
        return_coords = [dest.to_list(), constraints.start.to_list()]
        inbound = await self._call_ors_directions(return_coords, profile, options)

        # Combine routes
        combined = self._combine_routes(
            self._parse_ors_response(outbound),
            self._parse_ors_response(inbound),
        )
        return await self._attach_valhalla_surface(combined, self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"))

    async def _generate_loop_candidates(
        self,
        constraints: RouteConstraints,
        profile: str,
        options: Dict[str, Any],
        num_candidates: int = 3,
    ) -> List[Dict[str, Any]]:
        """Generate loop route candidates using triangular routes.

        Creates proper loops by placing two waypoints to form a triangle:
        start -> waypoint1 -> waypoint2 -> start

        Road routing typically adds 40-60% overhead vs straight-line distance,
        so we compensate by using shorter waypoint distances.
        """
        candidates = []
        target_distance = constraints.target_distance_meters or 25000  # Default 15 miles

        # Road routing overhead factor - adjust based on distance
        # Longer routes need higher overhead since roads meander more
        if target_distance > 60000:  # > 37 miles
            routing_overhead = 2.0
        elif target_distance > 40000:  # > 25 miles
            routing_overhead = 1.85
        else:
            routing_overhead = 1.7

        # For a triangular loop with 3 legs, straight-line distance per leg = target / 3
        # But roads add overhead, so actual_distance ≈ straight_line * routing_overhead
        # To get target distance: waypoint_dist = target / 3 / routing_overhead
        waypoint_distance = target_distance / 3 / routing_overhead

        # Try different starting directions for variety
        starting_bearings = [45, 90, 135, 0, 180]  # NE, E, SE, N, S

        for i, primary_bearing in enumerate(starting_bearings[:num_candidates * 2]):
            try:
                # Create two waypoints to form a triangle
                # Second bearing is ~100-120 degrees offset for a good loop shape
                secondary_bearing = (primary_bearing + 110) % 360

                waypoint1 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    primary_bearing
                )

                waypoint2 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    secondary_bearing
                )

                # Triangular route: start -> wp1 -> wp2 -> start
                coordinates = [
                    constraints.start.to_list(),
                    waypoint1.to_list(),
                    waypoint2.to_list(),
                    constraints.start.to_list()
                ]

                logger.info(f"Loop candidate {i}: bearings={primary_bearing},{secondary_bearing}, waypoint_dist={waypoint_distance:.0f}m, target={target_distance}m")

                result = await self._call_ors_directions(coordinates, profile, options)
                candidate = self._parse_ors_response(result)
                candidate = await self._attach_valhalla_surface(
                    candidate,
                    self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"),
                )
                candidate["candidate_index"] = i
                candidate["generation_params"] = {
                    "primary_bearing": primary_bearing,
                    "secondary_bearing": secondary_bearing,
                    "waypoint_distance": waypoint_distance,
                    "target_distance": target_distance,
                }
                candidates.append(candidate)
                if len(candidates) >= num_candidates:
                    logger.info(f"Got {len(candidates)} route candidate(s)")
                    return candidates

            except Exception as e:
                logger.warning(f"Failed to generate loop candidate {i} (bearing={primary_bearing}): {e}")
                continue

        return candidates

    # ==================== GraphHopper Methods ====================

    async def _generate_direct_route_graphhopper(
        self,
        constraints: RouteConstraints,
        profile: str,
    ) -> Dict[str, Any]:
        """Generate a direct point-to-point route using GraphHopper."""
        coordinates = [constraints.start.to_list()]

        for via in constraints.via_points:
            coordinates.append(via.to_list())

        if constraints.end:
            coordinates.append(constraints.end.to_list())
        else:
            raise ValueError("End point required for point-to-point route")

        result = await self._call_graphhopper_route(coordinates, profile)
        parsed = self._parse_graphhopper_response(result)
        return await self._attach_valhalla_surface(parsed, self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"))

    async def _generate_out_and_back_graphhopper(
        self,
        constraints: RouteConstraints,
        profile: str,
    ) -> Dict[str, Any]:
        """Generate an out-and-back route using GraphHopper."""
        target_distance = constraints.target_distance_meters or 16000
        one_way_distance = target_distance / 2

        bearing = random.uniform(0, 360)
        dest = self._point_at_distance(constraints.start, one_way_distance, bearing)

        coordinates = [constraints.start.to_list()]
        for via in constraints.via_points:
            coordinates.append(via.to_list())
        coordinates.append(dest.to_list())

        outbound = await self._call_graphhopper_route(coordinates, profile)

        return_coords = [dest.to_list(), constraints.start.to_list()]
        inbound = await self._call_graphhopper_route(return_coords, profile)

        combined = self._combine_routes(
            self._parse_graphhopper_response(outbound),
            self._parse_graphhopper_response(inbound),
        )
        return await self._attach_valhalla_surface(combined, self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"))

    async def _generate_loop_candidates_graphhopper(
        self,
        constraints: RouteConstraints,
        profile: str,
        num_candidates: int = 3,
    ) -> List[Dict[str, Any]]:
        """Generate loop route candidates using GraphHopper."""
        candidates = []
        target_distance = constraints.target_distance_meters or 25000

        if target_distance > 60000:
            routing_overhead = 2.0
        elif target_distance > 40000:
            routing_overhead = 1.85
        else:
            routing_overhead = 1.7

        waypoint_distance = target_distance / 3 / routing_overhead
        starting_bearings = [45, 90, 135, 0, 180]

        for i, primary_bearing in enumerate(starting_bearings[:num_candidates * 2]):
            try:
                secondary_bearing = (primary_bearing + 110) % 360

                waypoint1 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    primary_bearing
                )
                waypoint2 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    secondary_bearing
                )

                coordinates = [
                    constraints.start.to_list(),
                    waypoint1.to_list(),
                    waypoint2.to_list(),
                    constraints.start.to_list()
                ]

                result = await self._call_graphhopper_route(coordinates, profile)
                candidate = self._parse_graphhopper_response(result)
                candidate = await self._attach_valhalla_surface(
                    candidate,
                    self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"),
                )
                candidate["candidate_index"] = i
                candidate["generation_params"] = {
                    "primary_bearing": primary_bearing,
                    "secondary_bearing": secondary_bearing,
                    "waypoint_distance": waypoint_distance,
                    "target_distance": target_distance,
                }
                candidates.append(candidate)
                if len(candidates) >= num_candidates:
                    return candidates
            except Exception as e:
                logger.warning(f"Failed to generate GraphHopper loop candidate {i} (bearing={primary_bearing}): {e}")
                continue

        return candidates

    # ==================== BRouter Methods ====================

    async def _generate_direct_route_brouter(
        self,
        constraints: RouteConstraints,
        profile: str,
    ) -> Dict[str, Any]:
        """Generate a direct point-to-point route using BRouter."""
        coordinates = [constraints.start.to_list()]

        for via in constraints.via_points:
            coordinates.append(via.to_list())

        if constraints.end:
            coordinates.append(constraints.end.to_list())
        else:
            raise ValueError("End point required for point-to-point route")

        result = await self._call_brouter(coordinates, profile)
        parsed = self._parse_brouter_response(result, profile)
        return await self._attach_valhalla_surface(parsed, self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"))

    async def _generate_out_and_back_brouter(
        self,
        constraints: RouteConstraints,
        profile: str,
    ) -> Dict[str, Any]:
        """Generate an out-and-back route using BRouter."""
        target_distance = constraints.target_distance_meters or 16000
        one_way_distance = target_distance / 2 / 1.5  # Account for routing overhead

        bearing = random.uniform(0, 360)
        dest = self._point_at_distance(constraints.start, one_way_distance, bearing)

        coordinates = [constraints.start.to_list()]
        for via in constraints.via_points:
            coordinates.append(via.to_list())
        coordinates.append(dest.to_list())
        coordinates.append(constraints.start.to_list())

        result = await self._call_brouter(coordinates, profile)
        parsed = self._parse_brouter_response(result, profile)
        return await self._attach_valhalla_surface(parsed, self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"))

    async def _generate_loop_candidates_brouter(
        self,
        constraints: RouteConstraints,
        profile: str,
        num_candidates: int = 3,
    ) -> List[Dict[str, Any]]:
        """Generate loop route candidates using BRouter.

        BRouter routes on trails and paths, so the routing overhead is different.
        """
        candidates = []
        target_distance = constraints.target_distance_meters or 25000

        # BRouter on trails - adjust overhead based on distance
        # Longer routes need higher overhead since roads meander more over distance
        if target_distance > 60000:  # > 37 miles
            routing_overhead = 2.0
        elif target_distance > 40000:  # > 25 miles
            routing_overhead = 1.85
        else:
            routing_overhead = 1.7
        waypoint_distance = target_distance / 3 / routing_overhead

        # Try different starting directions - try ALL bearings until one works
        # This helps when some waypoints fall outside routing data coverage
        starting_bearings = [45, 90, 135, 0, 180, 270, 315, 225, 60, 120]

        for i, primary_bearing in enumerate(starting_bearings):
            try:
                secondary_bearing = (primary_bearing + 110) % 360

                waypoint1 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    primary_bearing
                )

                waypoint2 = self._point_at_distance(
                    constraints.start,
                    waypoint_distance,
                    secondary_bearing
                )

                # Build coordinates including any user-specified via_points
                coordinates = [constraints.start.to_list()]

                # Add user via_points first (these are the "must pass through" points)
                for via in constraints.via_points:
                    coordinates.append(via.to_list())

                # Then add computed waypoints for the loop shape
                coordinates.extend([
                    waypoint1.to_list(),
                    waypoint2.to_list(),
                    constraints.start.to_list()
                ])

                via_count = len(constraints.via_points)
                logger.info(f"BRouter loop candidate {i}: bearings={primary_bearing},{secondary_bearing}, waypoint_dist={waypoint_distance:.0f}m, target={target_distance}m, via_points={via_count}")

                result = await self._call_brouter(coordinates, profile)
                candidate = self._parse_brouter_response(result, profile)
                candidate = await self._attach_valhalla_surface(
                    candidate,
                    self.VALHALLA_PROFILES.get(constraints.sport_type, "bicycle"),
                )
                candidate["candidate_index"] = i
                candidate["generation_params"] = {
                    "primary_bearing": primary_bearing,
                    "secondary_bearing": secondary_bearing,
                    "waypoint_distance": waypoint_distance,
                    "target_distance": target_distance,
                }
                candidates.append(candidate)
                if len(candidates) >= num_candidates:
                    logger.info(f"Got {len(candidates)} BRouter route candidate(s)")
                    return candidates

            except Exception as e:
                logger.warning(f"Failed to generate BRouter loop candidate {i} (bearing={primary_bearing}): {e}")
                continue

        return candidates

    # ==================== Utility Methods ====================

    def _generate_loop_anchors(
        self,
        center: Coordinate,
        radius: float,
        num_anchors: int,
        base_bearing: float,
    ) -> List[Coordinate]:
        """Generate anchor points for a loop."""
        anchors = []
        bearing_step = 360 / num_anchors

        for i in range(num_anchors):
            bearing = base_bearing + (bearing_step * i)
            # Add some randomness to radius
            anchor_radius = radius * random.uniform(0.7, 1.3)
            anchor = self._point_at_distance(center, anchor_radius, bearing)
            anchors.append(anchor)

        return anchors

    def _point_at_distance(
        self,
        start: Coordinate,
        distance_meters: float,
        bearing_degrees: float,
    ) -> Coordinate:
        """Calculate a point at a given distance and bearing from start."""
        R = 6371000  # Earth's radius in meters
        d = distance_meters / R

        lat1 = math.radians(start.lat)
        lon1 = math.radians(start.lng)
        bearing = math.radians(bearing_degrees)

        lat2 = math.asin(
            math.sin(lat1) * math.cos(d) +
            math.cos(lat1) * math.sin(d) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2)
        )

        return Coordinate(
            lat=math.degrees(lat2),
            lng=math.degrees(lon2),
        )

    def _parse_ors_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse ORS response into standardized format."""
        features = response.get("features", [])
        if not features:
            raise ValueError("No route found in ORS response")

        feature = features[0]
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})
        summary = properties.get("summary", {})
        segments = properties.get("segments", [])

        # Extract coordinates with elevation
        coordinates = geometry.get("coordinates", [])

        # Extract extra info
        extras = properties.get("extras", {})

        # Parse surface breakdown from ORS extras
        # ORS surface codes: 0=Unknown, 1=Paved, 2=Unpaved, 3=Asphalt, 4=Concrete,
        # 5=Cobblestone, 6=Metal, 7=Wood, 8=Compacted Gravel, 9=Fine Gravel,
        # 10=Gravel, 11=Dirt, 12=Ground, 13=Ice, 14=Salt, 15=Sand, 16=Woodchips, 17=Grass, 18=Paving stones
        surface_info = extras.get("surface", {})
        surface_breakdown = self._parse_ors_surface(surface_info, summary.get("distance", 0))

        return {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "distance_meters": summary.get("distance", 0),
            "duration_seconds": summary.get("duration", 0),
            "elevation_gain": self._calculate_elevation_gain(coordinates),
            "elevation_loss": self._calculate_elevation_loss(coordinates),
            "segments": self._parse_segments(segments),
            "surface_breakdown": surface_breakdown,
            "surface_info": surface_info,
            "waytypes_info": extras.get("waytypes", {}),
            "steepness_info": extras.get("steepness", {}),
            "instructions": [
                step for seg in segments for step in seg.get("steps", [])
            ],
            "source": "ors",
        }

    def _parse_ors_surface(self, surface_info: Dict[str, Any], total_distance: float) -> Dict[str, float]:
        """Parse ORS surface info into breakdown percentages."""
        # ORS surface type mapping
        SURFACE_MAP = {
            0: "unknown",   # Unknown
            1: "paved",     # Paved
            2: "unpaved",   # Unpaved
            3: "paved",     # Asphalt
            4: "paved",     # Concrete
            5: "paved",     # Cobblestone
            6: "paved",     # Metal
            7: "unpaved",   # Wood
            8: "gravel",    # Compacted Gravel
            9: "gravel",    # Fine Gravel
            10: "gravel",   # Gravel
            11: "ground",   # Dirt
            12: "ground",   # Ground
            13: "unknown",  # Ice
            14: "unknown",  # Salt
            15: "ground",   # Sand
            16: "ground",   # Woodchips
            17: "ground",   # Grass
            18: "paved",    # Paving stones
        }

        breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 0}

        # ORS returns summary with [value, distance, percentage]
        summary = surface_info.get("summary", [])
        if summary:
            for item in summary:
                if isinstance(item, dict):
                    surface_code = item.get("value", 0)
                    amount = item.get("amount", 0)  # This is percentage
                    surface_type = SURFACE_MAP.get(surface_code, "unknown")
                    breakdown[surface_type] += amount

        # CRITICAL FIX: If no summary data, mark as unknown instead of using unreliable defaults
        # This will trigger validation failure and force alternative routes
        if sum(breakdown.values()) == 0:
            logger.warning("ORS returned no surface data - marking as 100% unknown")
            logger.warning("Route will be rejected by validation (requires <20% unknown)")
            breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}
        else:
            logger.info(f"ORS surface data: {breakdown}")

        return breakdown

    def _calculate_elevation_gain(self, coordinates: List[List[float]]) -> float:
        """Calculate total elevation gain from coordinates with elevation."""
        gain = 0
        for i in range(1, len(coordinates)):
            if len(coordinates[i]) > 2 and len(coordinates[i - 1]) > 2:
                diff = coordinates[i][2] - coordinates[i - 1][2]
                if diff > 0:
                    gain += diff
        return gain

    def _calculate_elevation_loss(self, coordinates: List[List[float]]) -> float:
        """Calculate total elevation loss from coordinates with elevation."""
        loss = 0
        for i in range(1, len(coordinates)):
            if len(coordinates[i]) > 2 and len(coordinates[i - 1]) > 2:
                diff = coordinates[i - 1][2] - coordinates[i][2]
                if diff > 0:
                    loss += diff
        return loss

    def _parse_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse ORS segments into standardized format."""
        parsed = []
        for seg in segments:
            parsed.append({
                "distance_meters": seg.get("distance", 0),
                "duration_seconds": seg.get("duration", 0),
                "steps": seg.get("steps", []),
            })
        return parsed

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
        total_distance = self._calculate_route_distance_for_detection(points)
        
        if total_distance == 0:
            return {
                "has_doubling_back": False,
                "retraced_distance_meters": 0.0,
                "retraced_percentage": 0.0,
                "doubling_back_score": 1.0,
            }

        # Check for segments that overlap and go in opposite directions
        retraced_distance = 0.0
        segment_length = 50  # Check every 50 meters of route
        num_segments = max(10, int(total_distance / segment_length))
        step = max(1, len(points) // num_segments)
        
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
                    seg_bearing = self._calculate_bearing_for_detection(seg_start[1], seg_start[0], seg_end[1], seg_end[0])
                    check_bearing = self._calculate_bearing_for_detection(check_start[1], check_start[0], check_end[1], check_end[0])
                    
                    # Calculate angle difference (accounting for wrap-around)
                    angle_diff = abs(seg_bearing - check_bearing)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff
                    
                    # If segments are roughly opposite (150-210 degrees difference), it's retracing
                    if angle_diff > 150:
                        seg_distance = self._haversine_distance(seg_start[1], seg_start[0], seg_end[1], seg_end[0])
                        retraced_distance += seg_distance

        retraced_percentage = (retraced_distance / total_distance * 100) if total_distance > 0 else 0.0
        has_doubling_back = retraced_percentage > 5.0  # More than 5% retracing is significant
        
        # Score: 1.0 = no retracing, 0.0 = all retracing
        if retraced_percentage == 0:
            doubling_back_score = 1.0
        elif retraced_percentage < 10:
            doubling_back_score = 1.0 - (retraced_percentage / 10) * 0.3
        elif retraced_percentage < 25:
            doubling_back_score = 0.7 - ((retraced_percentage - 10) / 15) * 0.4
        else:
            doubling_back_score = max(0.0, 0.3 - ((retraced_percentage - 25) / 75) * 0.3)
        
        return {
            "has_doubling_back": has_doubling_back,
            "retraced_distance_meters": round(retraced_distance, 1),
            "retraced_percentage": round(retraced_percentage, 1),
            "doubling_back_score": round(doubling_back_score, 3),
        }

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula (meters)."""
        R = 6371000  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    async def _snap_point_to_highway(
        self,
        point: Coordinate,
        highway_filter: str,
        radius_meters: int,
    ) -> Optional[List[float]]:
        """Snap a point to the nearest highway feature matching the filter."""
        lat = point.lat
        lng = point.lng
        query = f"""
[out:json][timeout:15];
(
  way["highway"~"{highway_filter}"](around:{radius_meters},{lat},{lng});
);
out geom;
"""
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.post(
                    settings.overpass_url,
                    data={"data": query},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            return None

        def _nearest_coordinate_on_linestring(coords: List[List[float]], target: List[float]) -> Optional[List[float]]:
            if not coords:
                return None
            best = None
            best_distance = float("inf")
            for coord in coords:
                distance = self._haversine_distance(target[1], target[0], coord[1], coord[0])
                if distance < best_distance:
                    best_distance = distance
                    best = coord
            return best

        best_point = None
        best_distance = float("inf")
        for element in data.get("elements", []):
            if element.get("type") != "way":
                continue
            geometry = element.get("geometry", [])
            if not geometry:
                continue
            coords = [[node["lon"], node["lat"]] for node in geometry if "lon" in node and "lat" in node]
            candidate = _nearest_coordinate_on_linestring(coords, [lng, lat])
            if not candidate:
                continue
            distance = self._haversine_distance(lat, lng, candidate[1], candidate[0])
            if distance < best_distance:
                best_distance = distance
                best_point = candidate
        return best_point

    async def _snap_point_to_network(
        self,
        point: Coordinate,
        highway_filter: str,
        radii: Tuple[int, ...] = (50, 150, 300),
    ) -> Tuple[Optional[List[float]], Optional[float]]:
        for radius in radii:
            snapped = await self._snap_point_to_highway(point, highway_filter, radius)
            if snapped:
                distance = self._haversine_distance(point.lat, point.lng, snapped[1], snapped[0])
                return snapped, distance
        return None, None

    def _connector_distance_limit(self, constraints: RouteConstraints) -> float:
        target = constraints.target_distance_meters or 20000
        return min(10000.0, max(500.0, target * 0.25))

    async def _generate_connector_route(
        self,
        start: Coordinate,
        end: Coordinate,
    ) -> Dict[str, Any]:
        """Generate a connector route between two points using any available router."""
        coordinates = [start.to_list(), end.to_list()]

        # Try ORS driving-car if available
        if self.ors_api_key:
            try:
                result = await self._call_ors_directions(coordinates, "driving-car", options=None, preference="shortest")
                parsed = self._parse_ors_response(result)
                parsed["source"] = "connector_ors"
                return parsed
            except Exception:
                pass

        # Try GraphHopper if available
        if self.graphhopper_api_key:
            try:
                result = await self._call_graphhopper_route(coordinates, "bike")
                parsed = self._parse_graphhopper_response(result)
                parsed["source"] = "connector_graphhopper"
                return parsed
            except Exception:
                pass

        # Try BRouter as fallback
        try:
            result = await self._call_brouter(coordinates, "fastbike")
            parsed = self._parse_brouter_response(result)
            parsed["source"] = "connector_brouter"
            return parsed
        except Exception:
            pass

        # Last resort: straight line
        return {
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "distance_meters": self._haversine_distance(start.lat, start.lng, end.lat, end.lng),
            "duration_seconds": None,
            "surface_breakdown": {"unknown": 100},
            "source": "connector_straight",
        }

    def _merge_line_coords(self, parts: List[List[List[float]]]) -> List[List[float]]:
        merged: List[List[float]] = []
        for coords in parts:
            if not coords:
                continue
            if not merged:
                merged = coords[:]
                continue
            if merged[-1] == coords[0]:
                merged.extend(coords[1:])
            else:
                merged.extend(coords)
        return merged

    def _apply_connector_surface_breakdown(
        self,
        surface_breakdown: Dict[str, float],
        core_distance: float,
        connector_distance: float,
    ) -> Dict[str, float]:
        if not surface_breakdown:
            return surface_breakdown
        total = max(1.0, core_distance + connector_distance)
        weighted = {}
        for key, value in surface_breakdown.items():
            weighted[key] = (value / 100.0) * core_distance
        weighted["unknown"] = weighted.get("unknown", 0.0) + connector_distance
        return {k: (v / total) * 100.0 for k, v in weighted.items()}

    async def _build_transition_plan(
        self,
        constraints: RouteConstraints,
    ) -> Optional[Dict[str, Any]]:
        """Compute trail/road transition plan for off-road routes."""
        if constraints.sport_type not in [SportType.MTB, SportType.GRAVEL, SportType.EMTB]:
            return None

        start = constraints.start
        end = constraints.end
        max_connector = self._connector_distance_limit(constraints)

        trail_start, trail_start_dist = await self._snap_point_to_network(start, TRAIL_HIGHWAY_FILTER)
        road_start, road_start_dist = await self._snap_point_to_network(start, ROAD_HIGHWAY_FILTER)

        transition_segments: List[Dict[str, Any]] = []
        start_connector = None
        end_connector = None

        adjusted = constraints.model_copy(deep=True)

        on_trail = trail_start_dist is not None and trail_start_dist <= 20
        on_road = road_start_dist is not None and road_start_dist <= 20

        if trail_start and not on_trail and on_road and trail_start_dist is not None and trail_start_dist <= max_connector:
            connector = await self._generate_connector_route(start, Coordinate(lat=trail_start[1], lng=trail_start[0]))
            start_connector = connector
            adjusted.start = Coordinate(lat=trail_start[1], lng=trail_start[0])
            transition_segments.append({
                "type": "start_connector",
                "source": connector.get("source"),
                "distance_meters": connector.get("distance_meters"),
                "geometry": connector.get("geometry"),
            })

        if constraints.route_type == RouteType.POINT_TO_POINT and end:
            trail_end, trail_end_dist = await self._snap_point_to_network(end, TRAIL_HIGHWAY_FILTER)
            road_end, road_end_dist = await self._snap_point_to_network(end, ROAD_HIGHWAY_FILTER)
            end_on_trail = trail_end_dist is not None and trail_end_dist <= 20
            end_on_road = road_end_dist is not None and road_end_dist <= 20
            if trail_end and not end_on_trail and end_on_road and trail_end_dist is not None and trail_end_dist <= max_connector:
                connector = await self._generate_connector_route(Coordinate(lat=trail_end[1], lng=trail_end[0]), end)
                end_connector = connector
                adjusted.end = Coordinate(lat=trail_end[1], lng=trail_end[0])
                transition_segments.append({
                    "type": "end_connector",
                    "source": connector.get("source"),
                    "distance_meters": connector.get("distance_meters"),
                    "geometry": connector.get("geometry"),
                })

        if not transition_segments:
            return None

        return {
            "constraints": adjusted,
            "start_connector": start_connector,
            "end_connector": end_connector,
            "transition_segments": transition_segments,
        }

    def _calculate_route_distance_for_detection(self, points: List[Tuple[float, float]]) -> float:
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

    def _calculate_bearing_for_detection(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing (direction) from point 1 to point 2 in degrees (0-360)."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)
        
        y = math.sin(delta_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
        
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360

    def _combine_routes(
        self,
        route1: Dict[str, Any],
        route2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Combine two routes (e.g., for out-and-back)."""
        coords1 = route1["geometry"]["coordinates"]
        coords2 = route2["geometry"]["coordinates"]

        # Skip first point of route2 to avoid duplicate
        combined_coords = coords1 + coords2[1:]

        return {
            "geometry": {
                "type": "LineString",
                "coordinates": combined_coords,
            },
            "distance_meters": route1["distance_meters"] + route2["distance_meters"],
            "duration_seconds": route1["duration_seconds"] + route2["duration_seconds"],
            "elevation_gain": route1["elevation_gain"] + route2["elevation_gain"],
            "elevation_loss": route1["elevation_loss"] + route2["elevation_loss"],
            "segments": route1["segments"] + route2["segments"],
            "surface_info": {**route1.get("surface_info", {}), **route2.get("surface_info", {})},
            "instructions": route1["instructions"] + route2["instructions"],
        }

    async def reroute_segment(
        self,
        segment_start: Coordinate,
        segment_end: Coordinate,
        constraints: RouteConstraints,
        avoid_original: bool = False,
    ) -> Dict[str, Any]:
        """Re-route a specific segment with new constraints."""
        profile = self.ORS_PROFILES.get(constraints.sport_type, "cycling-regular")
        options = self._build_ors_options(constraints, profile)

        coordinates = [segment_start.to_list(), segment_end.to_list()]
        result = await self._call_ors_directions(coordinates, profile, options)
        return self._parse_ors_response(result)


# Singleton instance
_routing_service: Optional[RoutingService] = None


async def get_routing_service() -> RoutingService:
    """Get or create routing service instance."""
    global _routing_service
    if _routing_service is None:
        _routing_service = RoutingService()
    return _routing_service
