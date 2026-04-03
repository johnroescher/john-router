"""Tests for route analysis service."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.analysis import RouteAnalysisService
from app.schemas.route import SurfaceBreakdown, MTBDifficultyBreakdown


@pytest.fixture
def analysis_service():
    """Create an analysis service instance."""
    return RouteAnalysisService()


@pytest.fixture
def sample_geometry():
    """Create sample route geometry."""
    return {
        "type": "LineString",
        "coordinates": [
            [-105.0, 39.7, 1600],
            [-105.01, 39.71, 1650],
            [-105.02, 39.72, 1700],
            [-105.03, 39.73, 1680],
            [-105.04, 39.74, 1750],
            [-105.05, 39.75, 1800],
        ],
    }


@pytest.fixture
def sample_segment_metadata():
    """Create sample segment metadata."""
    return [
        {
            "surface": "asphalt",
            "highway_type": "cycleway",
            "mtb_scale": None,
            "bicycle_access": "designated",
            "distance_meters": 1000,
            "max_grade": 5.0,
        },
        {
            "surface": "gravel",
            "highway_type": "track",
            "mtb_scale": 1.0,
            "bicycle_access": "yes",
            "distance_meters": 2000,
            "max_grade": 8.0,
        },
        {
            "surface": "ground",
            "highway_type": "path",
            "mtb_scale": 2.0,
            "bicycle_access": "yes",
            "distance_meters": 3000,
            "max_grade": 12.0,
        },
    ]


class TestRouteAnalysisService:
    """Test cases for RouteAnalysisService."""

    def test_calculate_total_distance(self, analysis_service, sample_geometry):
        """Test distance calculation."""
        coords = sample_geometry["coordinates"]
        distance = analysis_service._calculate_total_distance(coords)

        # Should be approximately 6-7.5 km based on coordinate spread
        assert 6000 < distance < 7500

    def test_haversine_distance(self, analysis_service):
        """Test Haversine distance calculation."""
        # Approximately 1 degree of latitude = 111km
        dist = analysis_service._haversine_distance(39.0, -105.0, 40.0, -105.0)

        # Should be approximately 111km (111,000m)
        assert 110000 < dist < 112000

    def test_analyze_surfaces_from_metadata(self, analysis_service, sample_segment_metadata):
        """Test surface analysis from segment metadata."""
        breakdown = analysis_service._analyze_surfaces(None, sample_segment_metadata)

        # Total distance: 6000m
        # Pavement: 1000m (16.7%)
        # Gravel: 2000m (33.3%)
        # Singletrack: 3000m (50%)
        assert breakdown.pavement > 15 and breakdown.pavement < 18
        assert breakdown.gravel > 32 and breakdown.gravel < 35
        assert breakdown.singletrack > 48 and breakdown.singletrack < 52

    def test_analyze_mtb_difficulty(self, analysis_service, sample_segment_metadata):
        """Test MTB difficulty analysis."""
        breakdown = analysis_service._analyze_mtb_difficulty(sample_segment_metadata)

        # Segment 1: no mtb_scale (unknown) - 1000m
        # Segment 2: mtb_scale 1 (blue) - 2000m
        # Segment 3: mtb_scale 2 (black) - 3000m

        # Total: 6000m
        assert breakdown.unknown > 15  # ~16.7%
        assert breakdown.blue > 30  # ~33.3%
        assert breakdown.black > 48  # ~50%

    def test_count_hike_a_bike(self, analysis_service):
        """Test hike-a-bike section counting."""
        segments = [
            {"mtb_scale": 2.0, "max_grade": 10.0, "sac_scale": ""},
            {"mtb_scale": 4.0, "max_grade": 15.0, "sac_scale": ""},  # Should count
            {"mtb_scale": 1.0, "max_grade": 30.0, "sac_scale": ""},  # Should count (steep)
            {"mtb_scale": 2.0, "max_grade": 10.0, "sac_scale": "T4"},  # Should count
        ]

        count = analysis_service._count_hike_a_bike(segments)
        assert count == 3

    def test_calculate_difficulty_ratings(self, analysis_service):
        """Test difficulty rating calculation."""
        elevation_stats = {
            "elevation_gain_meters": 500,
            "elevation_loss_meters": 500,
            "max_elevation_meters": 2000,
            "min_elevation_meters": 1500,
        }

        grade_analysis = {
            "avg_grade": 5.0,
            "max_grade": 15.0,
            "steepest_1km": 10.0,
        }

        surface_breakdown = SurfaceBreakdown(
            pavement=20, gravel=30, dirt=10, singletrack=35, unknown=5
        )

        mtb_breakdown = MTBDifficultyBreakdown(
            green=20, blue=40, black=30, double_black=5, unknown=5
        )

        ratings = analysis_service._calculate_difficulty_ratings(
            elevation_stats,
            grade_analysis,
            surface_breakdown,
            mtb_breakdown,
            total_distance=15000,
        )

        assert "physical_difficulty" in ratings
        assert "technical_difficulty" in ratings
        assert "risk_rating" in ratings
        assert "overall_difficulty" in ratings

        # All ratings should be 0-5
        for key, value in ratings.items():
            assert 0 <= value <= 5

    def test_estimate_time(self, analysis_service):
        """Test time estimation."""
        # 10km on pavement should be faster than 10km on singletrack
        pavement_breakdown = SurfaceBreakdown(
            pavement=100, gravel=0, dirt=0, singletrack=0, unknown=0
        )

        singletrack_breakdown = SurfaceBreakdown(
            pavement=0, gravel=0, dirt=0, singletrack=100, unknown=0
        )

        pavement_time = analysis_service._estimate_time(
            distance_meters=10000,
            elevation_gain_meters=100,
            surface_breakdown=pavement_breakdown,
            technical_difficulty=1.0,
        )

        singletrack_time = analysis_service._estimate_time(
            distance_meters=10000,
            elevation_gain_meters=100,
            surface_breakdown=singletrack_breakdown,
            technical_difficulty=3.0,
        )

        # Singletrack should take longer
        assert singletrack_time > pavement_time

    def test_steepest_window(self, analysis_service):
        """Test steepest grade over window calculation."""
        profile = [
            {"distance_meters": 0, "elevation_meters": 1600, "grade_percent": 0},
            {"distance_meters": 100, "elevation_meters": 1610, "grade_percent": 10},
            {"distance_meters": 200, "elevation_meters": 1625, "grade_percent": 15},
            {"distance_meters": 300, "elevation_meters": 1635, "grade_percent": 10},
            {"distance_meters": 400, "elevation_meters": 1640, "grade_percent": 5},
        ]

        steepest = analysis_service._steepest_window(profile, 100)

        # Steepest 100m section should be around 15m gain = 15%
        assert steepest >= 10

    def test_longest_climb(self, analysis_service):
        """Test longest continuous climb calculation."""
        profile = [
            {"distance_meters": 0, "elevation_meters": 1600},
            {"distance_meters": 100, "elevation_meters": 1650},  # +50
            {"distance_meters": 200, "elevation_meters": 1700},  # +50 (total 100)
            {"distance_meters": 300, "elevation_meters": 1680},  # -20 (ends climb)
            {"distance_meters": 400, "elevation_meters": 1720},  # +40
            {"distance_meters": 500, "elevation_meters": 1800},  # +80 (total 120)
        ]

        longest = analysis_service._longest_climb(profile)

        # Longest climb is the second one: 40 + 80 = 120m
        assert longest == 120

    @pytest.mark.asyncio
    async def test_analyze_route_integration(self, analysis_service, sample_geometry):
        """Test full route analysis."""
        with patch.object(
            analysis_service,
            "elevation_service",
            new_callable=lambda: AsyncMock(),
        ):
            # Mock elevation profile
            analysis_service.elevation_service = AsyncMock()
            analysis_service.elevation_service.get_elevation_profile = AsyncMock(
                return_value=[
                    {"distance_meters": 0, "elevation_meters": 1600, "grade_percent": 0, "coordinate": {"lng": -105.0, "lat": 39.7}},
                    {"distance_meters": 1000, "elevation_meters": 1650, "grade_percent": 5, "coordinate": {"lng": -105.01, "lat": 39.71}},
                    {"distance_meters": 2000, "elevation_meters": 1700, "grade_percent": 5, "coordinate": {"lng": -105.02, "lat": 39.72}},
                ]
            )
            analysis_service.elevation_service.calculate_stats = lambda x: {
                "elevation_gain_meters": 100,
                "elevation_loss_meters": 50,
                "max_elevation_meters": 1700,
                "min_elevation_meters": 1600,
                "avg_grade_percent": 5,
                "max_grade_percent": 8,
                "min_grade_percent": 0,
            }

            analysis = await analysis_service.analyze_route(sample_geometry)

            assert analysis.distance_meters > 0
            assert analysis.elevation_gain_meters >= 0
            assert len(analysis.elevation_profile) > 0
