"""Route validation service for ensuring route quality and safety."""
from typing import List, Dict, Any, Optional
import math

from app.schemas.route import (
    RouteValidation,
    ValidationIssue,
    RouteConstraints,
    MTBDifficulty,
)
from app.schemas.common import Coordinate
import structlog

logger = structlog.get_logger()


# Bicycle access values that indicate allowed access
BICYCLE_ALLOWED = ["yes", "designated", "permissive", "official"]
BICYCLE_DENIED = ["no", "private"]


class RouteValidationService:
    """Service for validating cycling routes."""

    async def validate_route(
        self,
        geometry: Dict[str, Any],
        segments: Optional[List[Dict[str, Any]]] = None,
        constraints: Optional[RouteConstraints] = None,
    ) -> RouteValidation:
        """Validate a route comprehensively.

        Args:
            geometry: GeoJSON LineString geometry
            segments: Segment metadata
            constraints: User constraints (for checking against)
        Returns:
            Validation results with errors, warnings, and info
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        info: List[ValidationIssue] = []

        coordinates = geometry.get("coordinates", [])

        # 1. Connectivity check
        connectivity_issues = self._check_connectivity(coordinates)
        errors.extend(connectivity_issues)

        # 2. Legality check
        if segments:
            legality_issues = self._check_legality(segments, constraints)
            errors.extend([i for i in legality_issues if i.severity == "error"])
            warnings.extend([i for i in legality_issues if i.severity == "warning"])

        # 3. Safety checks
        if segments:
            safety_issues = self._check_safety(segments, coordinates)
            warnings.extend([i for i in safety_issues if i.severity == "warning"])
            info.extend([i for i in safety_issues if i.severity == "info"])

        # 4. MTB difficulty checks
        if constraints and segments:
            difficulty_issues = self._check_mtb_difficulty(segments, constraints)
            warnings.extend([i for i in difficulty_issues if i.severity == "warning"])
            info.extend([i for i in difficulty_issues if i.severity == "info"])

        # 5. Doubling back check (routes that retrace themselves)
        doubling_back_issues = self._check_doubling_back(geometry)
        warnings.extend([i for i in doubling_back_issues if i.severity == "warning"])
        info.extend([i for i in doubling_back_issues if i.severity == "info"])

        # 6. Constraint satisfaction check
        if constraints:
            constraint_issues = self._check_constraints(
                geometry, segments, constraints
            )
            info.extend(constraint_issues)

        # 7. Constraint policy checks (avoidances/preferences)
        if constraints and segments:
            policy_issues = self._check_constraint_policies(segments, constraints)
            warnings.extend([i for i in policy_issues if i.severity == "warning"])
            info.extend([i for i in policy_issues if i.severity == "info"])

        # Determine status
        if errors:
            status = "errors"
        elif warnings:
            status = "warnings"
        else:
            status = "valid"

        # Calculate confidence
        confidence = self._calculate_validation_confidence(
            segments, errors, warnings
        )

        return RouteValidation(
            status=status,
            errors=errors,
            warnings=warnings,
            info=info,
            confidence_score=confidence,
        )

    def _check_connectivity(
        self,
        coordinates: List[List[float]],
    ) -> List[ValidationIssue]:
        """Check for gaps or discontinuities in the route."""
        issues = []

        if len(coordinates) < 2:
            issues.append(ValidationIssue(
                type="connectivity",
                severity="error",
                message="Route has fewer than 2 points",
            ))
            return issues

        # Check for large gaps between points
        MAX_GAP_METERS = 500  # Allow 500m gaps (could be tunnels, etc.)

        for i in range(1, len(coordinates)):
            dist = self._haversine_distance(
                coordinates[i - 1][1], coordinates[i - 1][0],
                coordinates[i][1], coordinates[i][0],
            )

            if dist > MAX_GAP_METERS:
                issues.append(ValidationIssue(
                    type="connectivity",
                    severity="error",
                    message=f"Large gap ({int(dist)}m) detected in route",
                    segment_idx=i - 1,
                    location=Coordinate(
                        lng=coordinates[i - 1][0],
                        lat=coordinates[i - 1][1],
                    ),
                    fix_suggestion="Check if this section requires a bridge, tunnel, or different routing",
                ))

        return issues

    def _check_legality(
        self,
        segments: List[Dict[str, Any]],
        constraints: Optional[RouteConstraints],
    ) -> List[ValidationIssue]:
        """Check bicycle access legality."""
        issues = []
        require_legal = constraints.require_bicycle_legal if constraints else True

        for i, segment in enumerate(segments):
            bicycle_access = segment.get("bicycle_access", "unknown")
            highway_type = segment.get("highway_type", "")

            # Check explicit denial
            if bicycle_access in BICYCLE_DENIED:
                severity = "error" if require_legal else "warning"
                issues.append(ValidationIssue(
                    type="legality",
                    severity=severity,
                    message=f"Bicycle access denied on segment (highway={highway_type})",
                    segment_idx=i,
                    fix_suggestion="Find an alternative route or verify local regulations",
                ))

            # Check unknown access on certain highway types
            elif bicycle_access == "unknown":
                # Some highway types are usually OK
                if highway_type not in ["cycleway", "path", "track", "residential", "tertiary"]:
                    issues.append(ValidationIssue(
                        type="legality",
                        severity="warning",
                        message=f"Unknown bicycle access on {highway_type}",
                        segment_idx=i,
                        fix_suggestion="Verify bicycle access is allowed",
                    ))

        return issues

    def _check_safety(
        self,
        segments: List[Dict[str, Any]],
        coordinates: List[List[float]],
    ) -> List[ValidationIssue]:
        """Check for safety concerns."""
        issues = []

        highway_distances = {}

        for i, segment in enumerate(segments):
            highway_type = segment.get("highway_type", "")
            distance = segment.get("distance_meters", 0)
            max_grade = abs(segment.get("max_grade", 0) or 0)

            # Track distance on each highway type
            highway_distances[highway_type] = highway_distances.get(highway_type, 0) + distance

            # Check for dangerous grades
            if max_grade > 20:
                issues.append(ValidationIssue(
                    type="safety",
                    severity="warning",
                    message=f"Very steep grade ({max_grade:.1f}%) - use caution",
                    segment_idx=i,
                    fix_suggestion="Consider walking this section or finding alternative",
                ))

            # Check for high-speed road segments
            if highway_type in ["primary", "secondary", "trunk"]:
                issues.append(ValidationIssue(
                    type="safety",
                    severity="warning",
                    message=f"Route uses high-traffic road ({highway_type})",
                    segment_idx=i,
                    fix_suggestion="Look for parallel bike path or quieter route",
                ))

        # Check total distance on highways
        highway_total = highway_distances.get("primary", 0) + highway_distances.get("secondary", 0)
        if highway_total > 1000:
            issues.append(ValidationIssue(
                type="safety",
                severity="warning",
                message=f"Extended riding ({int(highway_total)}m) on busy roads",
                fix_suggestion="Consider alternative routing to reduce road exposure",
            ))

        return issues

    def _check_mtb_difficulty(
        self,
        segments: List[Dict[str, Any]],
        constraints: RouteConstraints,
    ) -> List[ValidationIssue]:
        """Check MTB difficulty against user constraints."""
        issues = []

        # Map user difficulty to max allowed mtb_scale
        difficulty_thresholds = {
            MTBDifficulty.EASY: 1,
            MTBDifficulty.MODERATE: 2,
            MTBDifficulty.HARD: 3,
            MTBDifficulty.VERY_HARD: 5,
        }

        max_allowed = difficulty_thresholds.get(constraints.mtb_difficulty_target, 5)

        for i, segment in enumerate(segments):
            mtb_scale = segment.get("mtb_scale")
            if mtb_scale is not None and mtb_scale > max_allowed:
                issues.append(ValidationIssue(
                    type="difficulty",
                    severity="warning",
                    message=f"Segment exceeds difficulty preference (mtb_scale {mtb_scale} > {max_allowed})",
                    segment_idx=i,
                    fix_suggestion="Find easier alternative or adjust difficulty preference",
                ))

            # Check downhill grade
            min_grade = segment.get("min_grade", 0) or 0  # Negative for downhill
            if abs(min_grade) > constraints.max_downhill_grade_percent:
                issues.append(ValidationIssue(
                    type="difficulty",
                    severity="info",
                    message=f"Steep descent ({abs(min_grade):.1f}%) exceeds preference ({constraints.max_downhill_grade_percent}%)",
                    segment_idx=i,
                ))

            # Check uphill grade
            max_grade = segment.get("max_grade", 0) or 0
            if max_grade > constraints.max_uphill_grade_percent:
                issues.append(ValidationIssue(
                    type="difficulty",
                    severity="info",
                    message=f"Steep climb ({max_grade:.1f}%) exceeds preference ({constraints.max_uphill_grade_percent}%)",
                    segment_idx=i,
                ))

        return issues

    def validate_surface_constraints(
        self,
        surface_breakdown: Dict[str, float],
        surface_constraints: Dict[str, Any],
    ) -> tuple[bool, List[str]]:
        """Validate if surface breakdown meets user constraints.

        Args:
            surface_breakdown: Dict with percentages (pavement, gravel, dirt, singletrack, unknown)
            surface_constraints: Dict with avoid_surfaces, prefer_surfaces, require_surfaces lists

        Returns:
            (is_valid, reasons) tuple
        """
        issues = []

        # Map frontend surface names to backend names
        surface_map = {
            "pavement": "paved",
            "paved": "paved",
            "gravel": "gravel",
            "dirt": "unpaved",  # Backend uses 'unpaved' for dirt
            "singletrack": "ground",  # Backend uses 'ground' for singletrack
        }

        # Check AVOID constraints (max 10%)
        for surface in surface_constraints.get("avoid_surfaces", []):
            backend_surface = surface_map.get(surface, surface)
            actual_pct = surface_breakdown.get(backend_surface, 0)

            if actual_pct > 10:
                issues.append(
                    f"Route has {actual_pct:.0f}% {surface} but should avoid it (max 10%)"
                )

        # Check PREFER constraints (should be 60%+)
        for surface in surface_constraints.get("prefer_surfaces", []):
            backend_surface = surface_map.get(surface, surface)
            actual_pct = surface_breakdown.get(backend_surface, 0)

            if actual_pct < 60:
                issues.append(
                    f"Route has only {actual_pct:.0f}% {surface} but should be mostly {surface} (60%+ preferred)"
                )

        # Check REQUIRE constraints (must be 80%+)
        for surface in surface_constraints.get("require_surfaces", []):
            backend_surface = surface_map.get(surface, surface)
            actual_pct = surface_breakdown.get(backend_surface, 0)

            if actual_pct < 80:
                issues.append(
                    f"Route has only {actual_pct:.0f}% {surface} but must be {surface} only (80%+ required)"
                )

        is_valid = len(issues) == 0
        return is_valid, issues

    def _check_constraints(
        self,
        geometry: Dict[str, Any],
        segments: Optional[List[Dict[str, Any]]],
        constraints: RouteConstraints,
    ) -> List[ValidationIssue]:
        """Check if route satisfies user constraints."""
        issues = []

        coordinates = geometry.get("coordinates", [])

        # Calculate actual distance
        total_distance = 0
        for i in range(1, len(coordinates)):
            total_distance += self._haversine_distance(
                coordinates[i - 1][1], coordinates[i - 1][0],
                coordinates[i][1], coordinates[i][0],
            )

        # Check distance constraint
        if constraints.target_distance_meters:
            diff_percent = abs(total_distance - constraints.target_distance_meters) / constraints.target_distance_meters * 100

            if diff_percent > 20:
                issues.append(ValidationIssue(
                    type="constraint",
                    severity="info",
                    message=f"Route distance ({total_distance/1000:.1f}km) differs from target by {diff_percent:.0f}%",
                ))

        if constraints.min_distance_meters and total_distance < constraints.min_distance_meters:
            issues.append(ValidationIssue(
                type="constraint",
                severity="info",
                message=f"Route shorter than minimum ({total_distance/1000:.1f}km < {constraints.min_distance_meters/1000:.1f}km)",
            ))

        if constraints.max_distance_meters and total_distance > constraints.max_distance_meters:
            issues.append(ValidationIssue(
                type="constraint",
                severity="info",
                message=f"Route longer than maximum ({total_distance/1000:.1f}km > {constraints.max_distance_meters/1000:.1f}km)",
            ))

        return issues

    def _check_constraint_policies(
        self,
        segments: List[Dict[str, Any]],
        constraints: RouteConstraints,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        total_distance = sum(seg.get("distance_meters", 0) for seg in segments) or 1

        def share(distance: float) -> float:
            return (distance / total_distance) * 100

        if constraints.avoid_highways:
            highway_dist = sum(
                seg.get("distance_meters", 0)
                for seg in segments
                if seg.get("highway_type") in ["motorway", "trunk", "primary", "secondary"]
            )
            if highway_dist > 0:
                issues.append(ValidationIssue(
                    type="avoid_highways",
                    severity="warning",
                    message=f"Route includes {share(highway_dist):.1f}% high-speed roads",
                ))

        if constraints.avoid_unpaved_when_road and constraints.sport_type.value == "road":
            unpaved_dist = sum(
                seg.get("distance_meters", 0)
                for seg in segments
                if seg.get("surface") in ["unpaved", "gravel", "dirt", "ground", "sand", "mud"]
            )
            if unpaved_dist > 0:
                issues.append(ValidationIssue(
                    type="avoid_unpaved",
                    severity="warning",
                    message=f"Route includes {share(unpaved_dist):.1f}% unpaved surface",
                ))

        if constraints.prefer_bike_lanes:
            bike_lane_dist = sum(
                seg.get("distance_meters", 0)
                for seg in segments
                if seg.get("cycleway")
            )
            if bike_lane_dist < total_distance * 0.2:
                issues.append(ValidationIssue(
                    type="bike_lane_preference",
                    severity="info",
                    message="Limited bike lane coverage on this route",
                ))

        if constraints.prefer_designated_mtb_trails:
            designated_dist = sum(
                seg.get("distance_meters", 0)
                for seg in segments
                if seg.get("designated_mtb")
            )
            if designated_dist < total_distance * 0.2:
                issues.append(ValidationIssue(
                    type="designated_trails_preference",
                    severity="info",
                    message="Limited designated MTB trail coverage on this route",
                ))

        hazard_avoidances = constraints.hazard_avoidances.model_dump() if hasattr(constraints.hazard_avoidances, "model_dump") else {}
        for hazard, enabled in hazard_avoidances.items():
            if not enabled:
                continue
            hazard_dist = sum(
                seg.get("distance_meters", 0)
                for seg in segments
                if (seg.get("hazards", {}) or {}).get(hazard)
            )
            if hazard_dist > 0:
                issues.append(ValidationIssue(
                    type=f"hazard_{hazard}",
                    severity="warning",
                    message=f"Route includes {share(hazard_dist):.1f}% segments flagged for {hazard}",
                ))

        return issues

    def _calculate_validation_confidence(
        self,
        segments: Optional[List[Dict[str, Any]]],
        errors: List[ValidationIssue],
        warnings: List[ValidationIssue],
    ) -> float:
        """Calculate confidence in validation results."""
        confidence = 80  # Base confidence

        # Reduce for missing data
        if not segments:
            confidence -= 30

        # Reduce for unknown access
        if segments:
            unknown_count = sum(
                1 for s in segments if s.get("bicycle_access") == "unknown"
            )
            confidence -= min(20, unknown_count * 2)

        return max(0, min(100, confidence))

    def _check_doubling_back(
        self,
        geometry: Dict[str, Any],
    ) -> List[ValidationIssue]:
        """Check if route doubles back on itself (retraces the same path)."""
        issues = []
        coordinates = geometry.get("coordinates", [])
        
        if len(coordinates) < 4:
            return issues

        # Convert coordinates to list of (lng, lat) tuples
        points = [(coord[0], coord[1]) for coord in coordinates]
        total_distance = self._calculate_route_distance(points)
        
        if total_distance == 0:
            return issues

        # Check for segments that overlap and go in opposite directions
        retraced_distance = 0.0
        segment_length = 50  # Check every 50 meters of route
        num_segments = max(10, int(total_distance / segment_length))
        step = max(1, len(points) // num_segments)
        
        threshold_distance = 20.0  # Consider it retracing if within 20 meters
        
        for i in range(0, len(points) - step, step):
            if i + step >= len(points):
                continue
                
            seg_start = points[i]
            seg_end = points[i + step]
            seg_mid = points[min(i + step // 2, len(points) - 1)]
            
            # Check if this segment overlaps with any later segment going in opposite direction
            for j in range(i + step * 2, len(points) - step, step):
                if j + step >= len(points):
                    continue
                    
                check_start = points[j]
                check_end = points[j + step]
                check_mid = points[min(j + step // 2, len(points) - 1)]
                
                # Calculate distance between segment midpoints
                dist_to_seg = self._haversine_distance(seg_mid[1], seg_mid[0], check_mid[1], check_mid[0])
                
                if dist_to_seg < threshold_distance:
                    # Check if segments are going in opposite directions
                    seg_bearing = self._calculate_bearing(seg_start[1], seg_start[0], seg_end[1], seg_end[0])
                    check_bearing = self._calculate_bearing(check_start[1], check_start[0], check_end[1], check_end[0])
                    
                    # Calculate angle difference (accounting for wrap-around)
                    angle_diff = abs(seg_bearing - check_bearing)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff
                    
                    # If segments are roughly opposite (150-210 degrees difference), it's retracing
                    if angle_diff > 150:
                        seg_distance = self._haversine_distance(seg_start[1], seg_start[0], seg_end[1], seg_end[0])
                        retraced_distance += seg_distance

        retraced_percentage = (retraced_distance / total_distance * 100) if total_distance > 0 else 0.0
        
        # More lenient thresholds - only warn about significant retracing
        if retraced_percentage > 50:
            issues.append(ValidationIssue(
                type="doubling_back",
                severity="warning",
                message=f"Route retraces {retraced_percentage:.0f}% of its path ({retraced_distance:.0f}m). Consider a loop route instead.",
            ))
        elif retraced_percentage > 35:
            issues.append(ValidationIssue(
                type="doubling_back",
                severity="info",
                message=f"Route retraces {retraced_percentage:.0f}% of its path. A loop route might be more interesting.",
            ))

        return issues

    def _calculate_route_distance(self, points: List[tuple]) -> float:
        """Calculate total distance of route in meters."""
        if len(points) < 2:
            return 0.0
        total = 0.0
        for i in range(len(points) - 1):
            total += self._haversine_distance(
                points[i][1], points[i][0],
                points[i + 1][1], points[i + 1][0]
            )
        return total

    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing (direction) from point 1 to point 2 in degrees (0-360)."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)
        
        y = math.sin(delta_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
        
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two points."""
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2) ** 2 +
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c


# Singleton
_validation_service: Optional[RouteValidationService] = None


async def get_validation_service() -> RouteValidationService:
    """Get or create validation service instance."""
    global _validation_service
    if _validation_service is None:
        _validation_service = RouteValidationService()
    return _validation_service
