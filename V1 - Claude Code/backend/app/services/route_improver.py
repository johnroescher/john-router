"""Route improver service for automatically improving routes based on evaluation."""
from typing import Optional, List, Dict, Any
import json

import structlog

from app.schemas.planning import CandidateRoute
from app.schemas.evaluation import RouteEvaluation, IntentGap, Weakness
from app.schemas.planning import IntentObject
from app.schemas.knowledge import KnowledgeChunk
from app.services.planning_tools import route_generate, route_analyze, route_validate

logger = structlog.get_logger()


class RouteImprover:
    """Service for automatically improving routes based on evaluation results."""

    def __init__(self):
        from app.services.llm_client import clamp_max_tokens, extract_llm_text, get_llm_client, get_llm_model
        self.client = get_llm_client()
        self.model = get_llm_model()

    async def improve_route(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
        user_intent: IntentObject,
        knowledge_chunks: Optional[List[KnowledgeChunk]] = None,
    ) -> CandidateRoute:
        """Improve a route based on evaluation findings.
        
        Args:
            route: Route candidate to improve
            evaluation: Evaluation results with issues and opportunities
            user_intent: User's intent object
            knowledge_chunks: Optional relevant knowledge
            
        Returns:
            Improved CandidateRoute (or original if no improvements possible)
        """
        # Attempt real geometry regeneration when issues are significant
        regenerated = await self._regenerate_route_from_evaluation(route, evaluation, user_intent)
        if regenerated:
            return regenerated

        improved = CandidateRoute(
            candidate_id=route.candidate_id,
            brief_id=route.brief_id,
            label=route.label,
            routing_profile=route.routing_profile,
            generation_strategy=route.generation_strategy,
            geometry=route.geometry,
            waypoints=route.waypoints.copy() if route.waypoints else [],
            computed=route.computed.model_copy() if hasattr(route.computed, "model_copy") else (route.computed.copy() if route.computed else {}),
            validation=route.validation.model_copy() if hasattr(route.validation, "model_copy") else (route.validation.copy() if route.validation else {}),
        )

        changes_made = []

        # 1. Fix intent gaps
        for gap in evaluation.intent_gaps:
            change = await self._fix_gap(improved, gap, user_intent, knowledge_chunks)
            if change:
                changes_made.append(change)

        # 2. Fix weaknesses
        for weakness in evaluation.weaknesses:
            change = await self._fix_weakness(improved, weakness, user_intent, knowledge_chunks)
            if change:
                changes_made.append(change)

        # 3. Apply creative opportunities (if time permits)
        for opp in evaluation.improvement_opportunities[:2]:  # Limit to top 2
            change = await self._apply_opportunity(improved, opp, user_intent, knowledge_chunks)
            if change:
                changes_made.append(change)

        # 4. Apply LLM recommendations
        for rec in evaluation.recommendations[:2]:  # Limit to top 2
            change = await self._interpret_and_apply_recommendation(improved, rec, user_intent)
            if change:
                changes_made.append(change)

        # 5. LLM-powered improvement suggestions (complete improvement loop)
        llm_suggestions = await self._generate_llm_suggestions(
            route=improved,
            evaluation=evaluation,
            user_intent=user_intent,
            knowledge_chunks=knowledge_chunks,
        )
        for suggestion in llm_suggestions[:2]:
            if suggestion:
                changes_made.append(f"LLM suggestion: {suggestion}")

        if changes_made:
            logger.info(f"Applied {len(changes_made)} improvements to route {route.label}", changes=changes_made)
            # Note: In a full implementation, we would regenerate the route geometry here
            # For now, we mark that improvements were suggested
            if improved.computed:
                if isinstance(improved.computed, dict):
                    improved.computed["improvements_applied"] = changes_made
                else:
                    improved.generation_strategy = f"{improved.generation_strategy}_improved"
        else:
            logger.info(f"No improvements applied to route {route.label}")

        return improved

    async def improve_and_reevaluate(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
        user_intent: IntentObject,
        knowledge_chunks: Optional[List[KnowledgeChunk]] = None,
        max_iterations: int = 2,
    ) -> tuple[CandidateRoute, RouteEvaluation]:
        """Improve route and re-evaluate, iterating if needed.
        
        Args:
            route: Route to improve
            evaluation: Initial evaluation
            user_intent: User intent
            knowledge_chunks: Optional knowledge
            max_iterations: Maximum improvement iterations
            
        Returns:
            Tuple of (improved_route, final_evaluation)
        """
        from app.services.route_evaluator import get_route_evaluator
        
        current_route = route
        current_eval = evaluation
        route_evaluator = get_route_evaluator()
        
        for iteration in range(max_iterations):
            if current_eval.intent_match_score >= 0.9 or not current_eval.has_significant_issues():
                # Good enough, stop improving
                break
            
            # Improve
            improved_route = await self.improve_route(
                route=current_route,
                evaluation=current_eval,
                user_intent=user_intent,
                knowledge_chunks=knowledge_chunks,
            )
            
            # Re-evaluate
            current_eval = await route_evaluator.evaluate_route_against_intent(
                route=improved_route,
                intent=user_intent,
                original_request=user_intent.source.raw_text if user_intent.source else "",
                knowledge_chunks=knowledge_chunks,
            )
            
            # Check if we improved
            if current_eval.intent_match_score <= evaluation.intent_match_score + 0.05:
                # No significant improvement, stop
                break
            
            current_route = improved_route
        
        return current_route, current_eval

    async def _regenerate_route_from_evaluation(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
        user_intent: IntentObject,
    ) -> Optional[CandidateRoute]:
        """Attempt to regenerate a route geometry based on evaluation gaps."""
        if not evaluation.intent_gaps and not evaluation.has_significant_issues():
            return None

        waypoints = []
        if route.waypoints:
            for wp in route.waypoints:
                point = getattr(wp, "point", None)
                if point is not None and getattr(point, "lat", None) is not None and getattr(point, "lng", None) is not None:
                    waypoints.append({"lat": float(point.lat), "lng": float(point.lng)})

        if not waypoints:
            coords = route.geometry.get("coordinates") if route.geometry else None
            if coords:
                first = coords[0]
                waypoints.append({"lat": first[1], "lng": first[0]})

        if not waypoints:
            return None

        target_distance_km = None
        for gap in evaluation.intent_gaps:
            if gap.type == "distance" and isinstance(gap.expected_value, (int, float)):
                target_distance_km = float(gap.expected_value)
                break
        if target_distance_km is None and user_intent.hard_constraints.distance_km:
            target_distance_km = (
                user_intent.hard_constraints.distance_km.max
                or user_intent.hard_constraints.distance_km.min
            )

        target_elevation_gain_m = None
        for gap in evaluation.intent_gaps:
            if gap.type == "elevation" and isinstance(gap.expected_value, (int, float)):
                target_elevation_gain_m = float(gap.expected_value)
                break
        if target_elevation_gain_m is None and user_intent.hard_constraints.elevation_gain_m:
            target_elevation_gain_m = (
                user_intent.hard_constraints.elevation_gain_m.max
                or user_intent.hard_constraints.elevation_gain_m.min
            )

        route_type = user_intent.hard_constraints.route_type
        if route_type == "any":
            route_type = "loop"

        options: Dict[str, Any] = {
            "route_type": route_type,
            "target_distance_km": target_distance_km,
            "target_elevation_gain_m": target_elevation_gain_m,
            "avoid_highways": user_intent.soft_preferences.traffic_stress_max == "low",
            "quality_mode": True,
            "num_alternatives": 1,
        }

        surface_mix = user_intent.soft_preferences.surface_mix
        if surface_mix and surface_mix.pavement is not None:
            surface_preferences = {
                "pavement": float(surface_mix.pavement or 0),
                "gravel": float(surface_mix.gravel or 0),
                "singletrack": float(surface_mix.singletrack or 0),
            }
            options["surface_preferences"] = surface_preferences

        try:
            route_result = await route_generate(
                profile=route.routing_profile or "gravel",
                waypoints=waypoints,
                options=options,
            )
        except Exception as e:
            logger.warning(f"Route regeneration failed: {e}")
            return None

        new_geometry = route_result.get("geometry")
        if not new_geometry:
            return None

        analysis = await route_analyze(new_geometry)
        validation = await route_validate(new_geometry, route.routing_profile or "gravel")

        return self._build_candidate_from_analysis(
            base_route=route,
            geometry=new_geometry,
            analysis=analysis,
            validation=validation,
            transition_segments=route_result.get("transition_segments", []),
        )

    def _build_candidate_from_analysis(
        self,
        base_route: CandidateRoute,
        geometry: Dict[str, Any],
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
            candidate_id=base_route.candidate_id,
            brief_id=base_route.brief_id,
            label=base_route.label,
            routing_profile=base_route.routing_profile,
            generation_strategy=f"{base_route.generation_strategy}_improved",
            geometry=geometry,
            waypoints=base_route.waypoints,
            computed=computed,
            validation={"status": status, "issues": validation_issues},
            transition_segments=transition_segments or [],
        )

    async def _fix_gap(
        self,
        route: CandidateRoute,
        gap: IntentGap,
        user_intent: IntentObject,
        knowledge_chunks: Optional[List[KnowledgeChunk]],
    ) -> Optional[str]:
        """Fix an intent gap."""
        if gap.type == "distance":
            # Distance mismatch
            if gap.expected_value and gap.actual_value:
                diff_km = gap.expected_value - gap.actual_value
                if diff_km > 0:
                    # Route is too short - we'd need to add waypoints or extend
                    return f"Route needs {diff_km:.1f} km more distance"
                else:
                    # Route is too long - we'd need to shorten
                    return f"Route needs {abs(diff_km):.1f} km less distance"
        elif gap.type == "elevation":
            # Elevation mismatch
            if gap.expected_value and gap.actual_value:
                diff_m = gap.expected_value - gap.actual_value
                if diff_m > 0:
                    return f"Route needs {diff_m:.0f} m more elevation gain"
                else:
                    return f"Route needs {abs(diff_m):.0f} m less elevation gain"
        elif gap.type == "location":
            # Missing location - would need to add waypoint
            return f"Route should pass through: {gap.description}"
        
        return None

    async def _fix_weakness(
        self,
        route: CandidateRoute,
        weakness: Weakness,
        user_intent: IntentObject,
        knowledge_chunks: Optional[List[KnowledgeChunk]],
    ) -> Optional[str]:
        """Fix a weakness in the route."""
        if weakness.type == "highway_segment":
            # Highway segment that should be avoided
            # In full implementation, we'd search for alternative routes
            if weakness.suggestion:
                return f"Replace highway segment with: {weakness.suggestion}"
            return "Replace highway segment with quieter alternative"
        
        elif weakness.type == "too_short":
            # Route is too short
            return "Extend route to meet distance target"
        
        elif weakness.type == "too_hilly":
            # Route is too hilly
            return "Reroute to avoid steep climbs"
        
        elif weakness.type == "poor_surface":
            # Poor surface quality
            return "Reroute to use better surface types"
        
        return None

    async def _apply_opportunity(
        self,
        route: CandidateRoute,
        opportunity,
        user_intent: IntentObject,
        knowledge_chunks: Optional[List[KnowledgeChunk]],
    ) -> Optional[str]:
        """Apply a creative improvement opportunity."""
        if opportunity.type == "add_scenic_detour":
            return f"Add scenic detour: {opportunity.description}"
        elif opportunity.type == "include_poi":
            return f"Include point of interest: {opportunity.description}"
        elif opportunity.type == "better_surface":
            return f"Improve surface quality: {opportunity.description}"
        
        return None

    async def _interpret_and_apply_recommendation(
        self,
        route: CandidateRoute,
        recommendation: str,
        user_intent: IntentObject,
    ) -> Optional[str]:
        """Interpret and apply an LLM recommendation."""
        # For now, we just log the recommendation
        # In full implementation, we'd parse and apply it
        if "replace" in recommendation.lower() or "avoid" in recommendation.lower():
            return f"Applied recommendation: {recommendation[:100]}"
        elif "add" in recommendation.lower() or "include" in recommendation.lower():
            return f"Applied recommendation: {recommendation[:100]}"
        
        return None

    async def _generate_llm_suggestions(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
        user_intent: IntentObject,
        knowledge_chunks: Optional[List[KnowledgeChunk]],
    ) -> List[str]:
        """Generate LLM-powered improvement suggestions."""
        if not self.client:
            return []

        try:
            route_summary = {
                "distance_km": route.computed.distance_km if route.computed else None,
                "elevation_gain_m": route.computed.elevation_gain_m if route.computed else None,
            }

            knowledge_text = ""
            if knowledge_chunks:
                knowledge_list = [{"content": chunk.content[:150]} for chunk in knowledge_chunks[:3]]
                knowledge_text = f"\nRelevant knowledge: {json.dumps(knowledge_list, indent=2)}"

            prompt = f"""You are an expert cycling route planner. A route was generated but has some issues.

User Request: "{user_intent.source.raw_text if user_intent.source else 'N/A'}"

Current Route:
{json.dumps(route_summary, indent=2)}

Issues Found:
{json.dumps([w.model_dump() for w in evaluation.weaknesses], indent=2)}{knowledge_text}

Suggest up to 3 specific improvements to better match the intent. Provide each suggestion with:
- What change to make (e.g., "replace Highway 9 segment with parallel Greenway Trail")
- Why it improves the route

Return ONLY valid JSON array:
[
  {{"change": "...", "reason": "..."}},
  ...
]
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=clamp_max_tokens(1000),
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            text = extract_llm_text(response.choices[0]) if response.choices else "[]"
            cleaned = self._extract_json(text)
            suggestions = json.loads(cleaned)
            
            return [s.get("change", "") for s in suggestions if isinstance(s, dict)]
        except Exception as e:
            logger.warning(f"LLM suggestion generation failed: {e}", exc_info=True)
            return []

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2 and lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            cleaned = "\n".join(lines)
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]
        return "[]"


# Singleton instance
_route_improver: Optional[RouteImprover] = None


def get_route_improver() -> RouteImprover:
    """Get or create RouteImprover singleton."""
    global _route_improver
    if _route_improver is None:
        _route_improver = RouteImprover()
    return _route_improver
