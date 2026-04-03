"""Response generator service for natural language responses."""
from typing import Optional, List, Dict, Any
import json

import structlog

from app.schemas.planning import CandidateRoute, PlanningLoopResult, IntentObject
from app.schemas.evaluation import RouteEvaluation
from app.schemas.knowledge import KnowledgeChunk
from app.services.conversation_agent import get_conversation_agent

logger = structlog.get_logger()


class ResponseGenerator:
    """Service for generating conversational, friendly responses."""

    def __init__(self):
        from app.services.llm_client import clamp_max_tokens, extract_llm_text, get_llm_client, get_llm_model
        self.client = get_llm_client()
        self.model = get_llm_model()

    async def generate_route_response(
        self,
        route: CandidateRoute,
        intent: IntentObject,
        evaluation: Optional[RouteEvaluation] = None,
        knowledge_chunks: Optional[List[KnowledgeChunk]] = None,
        original_request: Optional[str] = None,
    ) -> str:
        """Generate a friendly, conversational response for a route.
        
        Args:
            route: Route candidate
            intent: User intent
            evaluation: Optional route evaluation
            knowledge_chunks: Optional relevant knowledge
            original_request: Original user request
            
        Returns:
            Friendly response text
        """
        if not self.client:
            return self._generate_fallback_response(route, intent)

        try:
            distance_km = route.computed.distance_km if route.computed else 0
            elevation_gain_m = route.computed.elevation_gain_m if route.computed else 0
            surface_breakdown = (
                route.computed.surface_mix.model_dump()
                if route.computed and route.computed.surface_mix
                else {}
            )
            route_stats = {
                "distance_km": distance_km,
                "elevation_gain_m": elevation_gain_m,
                "surface_breakdown": surface_breakdown,
            }

            knowledge_text = ""
            if knowledge_chunks:
                highlights = []
                for chunk in knowledge_chunks[:2]:
                    if "trail" in chunk.content.lower() or "route" in chunk.content.lower():
                        highlights.append(chunk.content[:100])
                if highlights:
                    knowledge_text = f"\nLocal highlights: {', '.join(highlights)}"

            evaluation_text = ""
            if evaluation:
                if evaluation.strengths:
                    evaluation_text = f"\nRoute strengths: {', '.join(evaluation.strengths[:3])}"
                if evaluation.summary:
                    evaluation_text += f"\n{evaluation.summary}"

            prompt = f"""You are a friendly, knowledgeable local cycling guide. Present this route to the user in a conversational, helpful way.

User Request: "{original_request or (intent.source.raw_text if intent.source else 'N/A')}"

Route Details:
- Name/Label: {route.label}
- Distance: {route_stats['distance_km']:.1f} km
- Elevation Gain: {route_stats['elevation_gain_m']:.0f} m
- Sport Type: {route.routing_profile}
- Surface: {json.dumps(route_stats.get('surface_breakdown', {}), indent=2)}{knowledge_text}{evaluation_text}

Write a friendly, first-person response (use "I") that:
1. Acknowledges the user's request
2. Highlights key features of the route
3. Mentions any local knowledge or interesting features
4. Explains why this route fits their request
5. Invites feedback or offers to adjust

Keep it concise (2-3 sentences) and conversational. Don't be overly technical.
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=clamp_max_tokens(500),
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            text = extract_llm_text(response.choices[0]) if response.choices else ""
            
            # Add proactive suggestions if available
            if evaluation:
                conversation_agent = get_conversation_agent()
                suggestions = conversation_agent.get_proactive_suggestions(route, evaluation)
                explanatory_notes = conversation_agent.get_explanatory_notes(route, evaluation)
                
                if explanatory_notes:
                    text += f"\n\n{explanatory_notes}"
                
                if suggestions:
                    text += "\n\n" + " ".join(suggestions)
            
            return text.strip()
        except Exception as e:
            logger.warning(f"Response generation failed: {e}", exc_info=True)
            return self._generate_fallback_response(route, intent)

    async def generate_multi_route_response(
        self,
        routes: List[CandidateRoute],
        intent: IntentObject,
        evaluations: Optional[List[RouteEvaluation]] = None,
        original_request: Optional[str] = None,
    ) -> str:
        """Generate response for multiple route options."""
        if not self.client:
            return self._generate_fallback_multi_response(routes, intent)

        try:
            routes_summary = []
            for idx, route in enumerate(routes):
                route_data = {
                    "label": route.label,
                    "distance_km": route.computed.distance_km if route.computed else 0,
                    "elevation_gain_m": route.computed.elevation_gain_m if route.computed else 0,
                    "strategy": route.generation_strategy,
                }
                if evaluations and idx < len(evaluations):
                    eval_data = evaluations[idx]
                    route_data["strengths"] = eval_data.strengths[:2] if eval_data.strengths else []
                routes_summary.append(route_data)

            prompt = f"""You are a friendly cycling guide. Present these {len(routes)} route options to the user.

User Request: "{original_request or (intent.source.raw_text if intent.source else 'N/A')}"

Routes:
{json.dumps(routes_summary, indent=2)}

Write a friendly response that:
1. Acknowledges their request
2. Briefly describes each route option (1-2 sentences each)
3. Highlights what makes each unique
4. Suggests which might be best for different preferences
5. Invites them to choose or ask for adjustments

Use first person ("I"). Keep it conversational and helpful.
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=clamp_max_tokens(800),
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            text = extract_llm_text(response.choices[0]) if response.choices else ""
            return text.strip()
        except Exception as e:
            logger.warning(f"Multi-route response generation failed: {e}", exc_info=True)
            return self._generate_fallback_multi_response(routes, intent)

    def _generate_fallback_response(self, route: CandidateRoute, intent: IntentObject) -> str:
        """Generate a simple fallback response."""
        distance = route.computed.distance_km if route.computed else 0
        elevation = route.computed.elevation_gain_m if route.computed else 0
        return f"I've created route {route.label} for you: {distance:.1f} km with {elevation:.0f} m of elevation gain. Let me know if you'd like any adjustments!"

    def _generate_fallback_multi_response(self, routes: List[CandidateRoute], intent: IntentObject) -> str:
        """Generate a simple fallback response for multiple routes."""
        labels = ", ".join([r.label for r in routes])
        return f"I've created {len(routes)} route options for you ({labels}). Each offers a different experience. Let me know which one you prefer or if you'd like me to adjust anything!"


# Singleton instance
_response_generator: Optional[ResponseGenerator] = None


def get_response_generator() -> ResponseGenerator:
    """Get or create ResponseGenerator singleton."""
    global _response_generator
    if _response_generator is None:
        _response_generator = ResponseGenerator()
    return _response_generator
