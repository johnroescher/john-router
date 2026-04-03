import pytest

from app.api import routes as routes_api
from app.schemas.route import SportType


def test_max_connector_distance_meters():
    assert routes_api._max_connector_distance_meters(SportType.MTB) == 250
    assert routes_api._max_connector_distance_meters(SportType.GRAVEL) == 250
    assert routes_api._max_connector_distance_meters(SportType.EMTB) == 250
    assert routes_api._max_connector_distance_meters(SportType.ROAD) == 100


def test_apply_connector_segments_adds_start_and_end():
    geometry = [
        [-97.0, 30.0],
        [-97.0002, 30.0002],
    ]
    original_start = [-97.0, 30.0]
    original_end = [-97.0003, 30.0003]
    snapped_start = [-97.00005, 30.00005]
    snapped_end = [-97.00025, 30.00025]

    result = routes_api._apply_connector_segments(
        geometry=geometry,
        original_start=original_start,
        original_end=original_end,
        snapped_start=snapped_start,
        snapped_end=snapped_end,
        max_connector_distance_meters=250,
    )

    assert result is not None
    updated = result["geometry"]
    assert updated[0] == original_start
    assert updated[-1] == original_end
    assert "start_connector" not in result["reasons"]
    assert "end_connector" in result["reasons"]


def test_apply_connector_segments_rejects_long_connectors():
    geometry = [
        [-97.0, 30.0],
        [-97.0002, 30.0002],
    ]
    original_start = [-97.0, 30.0]
    original_end = [-97.0, 30.01]  # ~1.1km
    snapped_start = [-97.00005, 30.00005]
    snapped_end = [-97.0, 30.0002]

    result = routes_api._apply_connector_segments(
        geometry=geometry,
        original_start=original_start,
        original_end=original_end,
        snapped_start=snapped_start,
        snapped_end=snapped_end,
        max_connector_distance_meters=100,
    )

    assert result is None
