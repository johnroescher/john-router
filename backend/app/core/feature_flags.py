"""Feature flags for enabling/disabling features."""
from typing import Dict, Any
from app.core.config import settings

# Feature flags configuration
FEATURE_FLAGS: Dict[str, bool] = {
    "user_preferences": True,
    "location_knowledge": True,
    "vector_search": True,
    "external_apis": True,  # Trailforks, etc.
    "route_strategies": True,
    "route_evaluation": True,
    "route_improvement": True,
    "clarification_questions": True,
    "response_generation": True,
    "proactive_suggestions": True,
    "caching": True,
    "parallel_processing": True,
    "prefetching": True,
}


def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature is enabled.
    
    Args:
        feature_name: Name of the feature flag
        
    Returns:
        True if feature is enabled, False otherwise
    """
    # Check environment variable first (allows runtime override)
    env_key = f"FEATURE_{feature_name.upper()}"
    env_value = getattr(settings, env_key.lower(), None)
    if env_value is not None:
        return bool(env_value)
    
    # Fall back to default flags
    return FEATURE_FLAGS.get(feature_name, False)


def get_all_feature_flags() -> Dict[str, bool]:
    """Get all feature flags and their current state.
    
    Returns:
        Dictionary of feature name to enabled status
    """
    return {
        name: is_feature_enabled(name)
        for name in FEATURE_FLAGS.keys()
    }
