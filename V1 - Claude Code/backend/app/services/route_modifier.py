"""Route modifier service for chat-based route modifications."""
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4
import structlog

from app.schemas.planning import CandidateRoute, IntentObject
from app.schemas.common import Coordinate
from app.schemas.evaluation import RouteEvaluation, Weakness
from app.services.route_evaluator import get_route_evaluator
from app.services.route_improver import get_route_improver
from app.services.planning_tools import route_generate, route_analyze, route_validate, geocode_place

logger = structlog.get_logger()


class RouteModifier:
    """Service for modifying existing routes based on chat requests."""

    def __init__(self):
        from app.services.llm_client import get_llm_client, get_llm_model
        self.client = get_llm_client()
        self.model = get_llm_model()

    async def modify_route(
        self,
        route: CandidateRoute,
        modification_request: str,
        original_intent: IntentObject,
        user_preferences: Optional[Any] = None,
    ) -> tuple[Optional[CandidateRoute], Optional[RouteEvaluation], Optional[float], Optional[str]]:
        """Modify a route based on chat request.
        
        Args:
            route: Route to modify
            modification_request: User's modification request (e.g., "make it longer", "avoid hills")
            original_intent: Original user intent
            user_preferences: Optional user preferences
            
        Returns:
            Tuple of (modified_route, evaluation, similarity_score, failure_reason)
        """
        # Parse modification intent (LLM-assisted when available)
        mod_intent = await self._parse_modification_intent(modification_request, original_intent)
        
        # Apply modifications
        modified_route, failure_reason = await self._apply_modifications(
            route,
            mod_intent,
            modification_request,
        )
        if not modified_route:
            return None, None, None, failure_reason or "Route modification failed."
        
        similarity_score = self._route_similarity_score(route.geometry, modified_route.geometry)

        # Evaluate the modified route
        route_evaluator = get_route_evaluator()
        evaluation = await route_evaluator.evaluate_route_against_intent(
            route=modified_route,
            intent=mod_intent,
            original_request=modification_request,
            user_preferences=user_preferences,
        )

        if similarity_score is not None and mod_intent.change_intent.strategy == "modify_existing":
            if similarity_score >= 0.7:
                evaluation.intent_match_score = min(1.0, evaluation.intent_match_score + 0.08)
                evaluation.strengths.append("Route stays close to your original path.")
            elif similarity_score < 0.4:
                evaluation.intent_match_score = max(0.0, evaluation.intent_match_score - 0.12)
                evaluation.weaknesses.append(Weakness(
                    type="low_similarity",
                    description="Changes diverge significantly from the original route.",
                    severity=0.7,
                    suggestion="Allow a fresh route if you want larger changes.",
                ))
        
        # Improve if needed
        if evaluation.intent_match_score < 0.8 or evaluation.has_significant_issues():
            route_improver = get_route_improver()
            modified_route, evaluation = await route_improver.improve_and_reevaluate(
                route=modified_route,
                evaluation=evaluation,
                user_intent=mod_intent,
            )
        
        if modified_route:
            similarity_score = self._route_similarity_score(route.geometry, modified_route.geometry)
        if similarity_score is not None and mod_intent.change_intent.strategy == "modify_existing":
            if similarity_score < 0.5:
                return None, None, similarity_score, (
                    "clarification_required: Do you want to keep this route close to your original path, "
                    "or should I generate a fresh route that matches the new request?"
                )

        return modified_route, evaluation, similarity_score, None

    async def _parse_modification_intent(
        self,
        modification_request: str,
        original_intent: IntentObject,
    ) -> IntentObject:
        """Parse modification request into updated intent."""
        import re
        
        # Create updated intent based on original
        updated_intent = original_intent.model_copy(deep=True)
        request_lower = modification_request.lower()

        # LLM-assisted parsing (best-effort)
        if self.client:
            llm_payload = await self._llm_parse_modification(modification_request)
            if isinstance(llm_payload, dict):
                updated_intent = self._apply_llm_modification(updated_intent, llm_payload)
        
        # Distance modifications
        if any(word in request_lower for word in ["longer", "more distance", "add distance", "extend"]):
            if updated_intent.hard_constraints.distance_km:
                current_max = updated_intent.hard_constraints.distance_km.max or 0
                current_min = updated_intent.hard_constraints.distance_km.min or 0
                # Increase by 20% or extract specific amount
                match = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|kilometer|mile|mi)", modification_request, re.IGNORECASE)
                if match:
                    add_km = float(match.group(1))
                    if "mile" in match.group(0).lower():
                        add_km *= 1.60934
                    updated_intent.hard_constraints.distance_km.max = (current_max or current_min) + add_km
                    updated_intent.hard_constraints.distance_km.min = (current_min or current_max) + add_km
                else:
                    updated_intent.hard_constraints.distance_km.max = (current_max or current_min) * 1.2
                    updated_intent.hard_constraints.distance_km.min = (current_min or current_max) * 1.2
        
        if any(word in request_lower for word in ["shorter", "less distance", "reduce distance"]):
            if updated_intent.hard_constraints.distance_km:
                current_max = updated_intent.hard_constraints.distance_km.max or 0
                current_min = updated_intent.hard_constraints.distance_km.min or 0
                match = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|kilometer|mile|mi)", modification_request, re.IGNORECASE)
                if match:
                    subtract_km = float(match.group(1))
                    if "mile" in match.group(0).lower():
                        subtract_km *= 1.60934
                    updated_intent.hard_constraints.distance_km.max = max(0, (current_max or current_min) - subtract_km)
                    updated_intent.hard_constraints.distance_km.min = max(0, (current_min or current_max) - subtract_km)
                else:
                    updated_intent.hard_constraints.distance_km.max = (current_max or current_min) * 0.8
                    updated_intent.hard_constraints.distance_km.min = (current_min or current_max) * 0.8
        
        # Elevation modifications
        if any(word in request_lower for word in ["flatter", "less elevation", "avoid hills", "no climbs"]):
            if updated_intent.hard_constraints.elevation_gain_m:
                current_max = updated_intent.hard_constraints.elevation_gain_m.max or 0
                updated_intent.hard_constraints.elevation_gain_m.max = current_max * 0.5  # Reduce by 50%
                updated_intent.hard_constraints.elevation_gain_m.min = 0
        
        if any(word in request_lower for word in ["hillier", "more elevation", "more climbing", "challenging"]):
            if updated_intent.hard_constraints.elevation_gain_m:
                current_max = updated_intent.hard_constraints.elevation_gain_m.max or 0
                current_min = updated_intent.hard_constraints.elevation_gain_m.min or 0
                updated_intent.hard_constraints.elevation_gain_m.max = (current_max or current_min) * 1.5
                updated_intent.hard_constraints.elevation_gain_m.min = (current_min or current_max) * 1.5
        
        # Surface modifications
        if any(word in request_lower for word in ["more singletrack", "more trail", "more dirt"]):
            if updated_intent.soft_preferences.surface_mix:
                updated_intent.soft_preferences.surface_mix.singletrack = 0.6
                updated_intent.soft_preferences.surface_mix.dirt = 0.3
        
        if any(word in request_lower for word in ["more pavement", "more road", "less dirt"]):
            if updated_intent.soft_preferences.surface_mix:
                updated_intent.soft_preferences.surface_mix.pavement = 0.7
                updated_intent.soft_preferences.surface_mix.dirt = 0.1
        
        # Avoidance modifications
        if "avoid" in request_lower or "no" in request_lower:
            # Extract what to avoid
            if "highway" in request_lower or "busy road" in request_lower:
                # Add to avoid list
                if not updated_intent.hard_constraints.must_avoid:
                    updated_intent.hard_constraints.must_avoid = []
                updated_intent.hard_constraints.must_avoid.append({"type": "highway", "description": "Avoid highways"})
                updated_intent.soft_preferences.traffic_stress_max = "low"
        
        return updated_intent

    async def _llm_parse_modification(self, modification_request: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        import json
        prompt = f"""Parse the user's modification request into structured intent updates.
Return ONLY valid JSON with these fields:
{{
  "target_distance_km": number|null,
  "distance_delta_km": number|null,
  "target_elevation_gain_m": number|null,
  "elevation_delta_m": number|null,
  "surface_preference": "pavement"|"gravel"|"dirt"|"singletrack"|"mixed"|null,
  "avoid_highways": boolean|null,
  "must_pass_through": [string]
}}

User request: "{modification_request}"
"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )
            text = response.choices[0].message.content if response.choices else ""
            payload = json.loads(self._extract_json(text))
            return payload if isinstance(payload, dict) else None
        except Exception as e:
            logger.debug(f"LLM modification parse failed: {e}")
            return None

    def _apply_llm_modification(self, intent: IntentObject, payload: Dict[str, Any]) -> IntentObject:
        from app.schemas.planning import LocationSpec
        updated = intent.model_copy(deep=True)

        target_distance_km = payload.get("target_distance_km")
        distance_delta_km = payload.get("distance_delta_km")
        if isinstance(target_distance_km, (int, float)):
            updated.hard_constraints.distance_km.min = float(target_distance_km) * 0.95
            updated.hard_constraints.distance_km.max = float(target_distance_km) * 1.05
        elif isinstance(distance_delta_km, (int, float)):
            current_min = updated.hard_constraints.distance_km.min or updated.hard_constraints.distance_km.max or 0
            current_max = updated.hard_constraints.distance_km.max or updated.hard_constraints.distance_km.min or 0
            updated.hard_constraints.distance_km.min = max(0, current_min + float(distance_delta_km))
            updated.hard_constraints.distance_km.max = max(0, current_max + float(distance_delta_km))

        target_elevation_gain_m = payload.get("target_elevation_gain_m")
        elevation_delta_m = payload.get("elevation_delta_m")
        if isinstance(target_elevation_gain_m, (int, float)):
            updated.hard_constraints.elevation_gain_m.min = max(0, float(target_elevation_gain_m) * 0.9)
            updated.hard_constraints.elevation_gain_m.max = max(0, float(target_elevation_gain_m) * 1.1)
        elif isinstance(elevation_delta_m, (int, float)):
            current_min = updated.hard_constraints.elevation_gain_m.min or updated.hard_constraints.elevation_gain_m.max or 0
            current_max = updated.hard_constraints.elevation_gain_m.max or updated.hard_constraints.elevation_gain_m.min or 0
            updated.hard_constraints.elevation_gain_m.min = max(0, current_min + float(elevation_delta_m))
            updated.hard_constraints.elevation_gain_m.max = max(0, current_max + float(elevation_delta_m))

        surface_pref = payload.get("surface_preference")
        if isinstance(surface_pref, str):
            surface_pref = surface_pref.lower()
            if surface_pref in {"pavement", "gravel", "dirt", "singletrack"}:
                updated.soft_preferences.surface_mix.pavement = 0.1
                updated.soft_preferences.surface_mix.gravel = 0.1
                updated.soft_preferences.surface_mix.dirt = 0.1
                updated.soft_preferences.surface_mix.singletrack = 0.1
                if surface_pref == "pavement":
                    updated.soft_preferences.surface_mix.pavement = 0.7
                elif surface_pref == "gravel":
                    updated.soft_preferences.surface_mix.gravel = 0.6
                elif surface_pref == "dirt":
                    updated.soft_preferences.surface_mix.dirt = 0.6
                elif surface_pref == "singletrack":
                    updated.soft_preferences.surface_mix.singletrack = 0.6

        if payload.get("avoid_highways") is True:
            updated.soft_preferences.traffic_stress_max = "low"
            updated.hard_constraints.must_avoid.append({"type": "highway", "description": "Avoid highways"})

        must_pass = payload.get("must_pass_through") or []
        if isinstance(must_pass, list):
            for item in must_pass:
                if isinstance(item, str) and item.strip():
                    updated.hard_constraints.must_pass_through.append(
                        LocationSpec(type="place", value=item.strip())
                    )

        return updated

    def _extract_json(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                cleaned = "\n".join(lines)
            else:
                cleaned = cleaned.strip("`")
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]
        return cleaned

    def _build_candidate_from_analysis(
        self,
        brief_id: str,
        label: str,
        routing_profile: str,
        generation_strategy: str,
        geometry: Dict[str, Any],
        waypoints: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        validation: Dict[str, Any],
        transition_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> CandidateRoute:
        surface_breakdown = analysis.get("surface_breakdown", {})
        computed = {
            "distance_km": analysis.get("distance_meters", 0) / 1000,
            "time_est_min": analysis.get("estimated_time_seconds", 0) / 60,
            "elevation_gain_m": analysis.get("elevation_gain_meters", 0),
            "grade_stats": {
                "up_max_pct": analysis.get("max_grade_percent", 0),
                "down_max_pct": analysis.get("max_grade_percent", 0),
                "spikes": [],
            },
            "surface_mix": {
                "pavement": surface_breakdown.get("pavement", 0),
                "gravel": surface_breakdown.get("gravel", 0),
                "dirt": surface_breakdown.get("dirt", 0),
                "singletrack": surface_breakdown.get("singletrack", 0),
                "unknown": surface_breakdown.get("unknown", 0),
            },
            "technical": {
                "mtb_scale_max": analysis.get("max_technical_rating"),
                "distribution": {
                    "0": analysis.get("mtb_difficulty_breakdown", {}).get("green", 0),
                    "1": analysis.get("mtb_difficulty_breakdown", {}).get("blue", 0),
                    "2": analysis.get("mtb_difficulty_breakdown", {}).get("black", 0),
                    "3plus": analysis.get("mtb_difficulty_breakdown", {}).get("double_black", 0),
                },
            },
            "traffic_stress": {
                "avg": 0.0,
                "max": 0.0,
                "hotspots": [],
            },
            "stop_density": {
                "intersections_per_km": None,
                "signals_est": None,
            },
            "data_confidence": analysis.get("confidence_score", 0.5),
        }

        validation_issues = []
        status = "pass"
        for issue in validation.get("errors", []):
            validation_issues.append({
                "severity": "error",
                "type": issue.get("type", "unknown"),
                "message": issue.get("message", ""),
                "location": issue.get("location"),
                "fix_hint": issue.get("fix_suggestion"),
            })
            status = "fail"
        for issue in validation.get("warnings", []):
            validation_issues.append({
                "severity": "warn",
                "type": issue.get("type", "unknown"),
                "message": issue.get("message", ""),
                "location": issue.get("location"),
                "fix_hint": issue.get("fix_suggestion"),
            })
            if status == "pass":
                status = "warn"

        return CandidateRoute(
            candidate_id=str(uuid4()),
            brief_id=brief_id,
            label=label,
            routing_profile=routing_profile,
            generation_strategy=generation_strategy,
            geometry=geometry,
            waypoints=[
                {
                    "type": "via",
                    "point": Coordinate(lat=wp["lat"], lng=wp["lng"]),
                    "lock": "soft",
                    "name": wp.get("name"),
                }
                for wp in waypoints
                if wp.get("lat") is not None and wp.get("lng") is not None
            ],
            computed=computed,
            validation={"status": status, "issues": validation_issues},
            transition_segments=transition_segments or [],
        )

    def _extract_anchor_points(self, geometry: Dict[str, Any], max_points: int = 5) -> List[Dict[str, float]]:
        coords = geometry.get("coordinates") or []
        if not coords:
            return []
        total = len(coords)
        if total <= max_points:
            return [{"lng": c[0], "lat": c[1]} for c in coords]
        indices = [0]
        steps = max_points - 1
        for i in range(1, steps):
            idx = int(round(i * (total - 1) / steps))
            indices.append(idx)
        indices.append(total - 1)
        unique_indices = []
        for idx in indices:
            if idx not in unique_indices:
                unique_indices.append(idx)
        return [{"lng": coords[idx][0], "lat": coords[idx][1]} for idx in unique_indices]

    async def _location_to_point(self, location: Any) -> Optional[Dict[str, float]]:
        if not location:
            return None
        if hasattr(location, "type") and getattr(location, "type") == "point":
            value = getattr(location, "value", None)
            if hasattr(value, "lat") and hasattr(value, "lng"):
                return {"lat": float(value.lat), "lng": float(value.lng)}
            if isinstance(value, dict) and value.get("lat") is not None and value.get("lng") is not None:
                return {"lat": float(value["lat"]), "lng": float(value["lng"])}
        if hasattr(location, "type") and getattr(location, "type") == "place":
            value = getattr(location, "value", None)
            if isinstance(value, str) and value.strip():
                geocode = await geocode_place(value.strip())
                if geocode.get("point"):
                    return {"lat": float(geocode["point"]["lat"]), "lng": float(geocode["point"]["lng"])}
        return None

    def _route_type_from_geometry(self, geometry: Dict[str, Any]) -> str:
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            return "loop"
        start = coords[0]
        end = coords[-1]
        if self._haversine_distance_m(start[1], start[0], end[1], end[0]) <= 80:
            return "loop"
        return "point_to_point"

    def _build_surface_preferences(self, mod_intent: IntentObject) -> Optional[Dict[str, float]]:
        surface_mix = mod_intent.soft_preferences.surface_mix
        if not surface_mix or surface_mix.pavement is None:
            return None
        pavement = float(surface_mix.pavement or 0)
        gravel = float(surface_mix.gravel or 0)
        dirt = float(surface_mix.dirt or 0)
        singletrack = float(surface_mix.singletrack or 0)
        gravel += dirt
        total = max(0.0001, pavement + gravel + singletrack)
        return {
            "pavement": pavement / total,
            "gravel": gravel / total,
            "singletrack": singletrack / total,
        }

    async def _apply_modifications(
        self,
        route: CandidateRoute,
        mod_intent: IntentObject,
        modification_request: str,
    ) -> tuple[Optional[CandidateRoute], Optional[str]]:
        """Apply modifications to route.
        
        Note: In a full implementation, this would regenerate the route geometry.
        For now, we regenerate a route using anchors from the existing geometry.
        """
        geometry = route.geometry or {}
        if not geometry or geometry.get("type") != "LineString":
            return None, "Current route geometry is missing or invalid."

        anchors = self._extract_anchor_points(geometry, max_points=7)
        if not anchors:
            return None, "Unable to extract anchor points from the current route."

        must_pass = []
        for loc in mod_intent.hard_constraints.must_pass_through:
            point = await self._location_to_point(loc)
            if point:
                must_pass.append(point)

        waypoints = anchors[:1] + must_pass + anchors[1:]
        if len(waypoints) > 7:
            waypoints = [waypoints[0]] + waypoints[1:6] + [waypoints[-1]]

        route_type = mod_intent.hard_constraints.route_type
        if route_type == "any":
            route_type = self._route_type_from_geometry(geometry)

        target_distance_km = None
        if mod_intent.hard_constraints.distance_km:
            target_distance_km = mod_intent.hard_constraints.distance_km.max or mod_intent.hard_constraints.distance_km.min
        base_distance_km = route.computed.distance_km if route.computed else None
        if not target_distance_km and base_distance_km:
            target_distance_km = base_distance_km

        delta_km = self._parse_distance_delta_km(modification_request)
        if delta_km and base_distance_km:
            target_distance_km = base_distance_km + delta_km

        target_elevation = None
        if mod_intent.hard_constraints.elevation_gain_m:
            target_elevation = mod_intent.hard_constraints.elevation_gain_m.max or mod_intent.hard_constraints.elevation_gain_m.min

        surface_preferences = self._build_surface_preferences(mod_intent)

        min_distance_km = mod_intent.hard_constraints.distance_km.min
        max_distance_km = mod_intent.hard_constraints.distance_km.max
        if target_distance_km and delta_km:
            min_distance_km = min_distance_km or target_distance_km * 0.95
            max_distance_km = max_distance_km or target_distance_km * 1.05

        options = {
            "route_type": route_type,
            "target_distance_km": target_distance_km,
            "min_distance_km": min_distance_km,
            "max_distance_km": max_distance_km,
            "target_elevation_gain_m": target_elevation,
            "avoid_highways": mod_intent.soft_preferences.traffic_stress_max == "low",
            "surface_preferences": surface_preferences,
            "quality_mode": True,
            "num_alternatives": 1,
        }

        route_result = await route_generate(
            profile=route.routing_profile or "gravel",
            waypoints=waypoints,
            options=options,
        )

        new_geometry = route_result.get("geometry")
        if not new_geometry:
            return None, route_result.get("meta", {}).get("error") or "Route generation failed."

        analysis = await route_analyze(new_geometry)
        validation = await route_validate(new_geometry, route.routing_profile or "gravel")

        modified = self._build_candidate_from_analysis(
            brief_id=route.brief_id,
            label=f"{route.label} (modified)",
            routing_profile=route.routing_profile,
            generation_strategy=f"{route.generation_strategy}_modified",
            geometry=new_geometry,
            waypoints=waypoints,
            analysis=analysis,
            validation=validation,
            transition_segments=route_result.get("transition_segments", []),
        )

        return modified, None

    def _haversine_distance_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        import math
        radius = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _route_similarity_score(self, original_geometry: Dict[str, Any], modified_geometry: Dict[str, Any]) -> Optional[float]:
        original = original_geometry.get("coordinates") if original_geometry else None
        modified = modified_geometry.get("coordinates") if modified_geometry else None
        if not original or not modified:
            return None

        original_sample = self._sample_coords(original, max_points=200)
        modified_sample = self._sample_coords(modified, max_points=200)

        if not original_sample or not modified_sample:
            return None

        threshold_m = 150.0
        match_count = 0
        for lon, lat in modified_sample:
            min_dist = None
            for o_lon, o_lat in original_sample:
                dist = self._haversine_distance_m(lat, lon, o_lat, o_lon)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
                if min_dist is not None and min_dist <= threshold_m:
                    break
            if min_dist is not None and min_dist <= threshold_m:
                match_count += 1

        return match_count / max(1, len(modified_sample))

    def _sample_coords(self, coords: List[List[float]], max_points: int = 200) -> List[Tuple[float, float]]:
        if not coords:
            return []
        if len(coords) <= max_points:
            return [(c[0], c[1]) for c in coords]
        step = max(1, int(len(coords) / max_points))
        sampled = [(coords[i][0], coords[i][1]) for i in range(0, len(coords), step)]
        if sampled[-1] != (coords[-1][0], coords[-1][1]):
            sampled.append((coords[-1][0], coords[-1][1]))
        return sampled

    def _parse_distance_delta_km(self, message: str) -> Optional[float]:
        import re
        if not message:
            return None
        match = re.search(
            r"(?:add|more|extend|increase)\s+(?:by\s+)?(\d+(?:\.\d+)?)(?:\s+more)?\s*(mile|miles|mi|km|kilometer|kilometre|kilometers|kilometres)",
            message,
            re.IGNORECASE,
        )
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit in {"km", "kilometer", "kilometre", "kilometers", "kilometres"}:
            return value
        return value * 1.60934


# Singleton instance
_route_modifier: Optional[RouteModifier] = None


def get_route_modifier() -> RouteModifier:
    """Get or create RouteModifier singleton."""
    global _route_modifier
    if _route_modifier is None:
        _route_modifier = RouteModifier()
    return _route_modifier
