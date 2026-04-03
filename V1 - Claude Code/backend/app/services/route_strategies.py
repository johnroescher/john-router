"""Route generation strategies for diverse route types."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from uuid import uuid4

from app.schemas.planning import IntentObject, RideBrief, IngredientSet, CandidateRoute
from app.schemas.common import Coordinate
import structlog

logger = structlog.get_logger()


class RouteStrategy(ABC):
    """Base class for route generation strategies."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def generate_route_specs(
        self,
        intent: IntentObject,
        brief: RideBrief,
        ingredients: IngredientSet,
        start_location: Optional[Coordinate],
        db: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Generate route specification dictionaries.
        
        Returns:
            List of route spec dicts with keys: label, routing_profile, generation_strategy, waypoints
        """
        pass

    def _extract_start_location(self, intent: IntentObject) -> Optional[Coordinate]:
        """Extract start location from intent."""
        if intent.hard_constraints.start.type == "point" and isinstance(intent.hard_constraints.start.value, Coordinate):
            return intent.hard_constraints.start.value
        return None

    def _normalize_start_location(self, start_location: Optional[Any]) -> Optional[Dict[str, float]]:
        """Normalize start location to a lat/lng dict."""
        if isinstance(start_location, Coordinate):
            return {"lat": start_location.lat, "lng": start_location.lng}
        if isinstance(start_location, dict):
            lat = start_location.get("lat")
            lng = start_location.get("lng")
            if lat is not None and lng is not None:
                return {"lat": lat, "lng": lng}
        return None

    def _get_discipline(self, intent: IntentObject) -> str:
        """Get discipline from intent, with fallback."""
        discipline = intent.hard_constraints.discipline
        if discipline == "any":
            return "gravel"  # Default
        return discipline

    def _attach_quality_meta(
        self,
        spec: Dict[str, Any],
        confidence: float,
        expected_fit: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        spec["confidence"] = round(confidence, 2)
        spec["expected_fit"] = expected_fit or []
        return spec


class ExplorerStrategy(RouteStrategy):
    """Strategy for exploration-focused routes - discovers new areas, less-traveled paths."""

    def __init__(self):
        super().__init__(
            name="explorer",
            description="Exploration-focused routes that discover new areas and less-traveled paths"
        )

    async def generate_route_specs(
        self,
        intent: IntentObject,
        brief: RideBrief,
        ingredients: IngredientSet,
        start_location: Optional[Coordinate],
        db: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Generate exploration-focused route specs."""
        start_point = self._normalize_start_location(start_location)
        if not start_point:
            return []

        discipline = self._get_discipline(intent)
        specs = []

        # Use POIs and less common trails from ingredients
        # Create routes that explore different directions
        bearings = [0, 90, 180, 270]  # N, E, S, W
        
        # Use POIs if available
        if ingredients.pois:
            for idx, poi in enumerate(ingredients.pois[:3]):
                poi_point = poi.point
                specs.append(self._attach_quality_meta({
                    "label": chr(65 + idx),  # A, B, C
                    "routing_profile": discipline,
                    "generation_strategy": "explorer",
                    "waypoints": [
                        {"lat": start_point["lat"], "lng": start_point["lng"]},
                        {"lat": poi_point.lat, "lng": poi_point.lng},
                    ],
                    "description": f"Exploratory route to {poi.name or poi.type}",
                }, confidence=0.6, expected_fit=["scenic", "poi"]))
        else:
            # Generate exploration routes in different directions
            for idx, bearing in enumerate(bearings[:3]):
                # Calculate waypoint at distance in bearing direction
                import math
                distance_km = (
                    intent.hard_constraints.distance_km.max
                    or intent.hard_constraints.distance_km.min
                    or 10.0
                )
                waypoint_distance = distance_km * 0.4 * 1000  # 40% of target distance
                
                lat_offset = (waypoint_distance / 111000) * math.cos(math.radians(bearing))
                lng_offset = (waypoint_distance / 111000) * math.sin(math.radians(bearing)) / math.cos(math.radians(start_point["lat"]))
                
                waypoint = {
                    "lat": start_point["lat"] + lat_offset,
                    "lng": start_point["lng"] + lng_offset,
                }
                
                specs.append(self._attach_quality_meta({
                    "label": chr(65 + idx),
                    "routing_profile": discipline,
                    "generation_strategy": "explorer",
                    "waypoints": [
                        {"lat": start_point["lat"], "lng": start_point["lng"]},
                        waypoint,
                    ],
                    "description": f"Exploration route heading {['north', 'east', 'south', 'west'][idx // 1]}",
                }, confidence=0.5, expected_fit=["scenic"]))

        return specs


class ClassicStrategy(RouteStrategy):
    """Strategy for classic/famous routes - well-known, popular routes."""

    def __init__(self):
        super().__init__(
            name="classic",
            description="Classic and famous routes that are well-known and popular"
        )

    async def generate_route_specs(
        self,
        intent: IntentObject,
        brief: RideBrief,
        ingredients: IngredientSet,
        start_location: Optional[Coordinate],
        db: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Generate classic route specs using named routes and popular trails."""
        start_point = self._normalize_start_location(start_location)
        if not start_point:
            return []

        discipline = self._get_discipline(intent)
        specs = []

        # Try to find named routes first (from location_knowledge)
        try:
            from app.services.named_routes import get_named_route_service
            from app.schemas.route import RouteConstraints
            
            # Create constraints from intent
            constraints = RouteConstraints(
                start=Coordinate(lat=start_point["lat"], lng=start_point["lng"]),
                sport_type=discipline,
                distance_km=intent.hard_constraints.distance_km,
            )
            
            named_route_service = await get_named_route_service()
            # We need db session, but we'll get it from context if available
            # For now, we'll use location_knowledge service directly
            from app.services.location_knowledge import get_location_knowledge_service
            location_service = get_location_knowledge_service()
            
            # Get location region from context if available (we'll pass None for now)
            named_routes = await location_service.suggest_named_routes(
                location=start_location,
                location_region=None,  # Could extract from context
                constraints=constraints,
                db=db,
            )
            
            if named_routes:
                for idx, named_route in enumerate(named_routes[:2]):  # Use top 2 named routes
                    waypoints = [{"lat": start_point["lat"], "lng": start_point["lng"]}]
                    
                    # If named route has geometry, use points from it
                    if named_route.geometry and named_route.geometry.get("type") == "LineString":
                        coords = named_route.geometry.get("coordinates", [])
                        if coords:
                            # Use a key point from the route
                            key_point = coords[len(coords) // 3]  # 1/3 point
                            waypoints.append({"lat": key_point[1], "lng": key_point[0]})
                    
                    specs.append(self._attach_quality_meta({
                        "label": chr(65 + idx),
                        "routing_profile": discipline,
                        "generation_strategy": "classic",
                        "waypoints": waypoints,
                        "description": f"Classic route: {named_route.name}",
                        "named_route": named_route.name,
                    }, confidence=0.8, expected_fit=["scenic", "low_traffic"]))
        except Exception as e:
            logger.warning(f"Failed to get named routes: {e}")

        # Also use well-known trails from networks (higher confidence)
        popular_networks = [n for n in ingredients.networks if n.get("confidence", 0) > 0.7]
        
        if popular_networks and len(specs) < 3:
            for idx, network in enumerate(popular_networks[:3 - len(specs)]):
                # Extract waypoints from network geometry if available
                geometry = network.get("geometry")
                waypoints = [{"lat": start_point["lat"], "lng": start_point["lng"]}]
                
                if geometry and geometry.get("type") == "LineString":
                    coords = geometry.get("coordinates", [])
                    if coords:
                        # Use midpoint or key point from the network
                        mid_idx = len(coords) // 2
                        mid_coord = coords[mid_idx]
                        waypoints.append({"lat": mid_coord[1], "lng": mid_coord[0]})
                
                specs.append(self._attach_quality_meta({
                    "label": chr(65 + len(specs)),
                    "routing_profile": discipline,
                    "generation_strategy": "classic",
                    "waypoints": waypoints,
                    "description": f"Classic route via {network.get('name', 'popular trail')}",
                }, confidence=0.7, expected_fit=["low_traffic", "scenic"]))
        
        # Fallback: balanced loop routes if we still don't have enough
        if len(specs) < 3:
            for idx in range(3 - len(specs)):
                specs.append(self._attach_quality_meta({
                    "label": chr(65 + len(specs)),
                    "routing_profile": discipline,
                    "generation_strategy": "classic",
                    "waypoints": [{"lat": start_point["lat"], "lng": start_point["lng"]}],
                    "description": "Classic balanced route",
                }, confidence=0.6, expected_fit=["low_traffic"]))

        return specs


class HiddenGemStrategy(RouteStrategy):
    """Strategy for hidden gem routes - lesser-known but great routes."""

    def __init__(self):
        super().__init__(
            name="hidden_gem",
            description="Hidden gem routes - lesser-known but excellent routes"
        )

    async def generate_route_specs(
        self,
        intent: IntentObject,
        brief: RideBrief,
        ingredients: IngredientSet,
        start_location: Optional[Coordinate],
        db: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Generate hidden gem route specs using less common trails."""
        start_point = self._normalize_start_location(start_location)
        if not start_point:
            return []

        discipline = self._get_discipline(intent)
        specs = []

        # Use less common networks (lower confidence, but still valid)
        hidden_networks = [n for n in ingredients.networks if 0.4 < n.get("confidence", 0) < 0.7]
        
        if hidden_networks:
            for idx, network in enumerate(hidden_networks[:3]):
                geometry = network.get("geometry")
                waypoints = [{"lat": start_point["lat"], "lng": start_point["lng"]}]
                
                if geometry and geometry.get("type") == "LineString":
                    coords = geometry.get("coordinates", [])
                    if coords:
                        # Use a point from the network
                        point_coord = coords[len(coords) // 3]  # Use 1/3 point
                        waypoints.append({"lat": point_coord[1], "lng": point_coord[0]})
                
                specs.append(self._attach_quality_meta({
                    "label": chr(65 + idx),
                    "routing_profile": discipline,
                    "generation_strategy": "hidden_gem",
                    "waypoints": waypoints,
                    "description": f"Hidden gem route via {network.get('name', 'lesser-known trail')}",
                }, confidence=0.65, expected_fit=["scenic", "unpaved"]))
        else:
            # Fallback: create routes with interesting waypoint patterns
            import math
            distance_km = (
                intent.hard_constraints.distance_km.max
                or intent.hard_constraints.distance_km.min
                or 10.0
            )
            waypoint_distance = distance_km * 0.35 * 1000
            
            # Create routes with interesting angles (not just cardinal directions)
            angles = [30, 150, 270]  # Interesting angles
            
            for idx, angle in enumerate(angles):
                lat_offset = (waypoint_distance / 111000) * math.cos(math.radians(angle))
                lng_offset = (waypoint_distance / 111000) * math.sin(math.radians(angle)) / math.cos(math.radians(start_point["lat"]))
                
                waypoint = {
                    "lat": start_point["lat"] + lat_offset,
                    "lng": start_point["lng"] + lng_offset,
                }
                
                specs.append(self._attach_quality_meta({
                    "label": chr(65 + idx),
                    "routing_profile": discipline,
                    "generation_strategy": "hidden_gem",
                    "waypoints": [
                        {"lat": start_point["lat"], "lng": start_point["lng"]},
                        waypoint,
                    ],
                    "description": "Hidden gem route exploring unique paths",
                }, confidence=0.55, expected_fit=["scenic", "unpaved"]))

        return specs


def select_strategies(intent: IntentObject, brief: RideBrief) -> List[RouteStrategy]:
    """Select appropriate strategies based on intent and brief.
    
    Returns:
        List of RouteStrategy instances to use
    """
    strategies = []
    
    # Analyze intent to determine which strategies to use
    message_lower = intent.source.raw_text.lower() if intent.source else ""
    
    # Check for keywords
    if any(word in message_lower for word in ["classic", "famous", "popular", "well-known", "epic"]):
        strategies.append(ClassicStrategy())
    
    if any(word in message_lower for word in ["explore", "discover", "new", "adventure", "unknown"]):
        strategies.append(ExplorerStrategy())
    
    if any(word in message_lower for word in ["hidden", "gem", "secret", "lesser-known", "off the beaten"]):
        strategies.append(HiddenGemStrategy())
    
    # Default: use a mix if no specific strategy requested
    if not strategies:
        strategies = [ClassicStrategy(), ExplorerStrategy(), HiddenGemStrategy()]
    
    # Limit to 3 strategies max
    return strategies[:3]
