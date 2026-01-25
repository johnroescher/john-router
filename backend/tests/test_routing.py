"""Tests for routing service."""
import math
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.routing import RoutingService
from app.schemas.route import RouteConstraints, SportType, RouteType, MTBDifficulty
from app.schemas.common import Coordinate


def _haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points (meters)."""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@pytest.fixture
def routing_service():
    """Create a routing service instance."""
    service = RoutingService()
    return service


@pytest.fixture
def basic_constraints():
    """Create basic route constraints."""
    return RouteConstraints(
        start=Coordinate(lat=39.7392, lng=-104.9903),
        route_type=RouteType.LOOP,
        sport_type=SportType.MTB,
        target_distance_meters=16000,
        mtb_difficulty_target=MTBDifficulty.MODERATE,
    )


class TestRoutingService:
    """Test cases for RoutingService."""

    def test_point_at_distance(self, routing_service):
        """Test calculating a point at a given distance and bearing."""
        start = Coordinate(lat=39.7392, lng=-104.9903)

        # Calculate point 1km north
        result = routing_service._point_at_distance(start, 1000, 0)

        # Should be approximately 0.009 degrees north
        assert abs(result.lat - 39.7482) < 0.01
        assert abs(result.lng - start.lng) < 0.001

    def test_generate_loop_anchors(self, routing_service):
        """Test generating anchor points for a loop."""
        center = Coordinate(lat=39.7392, lng=-104.9903)

        anchors = routing_service._generate_loop_anchors(
            center=center,
            radius=5000,  # 5km radius
            num_anchors=4,
            base_bearing=0,
        )

        assert len(anchors) == 4

        # All anchors should be roughly 5km from center
        for anchor in anchors:
            dist = _haversine_distance_meters(
                center.lat, center.lng,
                anchor.lat, anchor.lng,
            )
            # Allow for randomness in radius (0.7-1.3 multiplier)
            assert 3500 < dist < 6500

    def test_calculate_elevation_gain(self, routing_service):
        """Test elevation gain calculation."""
        # Coordinates with elevation [lng, lat, ele]
        coords = [
            [-105.0, 39.7, 1600],
            [-105.1, 39.8, 1700],  # +100
            [-105.2, 39.9, 1650],  # -50 (loss)
            [-105.3, 40.0, 1800],  # +150
        ]

        gain = routing_service._calculate_elevation_gain(coords)
        assert gain == 250  # 100 + 150

    def test_calculate_elevation_loss(self, routing_service):
        """Test elevation loss calculation."""
        coords = [
            [-105.0, 39.7, 1800],
            [-105.1, 39.8, 1700],  # -100
            [-105.2, 39.9, 1750],  # +50 (gain)
            [-105.3, 40.0, 1600],  # -150
        ]

        loss = routing_service._calculate_elevation_loss(coords)
        assert loss == 250  # 100 + 150

    def test_valhalla_edge_surface_mapping(self, routing_service):
        """Test Valhalla edge surface mapping contract."""
        detailed, base, confidence = routing_service._map_valhalla_edge_surface(
            {"surface": "asphalt", "use": "cycleway"}
        )
        assert detailed == "pavement"
        assert base == "paved"
        assert confidence >= 0.9

        detailed, base, confidence = routing_service._map_valhalla_edge_surface(
            {"unpaved": True, "use": "track"}
        )
        assert detailed == "singletrack"
        assert base == "unpaved"
        assert confidence >= 0.7

        detailed, base, confidence = routing_service._map_valhalla_edge_surface(
            {"use": "footway"}
        )
        assert detailed == "singletrack"
        assert base == "unknown"
        assert confidence >= 0.6

    def test_build_ors_options_with_avoid_highways(self, routing_service, basic_constraints):
        """Test building ORS options with highway avoidance."""
        basic_constraints.avoid_highways = True

        options = routing_service._build_ors_options(basic_constraints, "driving-car")

        assert options is not None
        assert "avoid_features" in options

    def test_build_ors_options_with_avoid_areas(self, routing_service, basic_constraints):
        """Test building ORS options with avoid areas."""
        basic_constraints.avoid_areas = [
            [
                Coordinate(lat=39.74, lng=-105.0),
                Coordinate(lat=39.75, lng=-105.0),
                Coordinate(lat=39.75, lng=-104.99),
                Coordinate(lat=39.74, lng=-104.99),
            ]
        ]

        options = routing_service._build_ors_options(basic_constraints, "driving-car")

        assert "avoid_polygons" in options
        assert options["avoid_polygons"]["type"] == "MultiPolygon"

    @pytest.mark.asyncio
    async def test_generate_route_mock(self, routing_service, basic_constraints):
        """Test route generation with mocked API call."""
        basic_constraints.sport_type = SportType.ROAD
        # Mock the ORS API response
        mock_response = {
            "features": [
                {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-104.9903, 39.7392, 1609],
                            [-104.9950, 39.7450, 1650],
                            [-104.9900, 39.7500, 1700],
                            [-104.9850, 39.7450, 1650],
                            [-104.9903, 39.7392, 1609],
                        ],
                    },
                    "properties": {
                        "summary": {"distance": 16000, "duration": 3600},
                        "segments": [],
                        "extras": {},
                    },
                }
            ]
        }

        with patch.object(
            routing_service, "_call_ors_directions", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_response

            candidates = await routing_service.generate_route(basic_constraints)

            assert len(candidates) > 0
            assert candidates[0]["distance_meters"] == 16000

    def test_combine_routes(self, routing_service):
        """Test combining two routes for out-and-back."""
        route1 = {
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-105.0, 39.7, 1600],
                    [-105.1, 39.8, 1700],
                ],
            },
            "distance_meters": 5000,
            "duration_seconds": 1000,
            "elevation_gain": 100,
            "elevation_loss": 0,
            "segments": [{"distance_meters": 5000}],
            "surface_info": {},
            "instructions": [],
        }

        route2 = {
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-105.1, 39.8, 1700],
                    [-105.0, 39.7, 1600],
                ],
            },
            "distance_meters": 5000,
            "duration_seconds": 1000,
            "elevation_gain": 0,
            "elevation_loss": 100,
            "segments": [{"distance_meters": 5000}],
            "surface_info": {},
            "instructions": [],
        }

        combined = routing_service._combine_routes(route1, route2)

        assert combined["distance_meters"] == 10000
        assert combined["duration_seconds"] == 2000
        assert combined["elevation_gain"] == 100
        assert combined["elevation_loss"] == 100
        assert len(combined["geometry"]["coordinates"]) == 3  # First coord of route2 skipped


class TestRoutingServiceProfiles:
    """Test ORS profile selection."""

    def test_road_profile(self):
        """Test road sport type uses correct profile."""
        service = RoutingService()
        assert service.ORS_PROFILES[SportType.ROAD] == "driving-car"

    def test_gravel_profile(self):
        """Test gravel sport type uses correct profile."""
        service = RoutingService()
        assert service.ORS_PROFILES[SportType.GRAVEL] == "cycling-regular"

    def test_mtb_profile(self):
        """Test MTB sport type uses correct profile."""
        service = RoutingService()
        assert service.ORS_PROFILES[SportType.MTB] == "cycling-mountain"

    def test_emtb_profile(self):
        """Test eMTB sport type uses correct profile."""
        service = RoutingService()
        assert service.ORS_PROFILES[SportType.EMTB] == "cycling-electric"
