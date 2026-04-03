"""Conversation agent for proactive suggestions and guidance."""
from typing import Optional, List
import structlog

from app.schemas.planning import CandidateRoute
from app.schemas.evaluation import RouteEvaluation

logger = structlog.get_logger()


class ConversationAgent:
    """Service for generating proactive suggestions and guidance."""

    def __init__(self):
        pass

    def get_proactive_suggestions(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
    ) -> List[str]:
        """Generate proactive suggestions based on route evaluation.
        
        Args:
            route: Route candidate
            evaluation: Route evaluation results
            
        Returns:
            List of suggestion strings
        """
        suggestions = []

        # Check for weaknesses that might need addressing
        for weakness in evaluation.weaknesses:
            if weakness.type == "too_hilly" and weakness.severity > 0.6:
                suggestions.append("If you'd like a flatter route, I can adjust that.")
            elif weakness.type == "highway_segment" and weakness.severity > 0.6:
                suggestions.append("I can reroute to avoid busy roads if you prefer quieter paths.")
            elif weakness.type == "too_short" and weakness.severity > 0.6:
                suggestions.append("I can extend this route if you want more distance.")
            elif weakness.type == "poor_surface" and weakness.severity > 0.6:
                suggestions.append("I can find routes with better surface quality if that's important to you.")

        # Check creativity score
        if evaluation.creativity_score < 0.3:
            suggestions.append("I have a more adventurous alternative if you're interested.")

        # Check for improvement opportunities
        if evaluation.improvement_opportunities:
            for opp in evaluation.improvement_opportunities[:2]:
                if opp.type == "add_scenic_detour":
                    suggestions.append(f"I could add a scenic detour: {opp.description[:50]}...")
                elif opp.type == "include_poi":
                    suggestions.append(f"I could include an interesting stop: {opp.description[:50]}...")

        # If route is very good, suggest alternatives
        if evaluation.intent_match_score > 0.9 and evaluation.quality_score > 0.8:
            suggestions.append("This route looks great! I also have other options if you want to explore alternatives.")

        return suggestions[:3]  # Limit to 3 suggestions

    def get_explanatory_notes(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
    ) -> str:
        """Provide brief friendly explanation of why this route was chosen.
        
        Args:
            route: Route candidate
            evaluation: Route evaluation results
            
        Returns:
            Explanatory text
        """
        notes = []

        # Explain based on strengths
        for strength in evaluation.strengths[:3]:
            if "scenic" in strength.lower() or "view" in strength.lower():
                notes.append("It includes some scenic viewpoints.")
            elif "traffic" in strength.lower() or "quiet" in strength.lower():
                notes.append("I kept it on low-traffic roads for safety.")
            elif "surface" in strength.lower():
                notes.append("The surface quality matches your preferences.")
            elif "distance" in strength.lower():
                notes.append("The distance fits your target perfectly.")

        # Explain based on strategy
        if route.generation_strategy == "classic":
            notes.append("This follows a classic, well-known route in the area.")
        elif route.generation_strategy == "explorer":
            notes.append("This explores some less-traveled paths for adventure.")
        elif route.generation_strategy == "hidden_gem":
            notes.append("This is a hidden gem - a great route that's not as well-known.")

        if not notes:
            notes.append("This route balances your preferences well.")

        return " ".join(notes)

    def generate_follow_up_questions(
        self,
        route: CandidateRoute,
        evaluation: RouteEvaluation,
    ) -> List[str]:
        """Generate helpful follow-up questions to engage the user.
        
        Args:
            route: Route candidate
            evaluation: Route evaluation results
            
        Returns:
            List of follow-up question strings
        """
        questions = []

        # If route has some issues but is acceptable
        if 0.6 <= evaluation.intent_match_score < 0.8:
            questions.append("Would you like me to adjust anything about this route?")

        # If multiple candidates were generated
        questions.append("Would you like to see alternative options?")

        # Based on route characteristics
        if route.computed and route.computed.elevation_gain_m > 500:
            questions.append("Is the elevation gain okay, or would you prefer something flatter?")

        return questions[:2]  # Limit to 2 questions


# Singleton instance
_conversation_agent: Optional[ConversationAgent] = None


def get_conversation_agent() -> ConversationAgent:
    """Get or create ConversationAgent singleton."""
    global _conversation_agent
    if _conversation_agent is None:
        _conversation_agent = ConversationAgent()
    return _conversation_agent
