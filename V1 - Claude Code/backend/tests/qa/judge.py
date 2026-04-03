"""Quality judge for route responses.

Scores API responses against per-scenario expectations and produces
a structured QualityVerdict with individual check results.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QualityVerdict:
    scenario: str
    passed: bool
    checks: Dict[str, bool]
    notes: List[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    status_code: int = 0
    raw: Optional[Dict[str, Any]] = None

    @property
    def failed_checks(self) -> List[str]:
        return [k for k, v in self.checks.items() if not v]

    def summary_line(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        fails = ", ".join(self.failed_checks) if self.failed_checks else ""
        extra = f"  [{fails}]" if fails else ""
        return f"  [{mark}] {self.scenario} ({self.elapsed_s:.1f}s){extra}"


def _haversine_m(a: List[float], b: List[float]) -> float:
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def judge_p2p(
    response: Dict[str, Any],
    status_code: int,
    elapsed_s: float,
    scenario: str,
    *,
    min_distance: float = 0,
    max_distance: float = 100_000,
    max_response_s: float = 30,
    expect_degraded: Optional[bool] = None,
) -> QualityVerdict:
    """Judge a point-to-point response."""
    geom = response.get("geometry", {})
    coords = geom.get("coordinates", [])
    distance = response.get("distance_meters", 0)
    sb = response.get("surface_breakdown", {})
    unknown_pct = sb.get("unknown", 100)

    checks = {
        "no_server_error": status_code < 500,
        "has_geometry": len(coords) >= 2,
        "enough_points": len(coords) >= 5,
        "distance_in_band": min_distance <= distance <= max_distance,
        "surface_not_all_unknown": unknown_pct < 95,
        "response_time_ok": elapsed_s < max_response_s,
        "router_used_present": response.get("router_used") is not None,
    }
    if expect_degraded is not None:
        checks["degraded_as_expected"] = response.get("degraded") == expect_degraded

    notes: List[str] = []
    if unknown_pct > 50:
        notes.append(f"High unknown surface: {unknown_pct:.0f}%")

    return QualityVerdict(
        scenario=scenario,
        passed=all(checks.values()),
        checks=checks,
        notes=notes,
        elapsed_s=elapsed_s,
        status_code=status_code,
        raw=response,
    )


def judge_generate(
    candidates: List[Dict[str, Any]],
    status_code: int,
    elapsed_s: float,
    scenario: str,
    *,
    min_distance: float = 0,
    max_distance: float = 200_000,
    max_response_s: float = 60,
) -> QualityVerdict:
    """Judge a /generate response (list of RouteCandidateResponse)."""
    checks = {
        "no_server_error": status_code < 500,
        "has_candidates": len(candidates) >= 1,
        "response_time_ok": elapsed_s < max_response_s,
    }
    notes: List[str] = []

    if candidates:
        c = candidates[0]
        route = c.get("route", {})
        geom = route.get("geometry", {})
        coords = geom.get("coordinates", []) if geom else []
        dist = route.get("distance_meters", 0)
        checks["has_geometry"] = len(coords) >= 2
        checks["distance_in_band"] = min_distance <= dist <= max_distance
        checks["router_used_present"] = c.get("router_used") is not None
    else:
        checks["has_geometry"] = False
        notes.append("No candidates returned")

    return QualityVerdict(
        scenario=scenario,
        passed=all(checks.values()),
        checks=checks,
        notes=notes,
        elapsed_s=elapsed_s,
        status_code=status_code,
        raw=candidates,
    )


def judge_chat(
    response: Dict[str, Any],
    status_code: int,
    elapsed_s: float,
    scenario: str,
    *,
    expect_route: bool = True,
    expect_clarification: bool = False,
    max_response_s: float = 180,
) -> QualityVerdict:
    """Judge a /chat/message response."""
    msg = response.get("message", {})
    content = msg.get("content", "")
    route_updated = response.get("route_updated", False)
    rd = response.get("route_data")
    needs_clar = response.get("needs_clarification", False)

    checks = {
        "no_server_error": status_code < 500,
        "has_message": len(content) > 10,
        "response_time_ok": elapsed_s < max_response_s,
        "not_empty_content": "error" not in content.lower()[:50] or status_code >= 400,
    }

    if expect_route:
        checks["route_updated"] = route_updated
        if rd:
            coords = rd.get("geometry", {}).get("coordinates", [])
            checks["has_route_geometry"] = len(coords) >= 2
            dist = rd.get("distance_meters", 0)
            checks["route_has_distance"] = dist > 100
        else:
            checks["has_route_geometry"] = False
            checks["route_has_distance"] = False

    if expect_clarification:
        checks["clarification_returned"] = needs_clar or "?" in content

    notes: List[str] = []
    pm = response.get("planning_meta", {})
    if pm.get("fallback_used"):
        notes.append(f"Fallback used: {pm.get('fallback_reason', 'unknown')}")

    return QualityVerdict(
        scenario=scenario,
        passed=all(checks.values()),
        checks=checks,
        notes=notes,
        elapsed_s=elapsed_s,
        status_code=status_code,
    )


# ---------- Rideability checks ----------

def judge_rideability(
    geometry: Dict[str, Any],
    distance_m: float,
    duration_s: float,
    surface_breakdown: Dict[str, float],
    sport_type: str,
    route_type: str,
    start_coord: List[float],
    scenario: str,
) -> QualityVerdict:
    """Deep quality checks on a route's geometry — would a human ride this?"""
    coords = geometry.get("coordinates", [])
    checks: Dict[str, bool] = {}
    notes: List[str] = []

    # Loop closure
    if route_type == "loop" and len(coords) >= 2:
        closure_m = _haversine_m(coords[0], coords[-1])
        checks["loop_closed"] = closure_m < 500
        if closure_m >= 500:
            notes.append(f"Loop not closed: {closure_m:.0f}m gap")
    else:
        checks["loop_closed"] = True

    # No teleportation
    max_gap = 0
    for i in range(1, len(coords)):
        gap = _haversine_m(coords[i - 1], coords[i])
        max_gap = max(max_gap, gap)
    checks["no_teleportation"] = max_gap < 2000
    if max_gap >= 2000:
        notes.append(f"Teleportation: {max_gap:.0f}m gap between points")

    # Reasonable speed
    if duration_s > 0 and distance_m > 0:
        speed_kmh = (distance_m / 1000) / (duration_s / 3600)
        checks["reasonable_speed"] = 3 < speed_kmh < 60
        if not checks["reasonable_speed"]:
            notes.append(f"Implied speed: {speed_kmh:.1f} km/h")
    else:
        checks["reasonable_speed"] = True

    # Not a straight line (at least 2 bearing changes > 10 degrees)
    if len(coords) >= 4:
        turn_count = 0
        for i in range(1, len(coords) - 1):
            b1 = math.atan2(coords[i][0] - coords[i-1][0], coords[i][1] - coords[i-1][1])
            b2 = math.atan2(coords[i+1][0] - coords[i][0], coords[i+1][1] - coords[i][1])
            angle = abs(math.degrees(b2 - b1)) % 360
            if angle > 180:
                angle = 360 - angle
            if angle > 10:
                turn_count += 1
        checks["not_straight_line"] = turn_count >= 2
        if turn_count < 2:
            notes.append(f"Only {turn_count} turns detected — may be a straight line")
    else:
        checks["not_straight_line"] = len(coords) >= 2

    # Surface plausibility
    paved = surface_breakdown.get("paved", 0)
    unknown = surface_breakdown.get("unknown", 0)
    if sport_type == "road":
        checks["surface_plausible"] = paved > 20 or unknown > 50
    elif sport_type in ("mtb", "emtb"):
        non_paved = 100 - paved
        checks["surface_plausible"] = non_paved > 20 or unknown > 50
    else:
        checks["surface_plausible"] = True

    # Region match — route stays within ~80km of start
    if start_coord and coords:
        max_drift = 0
        for c in coords:
            drift = _haversine_m(start_coord, c)
            max_drift = max(max_drift, drift)
        checks["region_match"] = max_drift < 80_000
        if max_drift >= 80_000:
            notes.append(f"Route drifts {max_drift/1000:.0f}km from start")
    else:
        checks["region_match"] = True

    return QualityVerdict(
        scenario=f"rideability:{scenario}",
        passed=all(checks.values()),
        checks=checks,
        notes=notes,
    )
