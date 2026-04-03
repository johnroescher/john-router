"""Tests for planning quality helpers."""
from datetime import datetime

from app.schemas.planning import IntentObject, IntentSource, DiscoveryQuery
from app.services.ride_brief_loop import RideBriefLoopService


def _build_intent() -> IntentObject:
    intent = IntentObject(
        intent_id="intent-123",
        timestamp=datetime.utcnow().isoformat(),
        source=IntentSource(raw_text="scenic quiet gravel loop"),
    )
    intent.hard_constraints.discipline = "gravel"
    intent.soft_preferences.scenic_bias = "high"
    intent.soft_preferences.traffic_stress_max = "low"
    return intent


def test_rank_and_prune_specs_prefers_quality_fit():
    service = RideBriefLoopService()
    intent = _build_intent()

    specs = [
        {"label": "A", "routing_profile": "gravel", "confidence": 0.8, "expected_fit": ["scenic"]},
        {"label": "B", "routing_profile": "road", "confidence": 0.2, "expected_fit": []},
        {"label": "C", "routing_profile": "gravel", "confidence": 0.4, "expected_fit": ["low_traffic"]},
        {"label": "D", "routing_profile": "mtb", "confidence": 0.1, "expected_fit": ["scenic"]},
    ]

    ranked = service._rank_and_prune_specs(specs, intent)

    assert len(ranked) >= 3
    assert ranked[0]["label"] == "A"
    assert all("quality_score" in spec for spec in ranked)
    scores = [spec["quality_score"] for spec in ranked]
    assert scores == sorted(scores, reverse=True)


def test_prioritize_discovery_queries_orders_by_priority():
    service = RideBriefLoopService()
    queries = [
        DiscoveryQuery(id="q1", purpose="trails", tool="overpass", parameters={"query": "way"}),  # lower priority
        DiscoveryQuery(id="q2", purpose="views", tool="pois", parameters={"types": ["viewpoint", "scenic"]}),
        DiscoveryQuery(id="q3", purpose="water", tool="pois", parameters={"types": ["water"]}),
    ]

    prioritized = service._prioritize_discovery_queries(queries, ["scenic", "poi"])

    assert prioritized[0].tool == "pois"
    assert "priority" in prioritized[0].parameters
