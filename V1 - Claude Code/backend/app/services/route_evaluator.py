"""Route evaluator service for evaluating routes against user intent."""
from typing import Optional, Dict, Any
from uuid import UUID
import json

import structlog

from app.schemas.evaluation import RouteEvaluation, IntentGap, Weakness, ImprovementOpportunity
from app.schemas.planning import IntentObject, CandidateRoute
from app.schemas.user_context import UserPreferences
from app.models.route_evaluation import RouteEvaluationLog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class RouteEvaluator:
    """Service for evaluating routes against user intent and quality criteria."""

    def __init__(self):
        from app.services.llm_client import clamp_max_tokens, extract_llm_text, get_llm_client, get_llm_model
        self.client = get_llm_client()
        self.model = get_llm_model()

    async def evaluate_route_against_intent(
        self,
        route: CandidateRoute,
        intent: IntentObject,
        original_request: str,
        user_preferences: Optional[UserPreferences] = None,
        knowledge_chunks: Optional[list] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        log_evaluation: bool = False,
    ) -> RouteEvaluation:
        """Evaluate a route against user intent.
        
        Args:
            route: CandidateRoute to evaluate
            intent: User's intent object
            original_request: Original user request text
            user_preferences: Optional user preferences
            knowledge_chunks: Optional relevant knowledge chunks
            
        Returns:
            RouteEvaluation with scores and issues
        """
        evaluation = RouteEvaluation(
            route_id=route.candidate_id,
            intent_match_score=0.6,
            quality_score=0.6,
            creativity_score=0.5,
        )

        # Basic checks (rule-based)
        self._evaluate_basic_checks(route, intent, evaluation)

        # Store initial scores
        initial_scores = {
            "intent_match_score": evaluation.intent_match_score,
            "quality_score": evaluation.quality_score,
            "creativity_score": evaluation.creativity_score,
        }

        # LLM-powered qualitative evaluation
        if self.client:
            await self._evaluate_with_llm(route, intent, original_request, user_preferences, knowledge_chunks, evaluation)
        else:
            logger.warning("LLM not available, using basic evaluation only")

        # Log evaluation if requested
        if log_evaluation and db:
            await self._log_evaluation(
                route=route,
                intent=intent,
                evaluation=evaluation,
                initial_scores=initial_scores,
                db=db,
                user_id=user_id,
            )

        return evaluation

    async def _log_evaluation(
        self,
        route: CandidateRoute,
        intent: IntentObject,
        evaluation: RouteEvaluation,
        initial_scores: Dict[str, float],
        db: AsyncSession,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Log evaluation results to database."""
        try:
            from uuid import UUID as UUIDType
            route_uuid = None
            if route.candidate_id:
                try:
                    route_uuid = UUIDType(route.candidate_id)
                except:
                    pass

            final_scores = {
                "intent_match_score": evaluation.intent_match_score,
                "quality_score": evaluation.quality_score,
                "creativity_score": evaluation.creativity_score,
            }

            issues_found = []
            issues_found.extend([gap.type for gap in evaluation.intent_gaps])
            issues_found.extend([w.type for w in evaluation.weaknesses])

            log_entry = RouteEvaluationLog(
                user_id=user_id,
                route_id=route_uuid,
                intent=intent.model_dump() if hasattr(intent, 'model_dump') else {},
                initial_scores=initial_scores,
                final_scores=final_scores,
                issues_found=issues_found,
                improvements_made=[],  # Will be filled by improver
            )
            db.add(log_entry)
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to log evaluation: {e}", exc_info=True)
            await db.rollback()

    def _evaluate_basic_checks(
        self,
        route: CandidateRoute,
        intent: IntentObject,
        evaluation: RouteEvaluation,
    ) -> None:
        """Perform basic rule-based checks."""
        # Distance check
        if route.computed and intent.hard_constraints.distance_km:
            route_distance_km = route.computed.distance_km
            target_min = intent.hard_constraints.distance_km.min
            target_max = intent.hard_constraints.distance_km.max

            if target_min and route_distance_km < target_min * 0.8:  # 20% tolerance
                gap = IntentGap(
                    type="distance",
                    description=f"Route is {target_min - route_distance_km:.1f} km shorter than minimum target",
                    severity=min(1.0, (target_min - route_distance_km) / target_min),
                    expected_value=target_min,
                    actual_value=route_distance_km,
                )
                evaluation.intent_gaps.append(gap)
                evaluation.intent_match_score = max(0.0, evaluation.intent_match_score - 0.3)

            if target_max and route_distance_km > target_max * 1.2:  # 20% tolerance
                gap = IntentGap(
                    type="distance",
                    description=f"Route is {route_distance_km - target_max:.1f} km longer than maximum target",
                    severity=min(1.0, (route_distance_km - target_max) / target_max),
                    expected_value=target_max,
                    actual_value=route_distance_km,
                )
                evaluation.intent_gaps.append(gap)
                evaluation.intent_match_score = max(0.0, evaluation.intent_match_score - 0.2)

        # Elevation check
        if route.computed and intent.hard_constraints.elevation_gain_m:
            route_elevation = route.computed.elevation_gain_m
            target_min = intent.hard_constraints.elevation_gain_m.min
            target_max = intent.hard_constraints.elevation_gain_m.max

            if target_min and route_elevation < target_min * 0.7:
                gap = IntentGap(
                    type="elevation",
                    description=f"Route has {target_min - route_elevation:.0f} m less elevation than target",
                    severity=min(1.0, (target_min - route_elevation) / max(target_min, 100)),
                    expected_value=target_min,
                    actual_value=route_elevation,
                )
                evaluation.intent_gaps.append(gap)

            if target_max and route_elevation > target_max * 1.3:
                gap = IntentGap(
                    type="elevation",
                    description=f"Route has {route_elevation - target_max:.0f} m more elevation than maximum",
                    severity=min(1.0, (route_elevation - target_max) / max(target_max, 100)),
                    expected_value=target_max,
                    actual_value=route_elevation,
                )
                evaluation.intent_gaps.append(gap)

        # Check for highway segments (if user wants to avoid)
        if route.computed:
            surface_breakdown = route.computed.surface_mix.model_dump() if route.computed.surface_mix else {}
            # This is a simplified check - in reality we'd analyze the route geometry
            # For now, we'll let LLM handle this

        # Initial intent match score (will be refined by LLM)
        if not evaluation.intent_gaps:
            evaluation.intent_match_score = 0.8  # Good baseline
        else:
            # Reduce score based on gaps
            gap_penalty = sum(gap.severity for gap in evaluation.intent_gaps) / len(evaluation.intent_gaps)
            evaluation.intent_match_score = max(0.0, 0.8 - gap_penalty * 0.5)

    async def _evaluate_with_llm(
        self,
        route: CandidateRoute,
        intent: IntentObject,
        original_request: str,
        user_preferences: Optional[UserPreferences],
        knowledge_chunks: Optional[list],
        evaluation: RouteEvaluation,
    ) -> None:
        """Use LLM for qualitative evaluation."""
        try:
            # Build context
            route_summary = {
                "distance_km": route.computed.distance_km if route.computed else None,
                "elevation_gain_m": route.computed.elevation_gain_m if route.computed else None,
                "surface_breakdown": route.computed.surface_mix.model_dump() if route.computed and route.computed.surface_mix else {},
            }

            preferences_text = ""
            if user_preferences:
                prefs = {
                    "typical_distance_km": user_preferences.typical_distance_km,
                    "preferred_surfaces": user_preferences.preferred_surfaces,
                    "avoided_areas": user_preferences.avoided_areas,
                }
                preferences_text = f"\nUser preferences: {json.dumps(prefs, indent=2)}"

            knowledge_text = ""
            if knowledge_chunks:
                knowledge_list = [{"content": chunk.content[:150], "source": chunk.source} for chunk in knowledge_chunks[:3]]
                knowledge_text = f"\nRelevant local knowledge: {json.dumps(knowledge_list, indent=2)}"

            prompt = f"""Evaluate this cycling route against the user's intent and provide structured feedback.

User Request: "{original_request}"

Intent:
{json.dumps(intent.model_dump(), indent=2)}

Route Summary:
{json.dumps(route_summary, indent=2)}{preferences_text}{knowledge_text}

Current Issues Found (rule-based):
{json.dumps([gap.model_dump() for gap in evaluation.intent_gaps], indent=2)}

Provide a comprehensive evaluation. Return ONLY valid JSON with this structure:
{{
  "intent_match_score": 0.0-1.0,
  "quality_score": 0.0-1.0,
  "creativity_score": 0.0-1.0,
  "intent_gaps": [
    {{"type": "...", "description": "...", "severity": 0.0-1.0, "expected_value": ..., "actual_value": ...}}
  ],
  "weaknesses": [
    {{"type": "...", "description": "...", "location": "...", "severity": 0.0-1.0, "suggestion": "..."}}
  ],
  "strengths": ["...", "..."],
  "improvement_opportunities": [
    {{"type": "...", "description": "...", "location": "...", "potential_improvement": "..."}}
  ],
  "recommendations": ["...", "..."],
  "summary": "..."
}}

Focus on:
- How well the route matches the user's stated intent
- Quality issues (highway segments if user wants quiet roads, surface quality, etc.)
- Creative opportunities (scenic detours, interesting features, etc.)
- Specific, actionable improvements
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=clamp_max_tokens(2000),
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            text = extract_llm_text(response.choices[0]) if response.choices else "{}"
            # Extract JSON from response
            cleaned = self._extract_json(text)
            llm_eval = json.loads(cleaned)

            # Update evaluation with LLM results (LLM scores take precedence)
            if "intent_match_score" in llm_eval:
                evaluation.intent_match_score = float(llm_eval["intent_match_score"])
            if "quality_score" in llm_eval:
                evaluation.quality_score = float(llm_eval["quality_score"])
            if "creativity_score" in llm_eval:
                evaluation.creativity_score = float(llm_eval["creativity_score"])

            # Add LLM-found gaps (merge with rule-based ones, prefer LLM for nuanced issues)
            if "intent_gaps" in llm_eval:
                for gap_data in llm_eval["intent_gaps"]:
                    gap_type = gap_data.get("type")
                    # Check if we already have this gap type
                    existing = [g for g in evaluation.intent_gaps if g.type == gap_type]
                    if existing:
                        # Update existing gap if LLM found more detail
                        existing[0].description = gap_data.get("description", existing[0].description)
                        existing[0].severity = max(existing[0].severity, float(gap_data.get("severity", 0)))
                    else:
                        evaluation.intent_gaps.append(IntentGap(**gap_data))

            if "weaknesses" in llm_eval:
                for weakness_data in llm_eval["weaknesses"]:
                    evaluation.weaknesses.append(Weakness(**weakness_data))

            if "strengths" in llm_eval:
                evaluation.strengths.extend(llm_eval["strengths"])

            if "improvement_opportunities" in llm_eval:
                for opp_data in llm_eval["improvement_opportunities"]:
                    evaluation.improvement_opportunities.append(ImprovementOpportunity(**opp_data))

            if "recommendations" in llm_eval:
                evaluation.recommendations.extend(llm_eval["recommendations"])

            if "summary" in llm_eval:
                evaluation.summary = llm_eval["summary"]

        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}", exc_info=True)
            # Keep rule-based evaluation results

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response."""
        cleaned = text.strip()
        # Remove markdown code blocks
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2 and lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            cleaned = "\n".join(lines)
        # Find JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]
        return cleaned


# Singleton instance
_route_evaluator: Optional[RouteEvaluator] = None


def get_route_evaluator() -> RouteEvaluator:
    """Get or create RouteEvaluator singleton."""
    global _route_evaluator
    if _route_evaluator is None:
        _route_evaluator = RouteEvaluator()
    return _route_evaluator
