"""Elevation service for fetching and caching elevation data."""
from typing import List, Optional, Tuple
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.schemas.common import Coordinate
import structlog

logger = structlog.get_logger()


class ElevationService:
    """Service for fetching elevation data."""
    _MIN_GRADE_DISTANCE_METERS = 5.0
    _MAX_ABS_GRADE_PERCENT = 40.0

    def __init__(self):
        self.api_url = settings.elevation_api_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_elevation(self, coordinate: Coordinate) -> Optional[float]:
        """Get elevation for a single coordinate."""
        try:
            # Use SRTM dataset (covers most of US well)
            url = f"{self.api_url}/srtm90m"
            params = {"locations": f"{coordinate.lat},{coordinate.lng}"}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if results and results[0].get("elevation") is not None:
                return results[0]["elevation"]
            return None

        except Exception as e:
            logger.warning(f"Failed to get elevation: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_elevations_batch(
        self,
        coordinates: List[Coordinate],
        batch_size: int = 100,
    ) -> List[Optional[float]]:
        """Get elevations for multiple coordinates in batches."""
        all_elevations = []

        for i in range(0, len(coordinates), batch_size):
            batch = coordinates[i:i + batch_size]
            batch_elevations = await self._fetch_batch(batch)
            all_elevations.extend(batch_elevations)

        return all_elevations

    async def _fetch_batch(
        self,
        coordinates: List[Coordinate],
    ) -> List[Optional[float]]:
        """Fetch elevations for a batch of coordinates."""
        try:
            # Format as pipe-separated lat,lng pairs
            locations = "|".join([f"{c.lat},{c.lng}" for c in coordinates])

            url = f"{self.api_url}/srtm90m"
            params = {"locations": locations}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            return [
                r.get("elevation") if r.get("elevation") is not None else None
                for r in results
            ]

        except Exception as e:
            logger.warning(f"Failed to get batch elevations: {e}")
            return [None] * len(coordinates)

    async def get_elevation_profile(
        self,
        coordinates: List[List[float]],
        sample_interval_meters: float = 50,
    ) -> List[dict]:
        """Get elevation profile along a route.

        Args:
            coordinates: List of [lng, lat] or [lng, lat, ele] coordinates
            sample_interval_meters: Distance between elevation samples

        Returns:
            List of elevation profile points with distance, elevation, and grade
        """
        profile = []
        cumulative_distance = 0

        # If coordinates already have elevation, use them
        if len(coordinates[0]) > 2 and coordinates[0][2] is not None:
            return self._build_profile_from_coords(coordinates)

        # Otherwise, sample elevations
        coords_to_sample = [
            Coordinate(lng=c[0], lat=c[1]) for c in coordinates
        ]

        elevations = await self.get_elevations_batch(coords_to_sample)

        return self._build_profile_from_elevations(coordinates, elevations)

    def _build_profile_from_coords(
        self,
        coordinates: List[List[float]],
    ) -> List[dict]:
        """Build profile from coordinates that already have elevation."""
        profile = []
        cumulative_distance = 0

        for i, coord in enumerate(coordinates):
            if i > 0:
                cumulative_distance += self._haversine_distance(
                    coordinates[i - 1][1], coordinates[i - 1][0],
                    coord[1], coord[0]
                )

            elevation = coord[2] if len(coord) > 2 else None

            # Calculate grade
            grade = 0
            if i > 0 and elevation is not None:
                prev_ele = coordinates[i - 1][2] if len(coordinates[i - 1]) > 2 else None
                if prev_ele is not None:
                    dist = self._haversine_distance(
                        coordinates[i - 1][1], coordinates[i - 1][0],
                        coord[1], coord[0]
                    )
                    if dist >= self._MIN_GRADE_DISTANCE_METERS:
                        grade = ((elevation - prev_ele) / dist) * 100
                        if grade > self._MAX_ABS_GRADE_PERCENT:
                            grade = self._MAX_ABS_GRADE_PERCENT
                        elif grade < -self._MAX_ABS_GRADE_PERCENT:
                            grade = -self._MAX_ABS_GRADE_PERCENT

            profile.append({
                "distance_meters": cumulative_distance,
                "elevation_meters": elevation,
                "grade_percent": grade,
                "coordinate": {"lng": coord[0], "lat": coord[1]},
            })

        return profile

    def _build_profile_from_elevations(
        self,
        coordinates: List[List[float]],
        elevations: List[Optional[float]],
    ) -> List[dict]:
        """Build profile from coordinates and separate elevation data."""
        profile = []
        cumulative_distance = 0

        for i, (coord, elevation) in enumerate(zip(coordinates, elevations)):
            if i > 0:
                cumulative_distance += self._haversine_distance(
                    coordinates[i - 1][1], coordinates[i - 1][0],
                    coord[1], coord[0]
                )

            # Calculate grade
            grade = 0
            if i > 0 and elevation is not None:
                prev_ele = elevations[i - 1]
                if prev_ele is not None:
                    dist = self._haversine_distance(
                        coordinates[i - 1][1], coordinates[i - 1][0],
                        coord[1], coord[0]
                    )
                    if dist >= self._MIN_GRADE_DISTANCE_METERS:
                        grade = ((elevation - prev_ele) / dist) * 100
                        if grade > self._MAX_ABS_GRADE_PERCENT:
                            grade = self._MAX_ABS_GRADE_PERCENT
                        elif grade < -self._MAX_ABS_GRADE_PERCENT:
                            grade = -self._MAX_ABS_GRADE_PERCENT

            profile.append({
                "distance_meters": cumulative_distance,
                "elevation_meters": elevation,
                "grade_percent": grade,
                "coordinate": {"lng": coord[0], "lat": coord[1]},
            })

        return profile

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two points using Haversine formula."""
        import math

        R = 6371000  # Earth's radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2) ** 2 +
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def calculate_stats(
        self,
        profile: List[dict],
    ) -> dict:
        """Calculate elevation statistics from profile."""
        elevations = [
            p["elevation_meters"]
            for p in profile
            if p["elevation_meters"] is not None
        ]
        grades = [p["grade_percent"] for p in profile]

        if not elevations:
            return {
                "elevation_gain_meters": 0,
                "elevation_loss_meters": 0,
                "max_elevation_meters": 0,
                "min_elevation_meters": 0,
                "avg_grade_percent": 0,
                "max_grade_percent": 0,
                "min_grade_percent": 0,
            }

        # Calculate gain/loss
        gain = 0
        loss = 0
        for i in range(1, len(elevations)):
            diff = elevations[i] - elevations[i - 1]
            if diff > 0:
                gain += diff
            else:
                loss += abs(diff)

        return {
            "elevation_gain_meters": gain,
            "elevation_loss_meters": loss,
            "max_elevation_meters": max(elevations),
            "min_elevation_meters": min(elevations),
            "avg_grade_percent": sum(grades) / len(grades) if grades else 0,
            "max_grade_percent": max(grades) if grades else 0,
            "min_grade_percent": min(grades) if grades else 0,
        }


# Singleton instance
_elevation_service: Optional[ElevationService] = None


async def get_elevation_service() -> ElevationService:
    """Get or create elevation service instance."""
    global _elevation_service
    if _elevation_service is None:
        _elevation_service = ElevationService()
    return _elevation_service
