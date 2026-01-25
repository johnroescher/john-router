from app.services.surface_match import _build_segmented_surface_data, classify_way_surface
from app.schemas.route import SurfaceSegment


def test_classify_way_surface_explicit_tags():
    surface_type, confidence = classify_way_surface({"surface": "gravel"})
    assert surface_type == "gravel"
    assert confidence > 0.9


def test_classify_way_surface_variable_highway():
    surface_type, confidence = classify_way_surface({"highway": "residential"})
    assert surface_type == "unknown"
    assert confidence <= 0.4


def test_build_segmented_surface_data_quality_metrics():
    geometry = [
        [-105.0, 39.0],
        [-105.0, 39.0005],
        [-105.0, 39.0010],
    ]
    segments = [
        SurfaceSegment(
            startIndex=0,
            endIndex=1,
            startDistanceMeters=0.0,
            endDistanceMeters=50.0,
            distanceMeters=50.0,
            surfaceType="gravel",
            confidence=0.9,
            matchDistanceMeters=5.0,
            source="overpass",
            osmWayId=123,
        ),
        SurfaceSegment(
            startIndex=1,
            endIndex=2,
            startDistanceMeters=50.0,
            endDistanceMeters=100.0,
            distanceMeters=50.0,
            surfaceType="unknown",
            confidence=0.2,
            matchDistanceMeters=None,
            source="map_inference",
            osmWayId=None,
        ),
    ]

    segmented = _build_segmented_surface_data(
        geometry,
        segments,
        known_distance=50.0,
        confidence_sum=45.0,
        match_distance_sum=250.0,
    )

    assert segmented.dataQuality > 0
    assert segmented.qualityMetrics is not None
    assert segmented.qualityMetrics.avgConfidence > 0
