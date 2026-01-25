"""Route analysis service for computing detailed statistics."""
from typing import List, Dict, Any, Optional
import math

from app.schemas.route import (
    RouteAnalysis,
    SurfaceBreakdown,
    MTBDifficultyBreakdown,
    ElevationPoint,
)
from app.schemas.common import Coordinate
from .elevation import ElevationService, get_elevation_service
import structlog

logger = structlog.get_logger()


# OSM surface type mapping to our categories
SURFACE_MAPPING = {
    # Pavement
    "asphalt": "pavement",
    "concrete": "pavement",
    "paved": "pavement",
    "concrete:plates": "pavement",
    "concrete:lanes": "pavement",
    "paving_stones": "pavement",
    "sett": "pavement",

    # Gravel
    "gravel": "gravel",
    "fine_gravel": "gravel",
    "compacted": "gravel",
    "pebblestone": "gravel",
    "unpaved": "gravel",

    # Dirt
    "dirt": "dirt",
    "earth": "dirt",
    "mud": "dirt",
    "sand": "dirt",
    "clay": "dirt",

    # Singletrack indicators
    "ground": "singletrack",
    "grass": "singletrack",
    "wood": "singletrack",
    "woodchips": "singletrack",
}

# Highway type to singletrack detection
SINGLETRACK_HIGHWAYS = ["path", "footway", "bridleway", "steps", "trail"]

# MTB scale to difficulty mapping
MTB_SCALE_DIFFICULTY = {
    0: "green",
    1: "blue",
    2: "black",
    3: "black",
    4: "double_black",
    5: "double_black",
}


class RouteAnalysisService:
    """Service for analyzing cycling routes."""

    def __init__(self, elevation_service: Optional[ElevationService] = None):
        self.elevation_service = elevation_service

    async def analyze_route(
        self,
        geometry: Dict[str, Any],
        routing_data: Optional[Dict[str, Any]] = None,
        segment_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> RouteAnalysis:
        """Perform comprehensive route analysis.

        Args:
            geometry: GeoJSON LineString geometry
            routing_data: Optional data from routing service
            segment_metadata: Optional metadata for each segment (from OSM, etc.)

        Returns:
            Complete route analysis
        """
        coordinates = geometry.get("coordinates", [])

        if not coordinates:
            raise ValueError("No coordinates in geometry")

        # Get elevation profile
        if self.elevation_service is None:
            self.elevation_service = await get_elevation_service()

        elevation_profile = await self.elevation_service.get_elevation_profile(coordinates)
        elevation_stats = self.elevation_service.calculate_stats(elevation_profile)

        # Calculate distance
        total_distance = self._calculate_total_distance(coordinates)

        # Analyze grades
        grade_analysis = self._analyze_grades(elevation_profile, total_distance)

        # Analyze surfaces
        surface_breakdown = self._analyze_surfaces(routing_data, segment_metadata)

        # Analyze MTB difficulty
        mtb_breakdown = self._analyze_mtb_difficulty(segment_metadata)

        # Calculate difficulty ratings
        difficulty_ratings = self._calculate_difficulty_ratings(
            elevation_stats,
            grade_analysis,
            surface_breakdown,
            mtb_breakdown,
            total_distance,
        )

        # Estimate time
        estimated_time = self._estimate_time(
            total_distance,
            elevation_stats["elevation_gain_meters"],
            surface_breakdown,
            difficulty_ratings["technical_difficulty"],
        )

        # Calculate confidence
        confidence = self._calculate_confidence(routing_data, segment_metadata)

        return RouteAnalysis(
            distance_meters=total_distance,
            elevation_gain_meters=elevation_stats["elevation_gain_meters"],
            elevation_loss_meters=elevation_stats["elevation_loss_meters"],
            estimated_time_seconds=estimated_time,
            max_elevation_meters=elevation_stats["max_elevation_meters"],
            min_elevation_meters=elevation_stats["min_elevation_meters"],
            avg_grade_percent=grade_analysis["avg_grade"],
            max_grade_percent=grade_analysis["max_grade"],
            longest_climb_meters=grade_analysis["longest_climb"],
            steepest_100m_percent=grade_analysis["steepest_100m"],
            steepest_1km_percent=grade_analysis["steepest_1km"],
            climbing_above_8_percent_meters=grade_analysis["climbing_above_8"],
            surface_breakdown=surface_breakdown,
            mtb_difficulty_breakdown=mtb_breakdown,
            max_technical_rating=self._get_max_technical_rating(segment_metadata),
            hike_a_bike_sections=self._count_hike_a_bike(segment_metadata),
            hike_a_bike_distance_meters=self._sum_hike_a_bike_distance(segment_metadata),
            physical_difficulty=difficulty_ratings["physical_difficulty"],
            technical_difficulty=difficulty_ratings["technical_difficulty"],
            risk_rating=difficulty_ratings["risk_rating"],
            overall_difficulty=difficulty_ratings["overall_difficulty"],
            elevation_profile=[
                ElevationPoint(
                    distance_meters=p["distance_meters"],
                    elevation_meters=p["elevation_meters"] or 0,
                    grade_percent=p["grade_percent"],
                    coordinate=Coordinate(**p["coordinate"]),
                )
                for p in elevation_profile
            ],
            confidence_score=confidence,
            data_completeness=self._calculate_data_completeness(segment_metadata),
        )

    def _calculate_total_distance(self, coordinates: List[List[float]]) -> float:
        """Calculate total route distance."""
        total = 0
        for i in range(1, len(coordinates)):
            total += self._haversine_distance(
                coordinates[i - 1][1], coordinates[i - 1][0],
                coordinates[i][1], coordinates[i][0],
            )
        return total

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two points."""
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

    def _analyze_grades(
        self,
        profile: List[dict],
        total_distance: float,
    ) -> Dict[str, float]:
        """Analyze grade distribution."""
        grades = [abs(p["grade_percent"]) for p in profile if p["grade_percent"] is not None]

        if not grades:
            return {
                "avg_grade": 0,
                "max_grade": 0,
                "longest_climb": 0,
                "steepest_100m": 0,
                "steepest_1km": 0,
                "climbing_above_8": 0,
            }

        # Calculate steepest over windows
        steepest_100m = self._steepest_window(profile, 100)
        steepest_1km = self._steepest_window(profile, 1000)

        # Calculate longest continuous climb
        longest_climb = self._longest_climb(profile)

        # Calculate distance above 8% grade
        climbing_above_8 = self._distance_above_grade(profile, 8)

        return {
            "avg_grade": sum(grades) / len(grades),
            "max_grade": max(grades),
            "longest_climb": longest_climb,
            "steepest_100m": steepest_100m,
            "steepest_1km": steepest_1km,
            "climbing_above_8": climbing_above_8,
        }

    def _steepest_window(self, profile: List[dict], window_meters: float) -> float:
        """Find steepest grade over a distance window."""
        max_grade = 0

        for i, point in enumerate(profile):
            window_gain = 0
            window_distance = 0
            j = i

            while j < len(profile) and window_distance < window_meters:
                if j > i:
                    segment_dist = profile[j]["distance_meters"] - profile[j - 1]["distance_meters"]
                    if profile[j]["elevation_meters"] and profile[j - 1]["elevation_meters"]:
                        elevation_diff = profile[j]["elevation_meters"] - profile[j - 1]["elevation_meters"]
                        if elevation_diff > 0:
                            window_gain += elevation_diff
                    window_distance += segment_dist
                j += 1

            if window_distance >= window_meters * 0.9:  # Allow 90% of window
                grade = (window_gain / window_distance) * 100 if window_distance > 0 else 0
                max_grade = max(max_grade, grade)

        return max_grade

    def _longest_climb(self, profile: List[dict]) -> float:
        """Find longest continuous climb."""
        max_climb = 0
        current_climb = 0

        for i in range(1, len(profile)):
            if profile[i]["elevation_meters"] and profile[i - 1]["elevation_meters"]:
                diff = profile[i]["elevation_meters"] - profile[i - 1]["elevation_meters"]
                if diff > 0:
                    current_climb += diff
                else:
                    max_climb = max(max_climb, current_climb)
                    current_climb = 0

        return max(max_climb, current_climb)

    def _distance_above_grade(self, profile: List[dict], grade_threshold: float) -> float:
        """Calculate distance where grade exceeds threshold."""
        total_distance = 0

        for i in range(1, len(profile)):
            if abs(profile[i]["grade_percent"]) >= grade_threshold:
                total_distance += profile[i]["distance_meters"] - profile[i - 1]["distance_meters"]

        return total_distance

    def _analyze_surfaces(
        self,
        routing_data: Optional[Dict[str, Any]],
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> SurfaceBreakdown:
        """Analyze surface type distribution."""
        surface_distances = {
            "pavement": 0,
            "gravel": 0,
            "dirt": 0,
            "singletrack": 0,
            "unknown": 0,
        }

        total_distance = 0

        # Try to get surface info from routing data
        if routing_data and "surface_breakdown" in routing_data:
            breakdown = routing_data.get("surface_breakdown", {}) or {}
            return SurfaceBreakdown(
                pavement=breakdown.get("paved", 0),
                gravel=breakdown.get("gravel", 0),
                dirt=breakdown.get("ground", 0) + breakdown.get("unpaved", 0),
                singletrack=0,
                unknown=breakdown.get("unknown", 0),
            )
        if routing_data and "surface_info" in routing_data:
            surface_info = routing_data["surface_info"]
            # ORS provides surface info as value ranges
            values = surface_info.get("values", [])
            summary = surface_info.get("summary", [])

            for item in summary:
                surface_type = self._map_surface_value(item.get("value", 0))
                distance = item.get("distance", 0)
                surface_distances[surface_type] += distance
                total_distance += distance

        # Fall back to segment metadata
        elif segment_metadata:
            for segment in segment_metadata:
                surface = segment.get("surface", "unknown")
                highway = segment.get("highway_type", "")
                distance = segment.get("distance_meters", 0)

                # Map surface
                mapped = SURFACE_MAPPING.get(surface, "unknown")

                # Override to singletrack if path/trail
                if highway in SINGLETRACK_HIGHWAYS:
                    mapped = "singletrack"

                surface_distances[mapped] += distance
                total_distance += distance

        # Calculate percentages
        if total_distance > 0:
            return SurfaceBreakdown(
                pavement=(surface_distances["pavement"] / total_distance) * 100,
                gravel=(surface_distances["gravel"] / total_distance) * 100,
                dirt=(surface_distances["dirt"] / total_distance) * 100,
                singletrack=(surface_distances["singletrack"] / total_distance) * 100,
                unknown=(surface_distances["unknown"] / total_distance) * 100,
            )

        return SurfaceBreakdown(unknown=100)

    def _map_surface_value(self, value: int) -> str:
        """Map ORS surface value to our category.
        
        ORS surface codes:
        0=Unknown, 1=Paved, 2=Unpaved, 3=Asphalt, 4=Concrete,
        5=Cobblestone, 6=Metal, 7=Wood, 8=Compacted Gravel, 9=Fine Gravel,
        10=Gravel, 11=Dirt, 12=Ground, 13=Ice, 14=Salt, 15=Sand,
        16=Woodchips, 17=Grass, 18=Paving stones
        """
        # Map to our surface categories
        if value == 0:
            return "unknown"
        elif value in [1, 3, 4, 5, 6, 18]:  # Paved surfaces
            return "pavement"
        elif value in [8, 9, 10]:  # Gravel surfaces
            return "gravel"
        elif value in [11, 12, 15, 16, 17]:  # Dirt/ground surfaces
            return "dirt"
        elif value == 2:  # Unpaved (generic - usually gravel or dirt)
            return "gravel"  # Default to gravel for generic unpaved
        elif value in [7, 13, 14]:  # Special cases
            return "unknown"  # Wood, ice, salt are uncommon and hard to categorize
        return "unknown"

    def _analyze_mtb_difficulty(
        self,
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> MTBDifficultyBreakdown:
        """Analyze MTB difficulty distribution."""
        difficulty_distances = {
            "green": 0,
            "blue": 0,
            "black": 0,
            "double_black": 0,
            "unknown": 0,
        }

        total_distance = 0

        if segment_metadata:
            for segment in segment_metadata:
                mtb_scale = segment.get("mtb_scale")
                distance = segment.get("distance_meters", 0)
                total_distance += distance

                if mtb_scale is not None:
                    # Round to nearest integer for mapping
                    scale_int = min(5, max(0, round(mtb_scale)))
                    difficulty = MTB_SCALE_DIFFICULTY.get(scale_int, "unknown")
                    difficulty_distances[difficulty] += distance
                else:
                    difficulty_distances["unknown"] += distance

        if total_distance > 0:
            return MTBDifficultyBreakdown(
                green=(difficulty_distances["green"] / total_distance) * 100,
                blue=(difficulty_distances["blue"] / total_distance) * 100,
                black=(difficulty_distances["black"] / total_distance) * 100,
                double_black=(difficulty_distances["double_black"] / total_distance) * 100,
                unknown=(difficulty_distances["unknown"] / total_distance) * 100,
            )

        return MTBDifficultyBreakdown(unknown=100)

    def _get_max_technical_rating(
        self,
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> Optional[float]:
        """Get maximum technical rating encountered."""
        if not segment_metadata:
            return None

        ratings = [
            s.get("mtb_scale")
            for s in segment_metadata
            if s.get("mtb_scale") is not None
        ]

        return max(ratings) if ratings else None

    def _count_hike_a_bike(
        self,
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> int:
        """Count segments likely requiring hike-a-bike."""
        if not segment_metadata:
            return 0

        count = 0
        for segment in segment_metadata:
            # Consider hike-a-bike if:
            # - MTB scale >= 4
            # - Very steep (>25% grade)
            # - SAC scale >= T3 (demanding mountain hiking)
            mtb_scale = segment.get("mtb_scale", 0) or 0
            max_grade = abs(segment.get("max_grade", 0) or 0)
            sac_scale = segment.get("sac_scale", "")

            if mtb_scale >= 4 or max_grade > 25 or sac_scale in ["T3", "T4", "T5", "T6"]:
                count += 1

        return count

    def _sum_hike_a_bike_distance(
        self,
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> float:
        """Sum distance of hike-a-bike sections."""
        if not segment_metadata:
            return 0

        total = 0
        for segment in segment_metadata:
            mtb_scale = segment.get("mtb_scale", 0) or 0
            max_grade = abs(segment.get("max_grade", 0) or 0)
            sac_scale = segment.get("sac_scale", "")

            if mtb_scale >= 4 or max_grade > 25 or sac_scale in ["T3", "T4", "T5", "T6"]:
                total += segment.get("distance_meters", 0)

        return total

    def _calculate_difficulty_ratings(
        self,
        elevation_stats: Dict[str, float],
        grade_analysis: Dict[str, float],
        surface_breakdown: SurfaceBreakdown,
        mtb_breakdown: MTBDifficultyBreakdown,
        total_distance: float,
    ) -> Dict[str, float]:
        """Calculate difficulty ratings (0-5 scale)."""
        # Physical difficulty based on elevation and distance
        elevation_per_km = (
            elevation_stats["elevation_gain_meters"] / (total_distance / 1000)
            if total_distance > 0
            else 0
        )

        physical = min(5, (
            (elevation_per_km / 20) +  # 100m/km = 5
            (grade_analysis["steepest_1km"] / 4) +  # 20% grade = 5
            (total_distance / 100000)  # 100km = 1 point
        ) / 2)

        # Technical difficulty from MTB breakdown and surfaces
        tech_score = (
            (mtb_breakdown.blue * 0.02) +
            (mtb_breakdown.black * 0.04) +
            (mtb_breakdown.double_black * 0.05) +
            (surface_breakdown.singletrack * 0.02)
        )
        technical = min(5, tech_score)

        # Risk rating
        risk = min(5, (
            (mtb_breakdown.black * 0.03) +
            (mtb_breakdown.double_black * 0.05) +
            (grade_analysis["max_grade"] / 10)
        ))

        # Overall weighted average
        overall = (physical * 0.4 + technical * 0.4 + risk * 0.2)

        return {
            "physical_difficulty": round(physical, 1),
            "technical_difficulty": round(technical, 1),
            "risk_rating": round(risk, 1),
            "overall_difficulty": round(overall, 1),
        }

    def _estimate_time(
        self,
        distance_meters: float,
        elevation_gain_meters: float,
        surface_breakdown: SurfaceBreakdown,
        technical_difficulty: float,
    ) -> int:
        """Estimate ride time in seconds."""
        # Base speed assumptions (m/s)
        BASE_SPEED = 5.0  # ~18 km/h on flat road

        # Adjust for surface
        surface_factor = (
            (surface_breakdown.pavement / 100 * 1.0) +
            (surface_breakdown.gravel / 100 * 0.85) +
            (surface_breakdown.dirt / 100 * 0.75) +
            (surface_breakdown.singletrack / 100 * 0.6) +
            (surface_breakdown.unknown / 100 * 0.8)
        )

        # Adjust for technical difficulty
        tech_factor = max(0.5, 1 - (technical_difficulty * 0.1))

        adjusted_speed = BASE_SPEED * surface_factor * tech_factor

        # Time for distance
        distance_time = distance_meters / adjusted_speed

        # Add time for climbing (Naismith's rule: +1 hour per 600m gain)
        climb_time = (elevation_gain_meters / 600) * 3600

        total_seconds = distance_time + climb_time

        return int(total_seconds)

    def _calculate_confidence(
        self,
        routing_data: Optional[Dict[str, Any]],
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> float:
        """Calculate confidence score (0-100)."""
        score = 50  # Base score

        if routing_data:
            score += 20  # Have routing data

            if "surface_info" in routing_data or "surface_breakdown" in routing_data:
                score += 10

            if "steepness_info" in routing_data:
                score += 10

        if segment_metadata:
            # Check data completeness
            completeness = self._calculate_data_completeness(segment_metadata)
            score += completeness * 0.1

        return min(100, max(0, score))

    def _calculate_data_completeness(
        self,
        segment_metadata: Optional[List[Dict[str, Any]]],
    ) -> float:
        """Calculate data completeness percentage."""
        if not segment_metadata:
            return 0

        fields = ["surface", "mtb_scale", "bicycle_access", "highway_type"]
        total_fields = len(segment_metadata) * len(fields)
        filled_fields = 0

        for segment in segment_metadata:
            for field in fields:
                if segment.get(field) is not None:
                    filled_fields += 1

        return (filled_fields / total_fields * 100) if total_fields > 0 else 0


# Singleton
_analysis_service: Optional[RouteAnalysisService] = None


async def get_analysis_service() -> RouteAnalysisService:
    """Get or create analysis service instance."""
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = RouteAnalysisService()
    return _analysis_service
