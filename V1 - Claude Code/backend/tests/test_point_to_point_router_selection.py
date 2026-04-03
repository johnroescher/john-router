"""Unit tests for point-to-point router selection heuristics."""
import pytest

from app.services.point_to_point_router_selection import (
    haversine_distance_meters,
    haversine_endpoint_gap_meters,
    is_two_point_long_segment,
    is_unreasonable_detour,
    route_score,
)


def test_haversine_known_short_distance():
    """Golden: ~111m per degree latitude at equator; Denver-scale points should be small."""
    a = [-105.27, 39.74]
    b = [-105.27, 39.75]
    d = haversine_distance_meters(a, b)
    assert 800 < d < 1300


def test_route_score_prefers_smaller_gap():
    direct = 5000.0
    low_gap = {
        "geometry": {"coordinates": [[-105.0, 39.7], [-105.0, 39.71], [-105.0, 39.72]]},
        "distance_meters": 5200,
    }
    start = [-105.0, 39.7]
    end = [-105.0, 39.72]
    g_low = low_gap["geometry"]["coordinates"]
    # Same distance, but geometry endpoints drift from requested start/end → higher gap penalty
    g_high = [[-104.5, 39.75], [-105.0, 39.71], [-104.95, 39.73]]
    s_low = route_score(
        low_gap,
        direct,
        haversine_endpoint_gap_meters(g_low, start, end),
    )
    s_high = route_score(
        {**low_gap, "geometry": {"coordinates": g_high}},
        direct,
        haversine_endpoint_gap_meters(g_high, start, end),
    )
    assert s_low < s_high


def test_is_unreasonable_detour():
    assert is_unreasonable_detour(10000, 5000) is True
    assert is_unreasonable_detour(7000, 5000) is False


def test_is_two_point_long_segment():
    assert is_two_point_long_segment([[0, 0], [1, 1]], 100) is True
    assert is_two_point_long_segment([[0, 0], [1, 1]], 10) is False
