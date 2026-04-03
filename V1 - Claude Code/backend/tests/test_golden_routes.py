"""
Golden route fixtures: stable geometry for regression on analysis invariants.

Uses coordinates with embedded elevation so analysis does not call external
elevation APIs (see ElevationService.get_elevation_profile).
"""
import pytest

from app.services.analysis import RouteAnalysisService
from app.services.validation import RouteValidationService
from app.schemas.route import RouteConstraints, SportType, RouteType
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
