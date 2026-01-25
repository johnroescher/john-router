"""Geocoding service for place search and address resolution."""
from typing import List, Optional, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.schemas.common import Coordinate, BoundingBox
import structlog

logger = structlog.get_logger()


class GeocodingService:
    """Service for geocoding and place search."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        # Use Nominatim (OpenStreetMap) for geocoding
        self.nominatim_url = "https://nominatim.openstreetmap.org"

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def geocode(self, query: str, prefer_us: bool = True) -> Optional[Coordinate]:
        """Convert address/place name to coordinates.

        Args:
            query: Address or place name
            prefer_us: If True, prefer US results. Set to False for international locations.

        Returns:
            Coordinate if found, None otherwise
        """
        try:
            url = f"{self.nominatim_url}/search"
            params = {
                "q": query,
                "format": "json",
                "limit": 3,  # Get multiple results for confidence checking
            }

            # CRITICAL FIX: Make US-first optional, not hardcoded
            # Only apply if not already specified in query (e.g., "Marin County, California")
            if prefer_us and "," not in query:
                params["countrycodes"] = "us"
                logger.info(f"Geocoding '{query}' with US preference")
            else:
                logger.info(f"Geocoding '{query}' globally (location specifies region)")

            headers = {
                "User-Agent": "JohnRouter/1.0 (contact@johnrouter.app)"
            }

            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()

            results = response.json()
            if results:
                result = results[0]
                display_name = result.get("display_name", query)
                importance = result.get("importance", 0)

                logger.info(f"Geocoded '{query}' → '{display_name}' (importance: {importance:.2f})")

                # CRITICAL FIX: Log confidence information
                if importance < 0.3:
                    logger.warning(f"Low confidence geocoding result for '{query}' (importance: {importance:.2f})")

                coord = Coordinate(
                    lat=float(result["lat"]),
                    lng=float(result["lon"]),
                )

                # Log if there were multiple close matches (ambiguous)
                if len(results) > 1:
                    logger.info(f"Note: {len(results)} matches found for '{query}', using first: '{display_name}'")

                return coord

            logger.warning(f"No geocoding results found for '{query}'")
            return None

        except Exception as e:
            logger.error(f"Geocoding failed for '{query}': {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def reverse_geocode(self, coordinate: Coordinate) -> Optional[Dict[str, Any]]:
        """Convert coordinates to address/place name.

        Args:
            coordinate: The coordinate to reverse geocode

        Returns:
            Address information if found
        """
        try:
            url = f"{self.nominatim_url}/reverse"
            params = {
                "lat": coordinate.lat,
                "lon": coordinate.lng,
                "format": "json",
            }
            headers = {
                "User-Agent": "JohnRouter/1.0 (contact@johnrouter.app)"
            }

            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()

            result = response.json()
            if result and "address" in result:
                return {
                    "display_name": result.get("display_name", ""),
                    "address": result["address"],
                    "type": result.get("type", ""),
                    "category": result.get("category", ""),
                }

            return None

        except Exception as e:
            logger.error(f"Reverse geocoding failed: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search_places(
        self,
        query: str,
        bbox: Optional[BoundingBox] = None,
        limit: int = 10,
        place_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for places matching query.

        Args:
            query: Search query
            bbox: Bounding box to limit search
            limit: Maximum number of results
            place_types: Filter by place types (e.g., ['trailhead', 'park'])

        Returns:
            List of matching places
        """
        try:
            url = f"{self.nominatim_url}/search"
            params = {
                "q": query,
                "format": "json",
                "limit": limit,
                "countrycodes": "us",
                "addressdetails": 1,
            }

            if bbox:
                params["viewbox"] = f"{bbox.min_lng},{bbox.max_lat},{bbox.max_lng},{bbox.min_lat}"
                params["bounded"] = 1

            headers = {
                "User-Agent": "JohnRouter/1.0 (contact@johnrouter.app)"
            }

            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()

            results = response.json()
            places = []

            for result in results:
                place = {
                    "name": result.get("display_name", ""),
                    "coordinate": Coordinate(
                        lat=float(result["lat"]),
                        lng=float(result["lon"]),
                    ),
                    "type": result.get("type", ""),
                    "category": result.get("category", ""),
                    "address": result.get("address", {}),
                    "importance": result.get("importance", 0),
                }

                # Filter by place types if specified
                if place_types:
                    if place["type"] in place_types or place["category"] in place_types:
                        places.append(place)
                else:
                    places.append(place)

            return places

        except Exception as e:
            logger.error(f"Place search failed for '{query}': {e}")
            return []

    async def search_trailheads(
        self,
        bbox: BoundingBox,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search for trailheads within a bounding box.

        Args:
            bbox: Bounding box to search
            limit: Maximum number of results

        Returns:
            List of trailheads
        """
        # Search for common trailhead-related terms
        queries = ["trailhead", "trail parking", "bike trail", "mountain bike"]
        all_results = []

        for query in queries:
            results = await self.search_places(
                query=query,
                bbox=bbox,
                limit=limit // len(queries),
                place_types=["trailhead", "park", "parking"],
            )
            all_results.extend(results)

        # Deduplicate by coordinate proximity
        unique_results = self._deduplicate_places(all_results)

        return unique_results[:limit]

    def _deduplicate_places(
        self,
        places: List[Dict[str, Any]],
        threshold_meters: float = 100,
    ) -> List[Dict[str, Any]]:
        """Remove duplicate places that are very close together."""
        import math

        unique = []
        for place in places:
            is_duplicate = False
            for existing in unique:
                dist = self._haversine_distance(
                    place["coordinate"].lat, place["coordinate"].lng,
                    existing["coordinate"].lat, existing["coordinate"].lng,
                )
                if dist < threshold_meters:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(place)

        return unique

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two points in meters."""
        import math

        R = 6371000
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


# Singleton
_geocoding_service: Optional[GeocodingService] = None


async def get_geocoding_service() -> GeocodingService:
    """Get or create geocoding service instance."""
    global _geocoding_service
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    return _geocoding_service
