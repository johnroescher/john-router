"""Tests for route validation service."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.validation import RouteValidationService
from app.schemas.route import (
    SurfaceBreakdown,
    MTBDifficultyBreakdown,
    RouteConstraints,
    Coordinate,
    SportType,
    MTBDifficulty,
)


@pytest.fixture
def validation_service():
    """Create a validation service instance."""
    return RouteValidationService()


@pytest.fixture
def sample_analysis():
    """Create sample route analysis result."""
    return {
        "distance_meters": 15000,
        "elevation_gain_meters": 500,
        "elevation_loss_meters": 450,
        "max_elevation_meters": 2100,
        "min_elevation_meters": 1600,
        "surface_breakdown": SurfaceBreakdown(
            pavement=20, gravel=30, dirt=10, singletrack=35, unknown=5
        ),
        "mtb_difficulty_breakdown": MTBDifficultyBreakdown(
            green=20, blue=40, black=30, double_black=5, unknown=5
        ),
        "physical_difficulty": 3.0,
        "technical_difficulty": 3.5,
        "overall_difficulty": 3.25,
        "hike_a_bike_count": 1,
        "grade_analysis": {
            "avg_grade": 5.0,
            "max_grade": 18.0,
            "steepest_1km": 12.0,
        },
    }


@pytest.fixture
def sample_constraints():
    """Create sample route constraints."""
    return RouteConstraints(
        start=Coordinate(lat=39.7, lng=-105.0),
        sport_type=SportType.MTB,
        mtb_difficulty_target=MTBDifficulty.MODERATE,
        max_uphill_grade_percent=15.0,
        min_distance_meters=10000,
        max_distance_meters=20000,
    )


@pytest.fixture
def sample_segments():
    """Create sample route segments."""
    return [
        {
            "highway_type": "cycleway",
            "bicycle_access": "designated",
            "surface": "asphalt",
            "mtb_scale": None,
            "max_grade": 5.0,
            "distance_meters": 3000,
        },
        {
            "highway_type": "track",
            "bicycle_access": "yes",
            "surface": "gravel",
            "mtb_scale": 1.0,
            "max_grade": 8.0,
            "distance_meters": 5000,
        },
        {
            "highway_type": "path",
            "bicycle_access": "yes",
            "surface": "ground",
            "mtb_scale": 2.0,
            "max_grade": 15.0,
            "distance_meters": 7000,
        },
    ]


class TestRouteValidationService:
    """Test cases for RouteValidationService."""

    def test_check_connectivity_valid(self, validation_service):
        """Test connectivity check with valid geometry."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.001, 39.701],
                [-105.002, 39.702],
            ],
        }

        issues = validation_service._check_connectivity(geometry["coordinates"])
        # No gaps, should pass
        assert all(i.severity != "error" for i in issues)

    def test_check_connectivity_with_gap(self, validation_service):
        """Test connectivity check with gap in geometry."""
        # Create geometry with a large gap (> 500m)
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.01, 39.71],
                [-105.5, 39.75],  # Large gap
                [-105.51, 39.76],
            ],
        }

        issues = validation_service._check_connectivity(geometry["coordinates"])
        # Should detect gap
        gap_issues = [i for i in issues if "gap" in i.message.lower()]
        assert len(gap_issues) > 0

    def test_check_legality_bicycle_access(self, validation_service):
        """Test legality check for bicycle access."""
        segments = [
            {"highway_type": "cycleway", "bicycle_access": "designated"},
            {"highway_type": "path", "bicycle_access": "no"},  # Illegal
            {"highway_type": "track", "bicycle_access": "yes"},
        ]

        issues = validation_service._check_legality(segments, None)
        # Should flag the segment with no bicycle access
        assert len(issues) > 0
        assert any("bicycle" in i.message.lower() or "access" in i.message.lower() for i in issues)

    def test_check_legality_highway_restriction(self, validation_service):
        """Test legality check for restricted highway types."""
        segments = [
            {"highway_type": "cycleway", "bicycle_access": "yes"},
            {"highway_type": "motorway", "bicycle_access": "unknown"},  # Restricted
            {"highway_type": "path", "bicycle_access": "yes"},
        ]

        issues = validation_service._check_legality(segments, None)
        # Should flag motorway
        assert len(issues) > 0

    def test_check_safety_steep_grade(self, validation_service):
        """Test safety check for steep grades."""
        segments = [
            {"max_grade": 5.0, "highway_type": "path"},
            {"max_grade": 25.0, "highway_type": "path"},  # Very steep
            {"max_grade": 8.0, "highway_type": "path"},
        ]

        coords = [
            [-105.0, 39.7],
            [-105.01, 39.71],
            [-105.02, 39.72],
        ]
        issues = validation_service._check_safety(segments, coords)
        # Should flag steep segment
        assert len(issues) > 0
        assert any("grade" in i.message.lower() or "steep" in i.message.lower() for i in issues)

    def test_check_safety_high_traffic(self, validation_service):
        """Test safety check for high-traffic roads."""
        segments = [
            {"highway_type": "cycleway", "traffic_level": "low"},
            {"highway_type": "primary", "traffic_level": "high"},  # High traffic
            {"highway_type": "path", "traffic_level": "none"},
        ]

        coords = [
            [-105.0, 39.7],
            [-105.01, 39.71],
            [-105.02, 39.72],
        ]
        issues = validation_service._check_safety(segments, coords)
        # Should flag high-traffic road
        assert len(issues) > 0
        assert any("traffic" in i.message.lower() for i in issues)

    def test_check_mtb_difficulty_match(self, validation_service):
        """Test MTB difficulty matching."""
        segments = [
            {"mtb_scale": 3.0, "max_grade": 10.0, "min_grade": -5.0},
        ]
        constraints = RouteConstraints(
            start=Coordinate(lat=39.7, lng=-105.0),
            sport_type=SportType.MTB,
            mtb_difficulty_target=MTBDifficulty.EASY,
        )

        # User wants easy difficulty but route is harder
        issues = validation_service._check_mtb_difficulty(segments, constraints)

        # Should flag difficulty mismatch
        assert len(issues) > 0

    def test_check_mtb_difficulty_appropriate(self, validation_service):
        """Test MTB difficulty when appropriate."""
        segments = [
            {"mtb_scale": 1.0, "max_grade": 8.0, "min_grade": -5.0},
        ]
        constraints = RouteConstraints(
            start=Coordinate(lat=39.7, lng=-105.0),
            sport_type=SportType.MTB,
            mtb_difficulty_target=MTBDifficulty.MODERATE,
        )

        # User wants moderate, route stays within difficulty
        issues = validation_service._check_mtb_difficulty(segments, constraints)

        # Should have no errors (maybe warnings)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_check_distance_constraints_valid(self, validation_service):
        """Test distance constraint validation when within range."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.01, 39.71],
                [-105.02, 39.72],
            ],
        }
        constraints = RouteConstraints(
            start=Coordinate(lat=39.7, lng=-105.0),
            sport_type=SportType.MTB,
            min_distance_meters=1000,
            max_distance_meters=10000,
        )
        issues = validation_service._check_constraints(geometry, None, constraints)

        # Should pass
        assert len(issues) == 0

    def test_check_distance_constraints_too_short(self, validation_service):
        """Test distance constraint validation when too short."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.005, 39.705],
            ],
        }
        constraints = RouteConstraints(
            start=Coordinate(lat=39.7, lng=-105.0),
            sport_type=SportType.MTB,
            min_distance_meters=3000,
        )
        issues = validation_service._check_constraints(geometry, None, constraints)

        # Should flag as too short
        assert len(issues) > 0
        assert any("short" in i.message.lower() or "distance" in i.message.lower() for i in issues)

    def test_check_distance_constraints_too_long(self, validation_service):
        """Test distance constraint validation when too long."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.2, 39.9],
            ],
        }
        constraints = RouteConstraints(
            start=Coordinate(lat=39.7, lng=-105.0),
            sport_type=SportType.MTB,
            max_distance_meters=2000,
        )
        issues = validation_service._check_constraints(geometry, None, constraints)

        # Should flag as too long
        assert len(issues) > 0
        assert any("long" in i.message.lower() or "distance" in i.message.lower() for i in issues)

    @pytest.mark.asyncio
    async def test_validate_route_integration(
        self, validation_service, sample_analysis, sample_constraints, sample_segments
    ):
        """Test full route validation."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.01, 39.71],
                [-105.02, 39.72],
                [-105.03, 39.73],
            ],
        }

        result = await validation_service.validate_route(
            geometry=geometry,
            constraints=sample_constraints,
            segments=sample_segments,
        )

        assert result.status in ["valid", "warnings", "errors"]
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.info, list)

    @pytest.mark.asyncio
    async def test_validate_route_with_errors(self, validation_service, sample_constraints):
        """Test route validation that produces errors."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-105.0, 39.7],
                [-105.01, 39.71],
            ],
        }

        segments = [
            {"highway_type": "path", "bicycle_access": "no", "max_grade": 25.0},  # Multiple issues
        ]

        result = await validation_service.validate_route(
            geometry=geometry,
            constraints=sample_constraints,
            segments=segments,
        )

        # Should have errors
        assert result.status == "errors"
        assert len(result.errors) > 0


