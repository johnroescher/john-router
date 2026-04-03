"""
Golden route fixtures: stable geometry for regression on analysis invariants.

Uses coordinates with embedded elevation so analysis does not call external
elevation APIs (see ElevationService.get_elevation_profile).
"""
import pytest

from app.services.analysis import RouteAnalysisService
from app.services.validation import RouteValidationService
from app.schemas.route import (
    RouteConstraints,
    SportType,
    RouteType,
    candidate_routing_observability,
)
from app.schemas.common import Coordinate


# Versioned golden loop (Front Range) — all points include elevation (m).
GOLDEN_LOOP_COORDINATES = [
    [-105.2705, 40.0150, 1600],
    [-105.2715, 40.0160, 1610],
    [-105.2725, 40.0155, 1605],
    [-105.2710, 40.0145, 1598],
    [-105.2705, 40.0150, 1600],
]


@pytest.fixture
def golden_geometry():
    return {"type": "LineString", "coordinates": GOLDEN_LOOP_COORDINATES}


@pytest.mark.asyncio
async def test_golden_loop_analysis_invariants(golden_geometry):
    """Distance and confidence stay within sane bands for the golden fixture."""
    service = RouteAnalysisService()
    analysis = await service.analyze_route(golden_geometry, routing_data={}, segment_metadata=[])

    assert analysis.distance_meters > 100
    assert analysis.distance_meters < 50_000
    # Confidence is on a 0–100 style scale in analysis output
    assert 0.0 <= analysis.confidence_score <= 100.0
    assert analysis.surface_breakdown is not None
    assert len(analysis.elevation_profile) >= 2


@pytest.mark.asyncio
async def test_golden_loop_validation_runs(golden_geometry):
    """Validation completes for a typical gravel constraint set."""
    analysis_service = RouteAnalysisService()
    analysis = await analysis_service.analyze_route(golden_geometry, routing_data={}, segment_metadata=[])

    validation_service = RouteValidationService()
    constraints = RouteConstraints(
        sport_type=SportType.GRAVEL,
        route_type=RouteType.LOOP,
        start=Coordinate(lat=40.0150, lng=-105.2705),
        target_distance_meters=5000,
    )
    result = await validation_service.validate_route(
        golden_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")


@pytest.mark.asyncio
async def test_golden_surface_breakdown_sums_to_full_scale(golden_geometry):
    """Surface buckets are normalized to a 0–100 scale (sum ≈ 100)."""
    service = RouteAnalysisService()
    analysis = await service.analyze_route(golden_geometry, routing_data={}, segment_metadata=[])
    sb = analysis.surface_breakdown
    total = sb.pavement + sb.gravel + sb.dirt + sb.singletrack + sb.unknown
    assert 99.0 <= total <= 101.0


@pytest.mark.asyncio
async def test_golden_elevation_profile_monotonic_distance(golden_geometry):
    """Elevation profile distances are non-decreasing along the route."""
    service = RouteAnalysisService()
    analysis = await service.analyze_route(golden_geometry, routing_data={}, segment_metadata=[])
    distances = [p.distance_meters for p in analysis.elevation_profile]
    for i in range(1, len(distances)):
        assert distances[i] >= distances[i - 1] - 1e-6


@pytest.mark.asyncio
async def test_golden_max_grade_sane(golden_geometry):
    """Max grade stays within the clamp used for display / validation."""
    service = RouteAnalysisService()
    analysis = await service.analyze_route(golden_geometry, routing_data={}, segment_metadata=[])
    assert -40.0 <= analysis.max_grade_percent <= 40.0


def test_candidate_routing_observability_maps_engine_and_surface():
    obs = candidate_routing_observability(
        {"source": "ORS", "surface_info": {"source": "valhalla_trace"}, "fallback_reason": "x"}
    )
    assert obs["router_used"] == "ors"
    assert obs["surface_source"] == "valhalla_trace"
    assert obs["fallback_reason"] == "x"

    obs2 = candidate_routing_observability({"geometry": {}})
    assert obs2["router_used"] is None
    assert obs2["surface_source"] == "unknown"
    assert obs2["fallback_reason"] is None


# Road point-to-point (~2 km, Boulder-ish bearing north along a straight-ish corridor).
GOLDEN_ROAD_P2P_COORDINATES = [
    [-105.2750, 40.0120, 1630],
    [-105.2749, 40.0145, 1631],
    [-105.2748, 40.0170, 1633],
    [-105.2747, 40.0195, 1634],
    [-105.2746, 40.0220, 1635],
    [-105.2745, 40.0245, 1636],
    [-105.2744, 40.0270, 1637],
    [-105.2743, 40.0295, 1638],
]

# MTB out-and-back: start == end, ~1 km along path, Front Range style trail wiggle.
GOLDEN_MTB_OAB_COORDINATES = [
    [-105.2880, 40.0280, 1680],
    [-105.2885, 40.0284, 1684],
    [-105.2890, 40.0288, 1688],
    [-105.2895, 40.0292, 1692],
    [-105.2900, 40.0296, 1696],
    [-105.2905, 40.0300, 1700],
    [-105.2900, 40.0296, 1696],
    [-105.2895, 40.0292, 1692],
    [-105.2890, 40.0288, 1688],
    [-105.2880, 40.0280, 1680],
]

# Flat edge case: negligible elevation change (constant 1600 m).
GOLDEN_EDGE_FLAT_COORDINATES = [
    [-105.2720, 40.0140, 1600],
    [-105.2715, 40.0145, 1600],
    [-105.2710, 40.0150, 1600],
    [-105.2705, 40.0155, 1600],
    [-105.2700, 40.0160, 1600],
    [-105.2695, 40.0165, 1600],
]

# Steep edge case: large vertical steps over short horizontal distance (grade clamp).
GOLDEN_EDGE_STEEP_COORDINATES = [
    [-105.2710, 40.0150, 1600],
    [-105.2709, 40.01502, 1650],
    [-105.2708, 40.01504, 1800],
    [-105.2707, 40.01506, 1800],
]


@pytest.fixture
def golden_road_p2p_geometry():
    return {"type": "LineString", "coordinates": GOLDEN_ROAD_P2P_COORDINATES}


@pytest.fixture
def golden_mtb_oab_geometry():
    return {"type": "LineString", "coordinates": GOLDEN_MTB_OAB_COORDINATES}


@pytest.fixture
def golden_edge_flat_geometry():
    return {"type": "LineString", "coordinates": GOLDEN_EDGE_FLAT_COORDINATES}


@pytest.fixture
def golden_edge_steep_geometry():
    return {"type": "LineString", "coordinates": GOLDEN_EDGE_STEEP_COORDINATES}


@pytest.mark.asyncio
async def test_golden_road_p2p_distance_band(golden_road_p2p_geometry):
    analysis_service = RouteAnalysisService()
    analysis = await analysis_service.analyze_route(
        golden_road_p2p_geometry, routing_data={}, segment_metadata=[]
    )
    assert 500 <= analysis.distance_meters <= 10_000

    validation_service = RouteValidationService()
    first = GOLDEN_ROAD_P2P_COORDINATES[0]
    last = GOLDEN_ROAD_P2P_COORDINATES[-1]
    constraints = RouteConstraints(
        sport_type=SportType.ROAD,
        route_type=RouteType.POINT_TO_POINT,
        start=Coordinate(lat=first[1], lng=first[0]),
        end=Coordinate(lat=last[1], lng=last[0]),
        target_distance_meters=2000,
    )
    result = await validation_service.validate_route(
        golden_road_p2p_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")


@pytest.mark.asyncio
async def test_golden_road_p2p_validation_road(golden_road_p2p_geometry):
    await RouteAnalysisService().analyze_route(
        golden_road_p2p_geometry, routing_data={}, segment_metadata=[]
    )

    first = GOLDEN_ROAD_P2P_COORDINATES[0]
    last = GOLDEN_ROAD_P2P_COORDINATES[-1]
    constraints = RouteConstraints(
        sport_type=SportType.ROAD,
        route_type=RouteType.POINT_TO_POINT,
        start=Coordinate(lat=first[1], lng=first[0]),
        end=Coordinate(lat=last[1], lng=last[0]),
        target_distance_meters=2000,
    )
    result = await RouteValidationService().validate_route(
        golden_road_p2p_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")


@pytest.mark.asyncio
async def test_golden_mtb_oab_distance_band(golden_mtb_oab_geometry):
    analysis_service = RouteAnalysisService()
    analysis = await analysis_service.analyze_route(
        golden_mtb_oab_geometry, routing_data={}, segment_metadata=[]
    )
    assert 200 <= analysis.distance_meters <= 10_000

    validation_service = RouteValidationService()
    first = GOLDEN_MTB_OAB_COORDINATES[0]
    constraints = RouteConstraints(
        sport_type=SportType.MTB,
        route_type=RouteType.OUT_AND_BACK,
        start=Coordinate(lat=first[1], lng=first[0]),
        target_distance_meters=1000,
    )
    result = await validation_service.validate_route(
        golden_mtb_oab_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")


@pytest.mark.asyncio
async def test_golden_mtb_oab_validation_mtb(golden_mtb_oab_geometry):
    await RouteAnalysisService().analyze_route(
        golden_mtb_oab_geometry, routing_data={}, segment_metadata=[]
    )

    first = GOLDEN_MTB_OAB_COORDINATES[0]
    constraints = RouteConstraints(
        sport_type=SportType.MTB,
        route_type=RouteType.OUT_AND_BACK,
        start=Coordinate(lat=first[1], lng=first[0]),
        target_distance_meters=1000,
    )
    result = await RouteValidationService().validate_route(
        golden_mtb_oab_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")


@pytest.mark.asyncio
async def test_golden_flat_elevation_gain_near_zero(golden_edge_flat_geometry):
    analysis_service = RouteAnalysisService()
    analysis = await analysis_service.analyze_route(
        golden_edge_flat_geometry, routing_data={}, segment_metadata=[]
    )
    assert analysis.elevation_gain_meters < 5

    validation_service = RouteValidationService()
    first = GOLDEN_EDGE_FLAT_COORDINATES[0]
    constraints = RouteConstraints(
        sport_type=SportType.GRAVEL,
        route_type=RouteType.POINT_TO_POINT,
        start=Coordinate(lat=first[1], lng=first[0]),
        end=Coordinate(
            lat=GOLDEN_EDGE_FLAT_COORDINATES[-1][1],
            lng=GOLDEN_EDGE_FLAT_COORDINATES[-1][0],
        ),
    )
    result = await validation_service.validate_route(
        golden_edge_flat_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")


@pytest.mark.asyncio
async def test_golden_steep_grade_clamped(golden_edge_steep_geometry):
    analysis_service = RouteAnalysisService()
    analysis = await analysis_service.analyze_route(
        golden_edge_steep_geometry, routing_data={}, segment_metadata=[]
    )
    assert -40.0 <= analysis.max_grade_percent <= 40.0

    validation_service = RouteValidationService()
    first = GOLDEN_EDGE_STEEP_COORDINATES[0]
    last = GOLDEN_EDGE_STEEP_COORDINATES[-1]
    constraints = RouteConstraints(
        sport_type=SportType.MTB,
        route_type=RouteType.POINT_TO_POINT,
        start=Coordinate(lat=first[1], lng=first[0]),
        end=Coordinate(lat=last[1], lng=last[0]),
    )
    result = await validation_service.validate_route(
        golden_edge_steep_geometry,
        segments=[],
        constraints=constraints,
    )
    assert result.status in ("valid", "warnings", "errors")
