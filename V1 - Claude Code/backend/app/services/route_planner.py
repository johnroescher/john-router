"""
Intelligent Route Planner with Human-Level Reasoning

This module implements a ReAct + Pre-Act pattern for route planning:
- RESEARCH: What trails/roads exist?
- ANALYZE: Which are best for this request?
- PLAN: How should we connect them?
- EXECUTE: Generate and validate the route
- REFINE: Iterate if needed

Based on:
- ReAct: Synergizing Reasoning and Acting (Yao et al., 2022)
- Pre-Act: Multi-Step Planning and Reasoning (2025)
"""
from typing import Dict, Any, List, Optional
import structlog

from app.schemas.route import RouteConstraints, SportType
from app.schemas.common import Coordinate
from app.services.trail_database import get_trail_database

logger = structlog.get_logger()


class IntelligentRoutePlanner:
    """
    Human-like route planning with multi-step reasoning.

    Unlike traditional routing that just calls APIs, this planner:
    1. Understands the request deeply
    2. Researches what trails/roads exist
    3. Analyzes which are best
    4. Plans an elegant route strategy
    5. Executes with validation
    6. Refines until requirements are met
    """

    def __init__(self):
        from app.services.llm_client import get_llm_client, get_llm_model
        self.client = get_llm_client()
        self.model = get_llm_model()

    async def plan_route(
        self,
        user_request: str,
        location: Coordinate,
        constraints: RouteConstraints,
        search_radius_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Plan a route using human-level reasoning.

        Args:
            user_request: Original user message
            location: Starting location
            constraints: Route constraints

        Returns:
            Routing plan with strategy, waypoints, and reasoning
        """
        logger.info(f"=== INTELLIGENT ROUTE PLANNING ===")
        logger.info(f"Request: {user_request}")
        logger.info(f"Sport: {constraints.sport_type}")

        # Phase 1: UNDERSTAND
        understanding = await self._understand_request(user_request, constraints)
        logger.info(f"Understanding: {understanding}")

        # Phase 2: RESEARCH
        trail_knowledge = await self._research_trails(
            location,
            constraints.sport_type,
            user_request,
            search_radius_km=search_radius_km,
        )
        logger.info(f"Trail knowledge acquired: {len(trail_knowledge.get('trails', []))} trails found")

        # Phase 3: ANALYZE
        analysis = await self._analyze_trail_options(understanding, trail_knowledge, constraints)
        logger.info(f"Analysis: {analysis['strategy']}")

        # Phase 4: PLAN
        routing_plan = await self._create_routing_plan(analysis, location, constraints, trail_knowledge)
        logger.info(f"Routing plan created with {len(routing_plan.get('waypoints', []))} waypoints")

        return routing_plan

    async def _understand_request(
        self,
        user_request: str,
        constraints: RouteConstraints,
    ) -> Dict[str, Any]:
        """
        Phase 1: Deeply understand what the user wants.

        For MTB: They want trails, not roads!
        For Road: They want smooth pavement
        For Gravel: They want gravel roads, not singletrack
        """
        prompt = f"""You are an expert route planner. Analyze this request:

Request: "{user_request}"
Sport Type: {constraints.sport_type}

Think step-by-step about what this rider REALLY wants:

1. What is the PRIMARY goal? (e.g., "experience singletrack trails", "smooth road ride", "gravel adventure")
2. What should be MAXIMIZED? (e.g., "time on trails", "scenic views", "elevation gain")
3. What should be AVOIDED? (e.g., "roads except for connections", "traffic", "steep grades")
4. What makes this ride GREAT? (e.g., "flowing singletrack", "challenging climbs", "quiet backroads")

Return a JSON object with:
{{
    "primary_goal": "string",
    "maximize": ["list", "of", "things"],
    "avoid": ["list", "of", "things"],
    "success_criteria": "what makes this ride great",
    "route_character": "overall vibe/feeling this route should have"
}}

Think like a human rider planning their own ride."""

        if self.client:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            import json
            try:
                return json.loads(response.choices[0].message.content)
            except Exception:
                pass

        # Fallback based on sport type
        if constraints.sport_type == SportType.MTB:
            return {
                "primary_goal": "Experience quality singletrack and trail riding",
                "maximize": ["time on trails", "singletrack", "natural terrain", "flow"],
                "avoid": ["paved roads", "highways", "urban areas"],
                "success_criteria": "Route should be primarily on trails and natural surfaces",
                "route_character": "Off-road adventure with minimal pavement"
            }
        if constraints.sport_type == SportType.ROAD:
            return {
                "primary_goal": "Smooth road cycling experience",
                "maximize": ["paved roads", "bike lanes", "scenic routes"],
                "avoid": ["unpaved surfaces", "dirt", "gravel"],
                "success_criteria": "Route should be primarily on paved surfaces",
                "route_character": "Smooth road ride"
            }
        # GRAVEL
        return {
            "primary_goal": "Gravel road adventure",
            "maximize": ["gravel roads", "mixed terrain", "quiet backroads"],
            "avoid": ["singletrack", "highways", "technical trails"],
            "success_criteria": "Route should be primarily on gravel roads",
            "route_character": "Gravel adventure ride"
        }

    async def _research_trails(
        self,
        location: Coordinate,
        sport_type: SportType,
        user_request: str,
        search_radius_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Phase 2: Research what trails/roads actually exist in this area.

        For MTB: Find trail systems, singletrack networks
        For Road: Find bike routes, scenic roads
        For Gravel: Find gravel road networks

        CRITICAL: This now queries actual OSM data to find real trails!
        """
        # Extract location context from request
        context_prompt = f"""Extract trail/route names and locations mentioned in this request:

"{user_request}"

Look for:
- Named trail systems (e.g., "Barton Creek Greenbelt", "Moab Slickrock")
- Named trails (e.g., "West Ridge Trail", "Flume Trail")
- Geographic areas (e.g., "around Boulder", "in Marin County")

Return JSON:
{{
    "trail_systems": ["list of named trail systems"],
    "specific_trails": ["list of named trails"],
    "geographic_areas": ["list of areas mentioned"]
}}"""

        mentioned = {"trail_systems": [], "specific_trails": [], "geographic_areas": []}
        if self.client:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": context_prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            import json
            try:
                mentioned = json.loads(response.choices[0].message.content)
            except Exception:
                mentioned = {"trail_systems": [], "specific_trails": [], "geographic_areas": []}

        # CRITICAL: Query actual trail database from OSM
        logger.info(f"=== QUERYING TRAIL DATABASE FROM OSM ===")
        trail_db = await get_trail_database()

        # Search radius based on expected route distance
        if not search_radius_km:
            search_radius_km = 15

        # Query for actual trails/roads based on sport type
        actual_trails = await trail_db.find_suitable_trails(
            location=location,
            sport_type=sport_type,
            radius_km=search_radius_km,
            limit=50,
        )

        logger.info(f"Found {len(actual_trails)} actual {sport_type.value} trails/roads in area")

        # Log sample of trails found
        if actual_trails:
            sample = actual_trails[:5]
            for trail in sample:
                logger.info(f"  - {trail['name']}: {trail['length_meters']:.0f}m, surface={trail['tags'].get('surface', 'unknown')}")

        # Build knowledge base with ACTUAL trail data
        trail_knowledge = {
            "location": {
                "lat": location.lat,
                "lng": location.lng,
            },
            "mentioned_systems": mentioned.get("trail_systems", []),
            "mentioned_trails": mentioned.get("specific_trails", []),
            "areas": mentioned.get("geographic_areas", []),
            "sport_type": sport_type.value,
            "actual_trails": actual_trails,  # CRITICAL: Real trail data from OSM
            "num_trails_found": len(actual_trails),
        }

        # Add strategy guidance
        if sport_type == SportType.MTB:
            trail_knowledge["trail_strategy"] = "prioritize_singletrack_and_natural_trails"
            trail_knowledge["surface_preference"] = "singletrack > dirt > gravel > pavement"
            trail_knowledge["routing_guidance"] = "Use roads only when absolutely necessary to connect trail systems"
        elif sport_type == SportType.ROAD:
            trail_knowledge["trail_strategy"] = "prioritize_paved_roads_and_bike_lanes"
            trail_knowledge["surface_preference"] = "pavement > bike_lane > quiet_road"
            trail_knowledge["routing_guidance"] = "Avoid unpaved surfaces"
        else:  # GRAVEL
            trail_knowledge["trail_strategy"] = "prioritize_gravel_roads"
            trail_knowledge["surface_preference"] = "gravel > dirt_road > pavement > singletrack"
            trail_knowledge["routing_guidance"] = "Mix of gravel and paved, avoid technical singletrack"

        return trail_knowledge

    async def _analyze_trail_options(
        self,
        understanding: Dict[str, Any],
        trail_knowledge: Dict[str, Any],
        constraints: RouteConstraints,
    ) -> Dict[str, Any]:
        """
        Phase 3: Analyze which trails/roads are best for this request.

        Think like a human: "If I wanted a 2-hour MTB ride here, I would..."
        """
        prompt = f"""You are an expert local rider analyzing route options.

RIDER'S GOAL:
{understanding['primary_goal']}

They want to maximize: {', '.join(understanding['maximize'])}
They want to avoid: {', '.join(understanding['avoid'])}
Success means: {understanding['success_criteria']}

TRAIL KNOWLEDGE:
- Sport type: {trail_knowledge['sport_type']}
- Routing strategy: {trail_knowledge['trail_strategy']}
- Surface preference: {trail_knowledge['surface_preference']}
- Routing guidance: {trail_knowledge['routing_guidance']}
- Mentioned trail systems: {trail_knowledge['mentioned_systems']}

CONSTRAINTS:
- Distance target: {constraints.target_distance_meters / 1609.34 if constraints.target_distance_meters else 'flexible'} miles
- Route type: {constraints.route_type}

Think like a human rider: What would make this a GREAT ride?

Return JSON:
{{
    "strategy": "high-level routing strategy (2-3 sentences)",
    "surface_target": "what % of each surface type should the route have",
    "waypoint_strategy": "how to select waypoints to achieve the goal",
    "validation_criteria": "how to know if the generated route is good",
    "red_flags": "what would make this route BAD (to check for)"
}}

Be specific and actionable."""

        analysis = None
        if self.client:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                top_p=1.0,
            )

            import json
            try:
                analysis = json.loads(response.choices[0].message.content)
            except Exception:
                analysis = None

        if not analysis:
            # Fallback
            if constraints.sport_type == SportType.MTB:
                analysis = {
                    "strategy": "Create a loop that maximizes singletrack and trail riding. Use paved roads only for brief connections between trail systems. Prioritize natural surfaces and off-road character.",
                    "surface_target": "70-90% singletrack/dirt trails, 5-15% gravel, <10% pavement (connections only)",
                    "waypoint_strategy": "Place waypoints on trail systems and trailheads. Avoid waypoints on roads unless connecting distant trail systems.",
                    "validation_criteria": "Route must be primarily off-road. Check that >70% is on trails/dirt/singletrack. Roads should only appear as brief connectors.",
                    "red_flags": "Route with >30% pavement is BAD. Route that stays on roads instead of entering trail systems is BAD. Route that just circles roads near trails without using them is BAD."
                }
            else:
                analysis = {
                    "strategy": "Create route matching sport type preferences",
                    "surface_target": "Appropriate for sport type",
                    "waypoint_strategy": "Standard waypoint placement",
                    "validation_criteria": "Check surface mix matches expectations",
                    "red_flags": "Wrong surface types for sport type"
                }

        return analysis

    async def _create_routing_plan(
        self,
        analysis: Dict[str, Any],
        location: Coordinate,
        constraints: RouteConstraints,
        trail_knowledge: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Phase 4: Create the actual routing plan.

        This returns waypoints and routing instructions that will be passed to
        the routing engine (BRouter/ORS).

        CRITICAL: Now generates actual waypoints from trail database!
        """
        logger.info(f"=== CREATING ROUTING PLAN WITH WAYPOINTS ===")

        # Get actual trails from research phase
        actual_trails = trail_knowledge.get("actual_trails", [])

        # Generate waypoints from trail network
        waypoints = []
        trail_db = await get_trail_database()

        if actual_trails and len(actual_trails) >= 3:
            # We have enough trails to create a good route
            target_distance_km = (constraints.target_distance_meters / 1000) if constraints.target_distance_meters else 20

            # Select strategic waypoints from trail network
            waypoints = trail_db.select_waypoints_from_trails(
                trails=actual_trails,
                start_location=location,
                target_distance_km=target_distance_km,
                num_waypoints=4,  # Create 4 waypoints for a loop
            )

            logger.info(f"Generated {len(waypoints)} waypoints from trail network:")
            for i, wp in enumerate(waypoints):
                logger.info(f"  Waypoint {i+1}: ({wp.lat:.6f}, {wp.lng:.6f})")

        else:
            logger.warning(f"Insufficient trails found ({len(actual_trails)}), cannot generate trail waypoints")
            logger.warning(f"Will fall back to standard routing without trail waypoints")

        return {
            "strategy": analysis["strategy"],
            "surface_target": analysis["surface_target"],
            "validation_criteria": analysis["validation_criteria"],
            "red_flags": analysis["red_flags"],
            "waypoints": waypoints,  # CRITICAL: Real waypoints from trail network!
            "num_waypoints": len(waypoints),
            "trails_available": len(actual_trails),
            "routing_instructions": {
                "sport_type": constraints.sport_type.value,
                "prefer_trails": constraints.sport_type == SportType.MTB,
                "avoid_roads": constraints.sport_type == SportType.MTB,
                "surface_requirements": analysis["surface_target"],
                "use_trail_waypoints": len(waypoints) > 0,
            }
        }


# Singleton
_planner: Optional[IntelligentRoutePlanner] = None


async def get_route_planner() -> IntelligentRoutePlanner:
    """Get or create route planner instance."""
    global _planner
    if _planner is None:
        _planner = IntelligentRoutePlanner()
    return _planner
