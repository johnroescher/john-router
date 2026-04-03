"""Ride Brief Loop orchestrator."""
from __future__ import annotations

import json
import math
from datetime import datetime
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Callable, Awaitable
from uuid import uuid4, UUID

from anthropic import AsyncAnthropic
import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.planning import PlanningSession, PlanningCandidate
from app.schemas.chat import ChatRequest, ChatMessage
from app.schemas.common import Coordinate
from app.schemas.route import SportType
from app.schemas.planning import (
    PlanningLoopResult,
    IntentObject,
    RouteChangeIntent,
    RideBrief,
    DiscoveryPlan,
    IngredientSet,
    CandidateRoute,
    CritiqueReport,
    RankedCandidate,
)
from app.services.planning_tools import (
    geocode_place,
    overpass_query,
    poi_search,
    route_generate,
    route_analyze,
    route_validate,
)
from app.services.user_context import get_user_context_service
from app.schemas.conversation import ConversationContext
from app.services.knowledge_retrieval import get_knowledge_retrieval_service
from app.services.route_strategies import select_strategies
from app.services.route_evaluator import get_route_evaluator
from app.services.route_improver import get_route_improver
from app.services.route_modifier import get_route_modifier
from app.services.cache_service import get_cache_service
from app.core.feature_flags import is_feature_enabled
from app.services.trail_database import get_trail_database
import hashlib

logger = structlog.get_logger()


class RideBriefLoopService:
    """Runs the 6-step Ride Brief Loop."""

    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self.model = "claude-sonnet-4-20250514"

    async def run(
        self,
        request: ChatRequest,
        conversation_history: Optional[List[ChatMessage]],
        db: AsyncSession,
        brief_updates: Optional[Dict[str, Any]] = None,
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
        request_id: Optional[str] = None,
    ) -> PlanningLoopResult:
        import time
        start_ts = time.monotonic()
        planning_events: List[Dict[str, Any]] = []
        llm_calls_used = 0

        async def _status(stage: str, message: str, progress: Optional[float] = None):
            if status_callback:
                try:
                    await status_callback(stage, message, progress)
                except Exception as e:
                    # Don't let status callback errors break the planning loop
                    logger.warning(f"Status callback error: {e}")
            planning_events.append({
                "stage": stage,
                "message": message,
                "progress": progress,
                "elapsed_ms": int((time.monotonic() - start_ts) * 1000),
            })
        
        # Send immediate status update to replace "Starting..." message
        await _status("extracting_intent", "Understanding your request...", 0.05)
        
        context = None  # Initialize context variable
        try:
            session = await self._load_session(db, request.conversation_id)
            # Get user_id from conversation if available (for now, we'll pass None if not available)
            user_id = None
            if request.conversation_id:
                # Try to get user_id from conversation
                from app.models.chat import ChatConversation
                conv_result = await db.execute(
                    select(ChatConversation).where(ChatConversation.id == request.conversation_id)
                )
                conv = conv_result.scalar_one_or_none()
                if conv:
                    user_id = conv.user_id
            
            # Load or create conversation context
            context = await self._load_or_create_context(session, user_id, db)
            
            intent = await self._extract_intent(request, session, db, user_id, context, _status)
            
            # Check if clarification is needed
            if intent.ambiguities and len(intent.ambiguities) > 0 and context:
                # Return early with clarification question
                # The API layer should handle this and return a clarification response
                clarification_question = intent.ambiguities[0].question
                logger.info(f"Clarification needed: {clarification_question}")
                # We'll let the intent pass through - the API will detect ambiguities and handle it
            
            await _status("expanding_brief", "Planning route details...", 0.15)
            brief = await self._expand_brief(intent, session, _status)

            if brief_updates:
                intent = self._apply_intent_updates(intent, brief_updates)
                brief = self._apply_brief_updates(brief, brief_updates)

            change_strategy = self._decide_change_strategy(request, intent)
            if change_strategy == "modify_existing" and request.current_route_geometry:
                await _status("modifying_route", "Updating your existing route...", 0.18)
                modified, critique, failure_reason, fallback_suggestion = await self._modify_existing_route(
                    request=request,
                    intent=intent,
                    brief=brief,
                    context=context,
                    status_callback=_status,
                )

                if modified and critique:
                    return PlanningLoopResult(
                        intent=intent,
                        ride_brief=brief,
                        discovery_plan=None,
                        ingredients=None,
                        candidates=[modified],
                        critique=critique,
                        iteration=1,
                        status="accepted",
                        selected_candidate_id=modified.candidate_id,
                    )

                return PlanningLoopResult(
                    intent=intent,
                    ride_brief=brief,
                    discovery_plan=None,
                    ingredients=None,
                    candidates=[],
                    critique=CritiqueReport(brief_id=brief.brief_id),
                    iteration=1,
                    status="modification_failed",
                    selected_candidate_id=None,
                    failure_reason=failure_reason,
                    fallback_suggestion=fallback_suggestion,
                )

            iteration = 1
            candidates_total = 0
            max_iterations = 3
            max_candidates_total = 12
            max_planning_latency_s = 55.0
            status = "in_progress"
            selected_candidate_id = None

            discovery_plan = None
            ingredients = None
            critique = None
            candidates: List[CandidateRoute] = []

            while iteration <= max_iterations and candidates_total < max_candidates_total:
                if (time.monotonic() - start_ts) > max_planning_latency_s:
                    logger.warning(
                        "planning_latency_cap_hit",
                        elapsed_s=round(time.monotonic() - start_ts, 1),
                        iteration=iteration,
                        candidates=candidates_total,
                    )
                    break
                if iteration > 1:
                    await _status("refining", f"Refining routes (iteration {iteration}/3)...", 0.3 + (iteration - 1) * 0.1)
                
                await _status("discovering_trails", "Planning trail discovery...", 0.25)
                discovery_plan = await self._build_discovery_plan(brief, session, _status)
                await _status("discovering_trails", "Searching for trails and roads...", 0.35)
                ingredients = await self._run_discovery(discovery_plan, brief, intent, _status)
                await _status("generating_routes", "Generating route candidates...", 0.5)
                candidates = await self._compose_candidates(intent, brief, ingredients, db, _status)
                llm_calls_used += 1 + len(candidates)
                candidates_total += len(candidates)
                
                # Evaluate and improve candidates before critique (if features enabled)
                if is_feature_enabled("route_evaluation") or is_feature_enabled("route_improvement"):
                    await _status("evaluating_routes", "Evaluating routes against your request...", 0.65)
                    route_evaluator = get_route_evaluator()
                    route_improver = get_route_improver()
                    
                    user_prefs = context.user_preferences if context else None
                    knowledge = []  # Could retrieve knowledge here if needed

                    import time as _time
                    eval_start = _time.monotonic()
                    MAX_EVAL_IMPROVE_SECONDS = 20.0
                    MAX_LLM_CALLS_PER_REQUEST = 8
                    llm_call_count = getattr(self, '_llm_call_count', 0)

                    if is_feature_enabled("parallel_processing"):
                        # Evaluate candidates in parallel
                        import asyncio
                        eval_tasks = [
                            route_evaluator.evaluate_route_against_intent(
                                route=cand,
                                intent=intent,
                                original_request=request.message if hasattr(request, 'message') else "",
                                user_preferences=user_prefs,
                                knowledge_chunks=knowledge,
                                db=db,
                                user_id=user_id,
                                log_evaluation=True,
                            )
                            for cand in candidates
                        ]
                        evaluations = await asyncio.gather(*eval_tasks, return_exceptions=True)
                        
                        # Improve candidates that need it (in parallel)
                        async def _return_candidate(candidate: CandidateRoute) -> CandidateRoute:
                            return candidate

                        improved_tasks = []
                        for cand, eval_result in zip(candidates, evaluations):
                            if isinstance(eval_result, Exception):
                                logger.warning(f"Evaluation failed for candidate {cand.label}: {eval_result}")
                                improved_tasks.append(_return_candidate(cand))
                            elif is_feature_enabled("route_improvement") and (eval_result.intent_match_score < 0.8 or eval_result.has_significant_issues()):
                                elapsed = _time.monotonic() - eval_start
                                llm_call_count += 1
                                if elapsed > MAX_EVAL_IMPROVE_SECONDS:
                                    logger.warning("eval_improve_time_budget_exceeded", elapsed_s=round(elapsed, 1))
                                    improved_tasks.append(_return_candidate(cand))
                                elif llm_call_count > MAX_LLM_CALLS_PER_REQUEST:
                                    logger.warning("eval_improve_llm_budget_exceeded", calls=llm_call_count)
                                    improved_tasks.append(_return_candidate(cand))
                                else:
                                    improved_tasks.append(route_improver.improve_and_reevaluate(
                                        route=cand,
                                        evaluation=eval_result,
                                        user_intent=intent,
                                        knowledge_chunks=knowledge,
                                    ))
                            else:
                                improved_tasks.append(_return_candidate(cand))
                        
                        # Wait for all improvements
                        improved_candidates = await asyncio.gather(*improved_tasks, return_exceptions=True)
                        
                        # Filter out exceptions and use improved candidates
                        candidates = []
                        for cand in improved_candidates:
                            if isinstance(cand, Exception):
                                continue
                            if isinstance(cand, tuple):
                                candidates.append(cand[0])
                            else:
                                candidates.append(cand)
                    else:
                        # Sequential evaluation (fallback)
                        for cand in candidates:
                            eval_result = await route_evaluator.evaluate_route_against_intent(
                                route=cand,
                                intent=intent,
                                original_request=request.message if hasattr(request, 'message') else "",
                                user_preferences=user_prefs,
                                knowledge_chunks=knowledge,
                                db=db,
                                user_id=user_id,
                                log_evaluation=True,
                            )
                            if is_feature_enabled("route_improvement") and (eval_result.intent_match_score < 0.8 or eval_result.has_significant_issues()):
                                elapsed = _time.monotonic() - eval_start
                                llm_call_count += 1
                                if elapsed > MAX_EVAL_IMPROVE_SECONDS or llm_call_count > MAX_LLM_CALLS_PER_REQUEST:
                                    logger.warning("eval_improve_budget_exceeded_sequential", elapsed_s=round(elapsed, 1), calls=llm_call_count)
                                else:
                                    improved, _ = await route_improver.improve_and_reevaluate(
                                        route=cand,
                                        evaluation=eval_result,
                                        user_intent=intent,
                                        knowledge_chunks=knowledge,
                                    )
                                    idx = candidates.index(cand)
                                    candidates[idx] = improved
                
                llm_calls_used += 1
                await _status("critiquing_routes", "Evaluating route quality...", 0.7)
                critique = await self._critique_candidates(brief, candidates, _status)

                accept, selected_candidate_id = self._should_accept(critique, candidates)
                if accept:
                    status = "accepted"
                    break

                iteration += 1
                if iteration > max_iterations:
                    status = "needs_revision"
                    break

                brief = self._apply_brief_updates(brief, self._critique_updates(critique))

            if not critique:
                critique = CritiqueReport(brief_id=brief.brief_id)

            result = PlanningLoopResult(
                intent=intent,
                ride_brief=brief,
                discovery_plan=discovery_plan,
                ingredients=ingredients,
                candidates=candidates,
                critique=critique,
                iteration=iteration,
                status=status,
                selected_candidate_id=selected_candidate_id,
            )

            await _status("finalizing", "Preparing response...", 0.95)
            # Update context with final results
            if context:
                context.last_route_candidates = candidates
                # Save context to session if available
                if session:
                    try:
                        # Store context in session (we'll need to add this field to PlanningSession or store separately)
                        # For now, we'll just keep it in memory
                        pass
                    except Exception as e:
                        logger.warning(f"Failed to save context: {e}")
            
            await self._persist_session(db, request, result, context=context)
            await _status("finalizing", "Complete", 1.0)

            # Log structured planning summary for observability
            try:
                stage_durations: Dict[str, float] = {}
                last_ts = 0
                last_stage = None
                for event in planning_events:
                    stage = event.get("stage")
                    elapsed = event.get("elapsed_ms", 0)
                    if last_stage is not None:
                        stage_durations[last_stage] = max(0, elapsed - last_ts)
                    last_stage = stage
                    last_ts = elapsed
                if last_stage is not None and last_stage not in stage_durations:
                    stage_durations[last_stage] = max(0, int((time.monotonic() - start_ts) * 1000) - last_ts)

                logger.info(
                    "planning_summary",
                    request_id=request_id,
                    conversation_id=str(request.conversation_id) if request.conversation_id else None,
                    status=result.status,
                    iteration=result.iteration,
                    candidates=len(result.candidates),
                    failure_reason=result.failure_reason,
                    fallback_suggestion=result.fallback_suggestion,
                    stage_durations_ms=stage_durations,
                    llm_calls_used=llm_calls_used,
                    planning_latency_ms=int((time.monotonic() - start_ts) * 1000),
                )
            except Exception as e:
                logger.warning(f"Failed to log planning summary: {e}")

            return result
        except Exception as e:
            # Log error and re-raise so it can be handled by the caller
            logger.error(f"Planning loop error: {e}", exc_info=True)
            await _status("error", f"Error during planning: {str(e)}", None)
            raise

    async def _load_session(
        self,
        db: AsyncSession,
        conversation_id: Optional[UUID],
    ) -> Optional[PlanningSession]:
        if not conversation_id:
            return None
        result = await db.execute(
            select(PlanningSession).where(PlanningSession.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def _extract_intent(
        self,
        request: ChatRequest,
        session: Optional[PlanningSession],
        db: AsyncSession,
        user_id: Optional[UUID] = None,
        context: Optional[ConversationContext] = None,
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> IntentObject:
        if session and isinstance(session.intent_object, dict) and session.intent_object:
            try:
                return IntentObject.model_validate(session.intent_object)
            except Exception:
                pass

        if not self.client:
            intent = self._fallback_intent(request, context=context)
            # Geocode place-based locations even in fallback mode
            if intent.hard_constraints.start.type == "place" and isinstance(intent.hard_constraints.start.value, str):
                if status_callback:
                    await status_callback("geocoding", "Looking up start location...", None)
                geocode = await geocode_place(intent.hard_constraints.start.value)
                if geocode.get("point"):
                    intent.hard_constraints.start = intent.hard_constraints.start.model_copy(
                        update={"type": "point", "value": Coordinate(**geocode["point"])}
                    )
                    intent.notes.append("Start location geocoded from place name.")

            if intent.hard_constraints.end.type == "place" and isinstance(intent.hard_constraints.end.value, str):
                if status_callback:
                    await status_callback("geocoding", "Looking up end location...", None)
                geocode = await geocode_place(intent.hard_constraints.end.value)
                if geocode.get("point"):
                    intent.hard_constraints.end = intent.hard_constraints.end.model_copy(
                        update={"type": "point", "value": Coordinate(**geocode["point"])}
                    )
                    intent.notes.append("End location geocoded from place name.")

            intent = await self._enhance_constraints(intent, request, None, [])
            return intent

        # Retrieve user preferences if available
        user_preferences = None
        if user_id and db:
            try:
                user_context_service = get_user_context_service()
                # Try to get location from request or derive region
                location_region = None
                location = None
                if request.map_center:
                    location = request.map_center
                # For now, we'll pass None for location_region and let the service handle it
                user_preferences = await user_context_service.get_user_preferences(
                    user_id=user_id,
                    location=location,
                    location_region=location_region,
                    db=db,
                )
            except Exception as e:
                logger.warning(f"Failed to retrieve user preferences: {e}", exc_info=True)

        # Retrieve relevant knowledge chunks (if feature enabled)
        knowledge_chunks = []
        if db and is_feature_enabled("vector_search"):
            try:
                knowledge_service = await get_knowledge_retrieval_service()
                location_region = None
                location = request.map_center
                if context and context.location_region:
                    location_region = context.location_region
                
                sport_type = None
                if context and context.sport_type:
                    sport_type = context.sport_type
                
                knowledge_chunks = await knowledge_service.retrieve_knowledge(
                    query=request.message,
                    location=location,
                    location_region=location_region,
                    sport_type=sport_type,
                    limit=5,
                    db=db,
                )
            except Exception as e:
                logger.warning(f"Knowledge retrieval failed: {e}", exc_info=True)

        # Build prompt with user preferences if available
        preferences_text = ""
        if user_preferences:
            prefs_dict = {
                "typical_distance_km": user_preferences.typical_distance_km,
                "preferred_surfaces": user_preferences.preferred_surfaces,
                "avoided_areas": user_preferences.avoided_areas,
                "favorite_trails": user_preferences.favorite_trails,
            }
            preferences_text = f"\nUser preferences (use as defaults if request is vague): {json.dumps(prefs_dict, indent=2)}"

        # Build knowledge context text
        knowledge_text = ""
        if knowledge_chunks:
            knowledge_list = []
            for chunk in knowledge_chunks[:3]:  # Top 3 most relevant
                knowledge_list.append({
                    "content": chunk.content[:200],  # Truncate for prompt
                    "source": chunk.source,
                    "relevance": chunk.relevance_score,
                })
            if knowledge_list:
                knowledge_text = f"\nRelevant local knowledge:\n{json.dumps(knowledge_list, indent=2)}"

        prompt = f"""Extract intent from the user request.
Return ONLY valid JSON matching the IntentObject schema.

If there is a current route, decide whether the user wants to modify the existing route or regenerate a new one.
Populate change_intent with:
- strategy: "modify_existing", "regenerate", or "auto"
- rationale: a short explanation for the strategy
- priority: a short ordered list of the most important user goals
- requested_changes: concrete change requests (e.g., "make it longer", "avoid highways", "add a cafe stop")

User request: "{request.message}"
Current constraints: {json.dumps(request.current_constraints or {})}
Current route context: {json.dumps(request.current_route_geometry or [])}{preferences_text}{knowledge_text}
"""
        try:
            # Add timeout wrapper to prevent hanging
            import asyncio
            payload = await asyncio.wait_for(
                self._llm_json(prompt),
                timeout=35.0,  # Slightly longer than _llm_json timeout
            )
            if not isinstance(payload, dict):
                logger.warning(
                    "llm_intent_parse_non_dict",
                    payload_type=type(payload).__name__,
                )
                return self._fallback_intent(request, context=context)
            payload.setdefault("intent_id", str(uuid4()))
            payload.setdefault("timestamp", datetime.utcnow().isoformat())
            payload.setdefault("source", {
                "raw_text": request.message,
                "conversation_id": request.conversation_id,
                "turn_id": "1",
            })
            intent = IntentObject.model_validate(payload)
            intent = await self._enhance_constraints(intent, request, user_preferences, knowledge_chunks)
            
            # Extract entities and update context
            if context:
                await self._extract_entities(intent, request, context)
                context.last_intent = intent
            
            # Check for ambiguities and handle clarification if needed
            if intent.ambiguities and len(intent.ambiguities) > 0:
                # Store pending clarification in context
                if context:
                    context.pending_clarification = intent.ambiguities[0].question
                # Return intent with ambiguities - caller should handle clarification
                return intent
        except asyncio.TimeoutError:
            logger.error("Intent extraction timed out, using fallback")
            return self._fallback_intent(request, context=context)
        except Exception as e:
            logger.warning("IntentObject validation failed, using fallback", error=str(e), exc_info=True)
            return self._fallback_intent(request, context=context)

        if intent.hard_constraints.start.type == "place" and isinstance(intent.hard_constraints.start.value, str):
            if status_callback:
                await status_callback("geocoding", "Looking up start location...", None)
            geocode = await geocode_place(intent.hard_constraints.start.value)
            if geocode.get("point"):
                intent.hard_constraints.start = intent.hard_constraints.start.model_copy(
                    update={"type": "point", "value": Coordinate(**geocode["point"])}
                )
                intent.notes.append("Start location geocoded from place name.")

        if intent.hard_constraints.end.type == "place" and isinstance(intent.hard_constraints.end.value, str):
            if status_callback:
                await status_callback("geocoding", "Looking up end location...", None)
            geocode = await geocode_place(intent.hard_constraints.end.value)
            if geocode.get("point"):
                intent.hard_constraints.end = intent.hard_constraints.end.model_copy(
                    update={"type": "point", "value": Coordinate(**geocode["point"])}
                )
                intent.notes.append("End location geocoded from place name.")

        return intent

    def _message_requests_regenerate(self, message: str) -> bool:
        msg = (message or "").lower()
        regenerate_phrases = [
            "new route",
            "start over",
            "regenerate",
            "different route",
            "completely different",
            "entirely new",
            "fresh route",
            "replace the route",
        ]
        return any(phrase in msg for phrase in regenerate_phrases)

    def _message_requests_modify(self, message: str) -> bool:
        msg = (message or "").lower()
        modify_phrases = [
            "adjust",
            "tweak",
            "modify",
            "update",
            "change",
            "make it",
            "add",
            "avoid",
            "include",
            "pass by",
            "detour",
            "reroute",
            "shorter",
            "longer",
            "flatter",
            "hillier",
            "less",
            "more",
            "keep",
            "same route",
        ]
        return any(phrase in msg for phrase in modify_phrases)

    def _decide_change_strategy(
        self,
        request: ChatRequest,
        intent: IntentObject,
    ) -> str:
        change_intent = intent.change_intent if intent.change_intent else RouteChangeIntent()

        if not request.current_route_geometry:
            change_intent.strategy = "regenerate"
            if not change_intent.rationale:
                change_intent.rationale = "No current route is available to modify."
            intent.change_intent = change_intent
            return "regenerate"

        strategy = change_intent.strategy or "auto"
        if strategy == "auto":
            if self._message_requests_regenerate(request.message):
                strategy = "regenerate"
            elif self._message_requests_modify(request.message):
                strategy = "modify_existing"
            else:
                strategy = "modify_existing"
            change_intent.strategy = strategy
            if not change_intent.rationale:
                change_intent.rationale = "Inferred from the request and existing route context."

        intent.change_intent = change_intent
        return strategy

    def _resolve_routing_profile(self, intent: IntentObject, request: ChatRequest) -> str:
        discipline = intent.hard_constraints.discipline if intent and intent.hard_constraints else "any"
        if discipline in {"road", "gravel", "mtb", "emtb", "urban"}:
            return discipline
        constraints = request.current_constraints or {}
        profile = constraints.get("sport_type") or constraints.get("sportType")
        if profile in {"road", "gravel", "mtb", "emtb", "urban"}:
            return str(profile)
        return "gravel"

    async def _modify_existing_route(
        self,
        request: ChatRequest,
        intent: IntentObject,
        brief: RideBrief,
        context: Optional[ConversationContext],
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> tuple[Optional[CandidateRoute], Optional[CritiqueReport], Optional[str], Optional[str]]:
        if not request.current_route_geometry:
            return None, None, "I couldn't find a current route to modify.", "Try asking me to generate a new route instead."

        geometry = {
            "type": "LineString",
            "coordinates": request.current_route_geometry,
        }
        routing_profile = self._resolve_routing_profile(intent, request)

        if status_callback:
            await status_callback("analyzing_routes", "Analyzing the current route...", 0.2)
        analysis = await route_analyze(geometry)
        if status_callback:
            await status_callback("validating_routes", "Validating the current route...", 0.25)
        validation = await route_validate(geometry, routing_profile)

        base_candidate = self._build_candidate_from_analysis(
            brief_id=brief.brief_id,
            label="Current",
            routing_profile=routing_profile,
            generation_strategy="existing_route",
            geometry=geometry,
            waypoints=[
                {"lat": coord[1], "lng": coord[0]}
                for coord in (request.current_route_geometry[:2] if request.current_route_geometry else [])
            ],
            analysis=analysis,
            validation=validation,
            transition_segments=[],
        )

        route_modifier = get_route_modifier()
        modified, evaluation, similarity_score, failure_reason = await route_modifier.modify_route(
            route=base_candidate,
            modification_request=request.message,
            original_intent=intent,
            user_preferences=context.user_preferences if context else None,
        )

        if not modified:
            fallback = "I can try generating a fresh route that matches your request if you'd like."
            return None, None, failure_reason or "I couldn't modify the existing route with that request.", fallback

        critique = await self._critique_candidates(brief, [modified], status_callback)
        if evaluation and similarity_score is not None:
            intent.notes.append(f"Similarity to original route: {similarity_score:.2f}")

        return modified, critique, None, None

    async def _expand_brief(
        self,
        intent: IntentObject,
        session: Optional[PlanningSession],
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> RideBrief:
        if session and isinstance(session.ride_brief, dict) and session.ride_brief:
            try:
                return RideBrief.model_validate(session.ride_brief)
            except Exception:
                pass

        if not self.client:
            return self._fallback_brief(intent)

        prompt = f"""Expand intent into a RideBrief.
Return ONLY valid JSON matching the RideBrief schema.

IntentObject:
{json.dumps(intent.model_dump(), indent=2)}
"""
        try:
            payload = await self._llm_json(prompt)
            if isinstance(payload, dict):
                payload.setdefault("brief_id", str(uuid4()))
                payload.setdefault("intent_id", intent.intent_id)
            return RideBrief.model_validate(payload)
        except Exception as e:
            logger.warning("RideBrief validation failed, using fallback", error=str(e))
            return self._fallback_brief(intent)

    async def _build_discovery_plan(
        self,
        brief: RideBrief,
        session: Optional[PlanningSession],
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> DiscoveryPlan:
        if session and isinstance(session.discovery_plan, dict) and session.discovery_plan:
            try:
                return DiscoveryPlan.model_validate(session.discovery_plan)
            except Exception:
                pass

        if not self.client:
            return self._fallback_discovery_plan(brief)

        prompt = f"""Create a DiscoveryPlan for the RideBrief.
Return ONLY valid JSON matching the DiscoveryPlan schema.

RideBrief:
{json.dumps(brief.model_dump(), indent=2)}
"""
        try:
            payload = await self._llm_json(prompt)
            if isinstance(payload, dict):
                payload.setdefault("plan_id", str(uuid4()))
                payload.setdefault("brief_id", brief.brief_id)
            return DiscoveryPlan.model_validate(payload)
        except Exception as e:
            logger.warning("DiscoveryPlan validation failed, using fallback", error=str(e))
            return self._fallback_discovery_plan(brief)

    async def _run_discovery(
        self,
        plan: DiscoveryPlan,
        brief: RideBrief,
        intent: IntentObject,
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> IngredientSet:
        networks = []
        connectors = []
        pois = []
        avoid_zones = []
        notes = []

        priority_tags = self._priority_tags_from_intent(intent)
        plan.queries = self._prioritize_discovery_queries(plan.queries, priority_tags)
        query_count = len(plan.queries)
        for idx, query in enumerate(plan.queries):
            priority = query.parameters.get("priority", 0.0) if query.parameters else 0.0
            if query.tool == "overpass":
                if status_callback:
                    await status_callback("discovering_trails", f"Searching OpenStreetMap... ({idx + 1}/{query_count})", 0.35 + (idx / query_count) * 0.1)
                result = await overpass_query(query.parameters.get("query", ""))
                for feature in result.get("features", []):
                    tags = feature.get("properties", {}).get("tags", {})
                    name = tags.get("name") or f"OSM {feature.get('properties', {}).get('id')}"
                    networks.append({
                        "name": name,
                        "geometry": feature.get("geometry"),
                        "tags": tags,
                        "confidence": 0.6,
                    })
                notes.append(f"Overpass returned {result.get('meta', {}).get('count', 0)} features.")

            if query.tool == "pois":
                if status_callback:
                    await status_callback("discovering_trails", f"Searching points of interest... ({idx + 1}/{query_count})", 0.35 + (idx / query_count) * 0.1)
                result = await poi_search(
                    bbox=query.parameters.get("bbox"),
                    center=query.parameters.get("center"),
                    types=query.parameters.get("types", []),
                    constraints=query.parameters.get("constraints", {}),
                )
                for item in result:
                    pois.append({
                        "type": item.get("type", "poi"),
                        "name": item.get("name", ""),
                        "point": Coordinate(**item.get("point")),
                        "confidence": item.get("confidence", 0.5),
                    })

            if self._should_stop_discovery(priority_tags, priority, networks, pois):
                notes.append("Discovery stopped early after reaching high-signal ingredients.")
                break

        return IngredientSet(
            ingredients_id=str(uuid4()),
            brief_id=brief.brief_id,
            networks=networks,
            connectors=connectors,
            pois=pois,
            avoid_zones=avoid_zones,
            notes=notes,
        )

    async def _compose_candidates(
        self,
        intent: IntentObject,
        brief: RideBrief,
        ingredients: IngredientSet,
        db: AsyncSession,
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> List[CandidateRoute]:
        # Get start location from intent
        start_location = self._extract_start_location(intent)
        
        # Select strategies based on intent
        strategies = select_strategies(intent, brief)
        logger.info(f"Selected {len(strategies)} route strategies: {[s.name for s in strategies]}")
        
        # Generate specs from strategies
        all_specs = []
        for strategy in strategies:
            try:
                strategy_specs = await strategy.generate_route_specs(
                    intent=intent,
                    brief=brief,
                    ingredients=ingredients,
                    start_location=start_location,
                    db=db,
                )
                all_specs.extend(strategy_specs)
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} failed: {e}", exc_info=True)
        
        # Also try LLM generation if available (for additional variety)
        llm_specs = []
        if self.client:
            prompt = f"""Compose 2-3 additional candidate route specs from the RideBrief and IngredientSet.
Return ONLY valid JSON: an array of objects with fields:
label, routing_profile, generation_strategy, waypoints (list of lat/lng pairs).

RideBrief:
{json.dumps(brief.model_dump(), indent=2)}

IngredientSet:
{json.dumps(ingredients.model_dump(), indent=2)}
"""
            try:
                payload = await self._llm_json(prompt)
                if isinstance(payload, list):
                    llm_specs = [s for s in payload if isinstance(s, dict)]
                elif isinstance(payload, dict):
                    llm_specs = [payload]
                else:
                    logger.warning(
                        "llm_compose_specs_unexpected_type",
                        payload_type=type(payload).__name__,
                    )
                    llm_specs = []
            except Exception as e:
                logger.warning("Failed to parse candidate specs from LLM", error=str(e))
        
        # Combine strategy specs and LLM specs
        specs = all_specs + llm_specs
        
        # Add trail DB-driven specs when we don't have good candidates yet
        if start_location:
            discipline = intent.hard_constraints.discipline
            if discipline == "any":
                discipline = "gravel"
            if not specs:
                target_distance_km = self._resolve_target_distance_km(intent, discipline)
                for strategy in ["classic", "explorer", "hidden_gem"]:
                    trail_waypoints = await self._trail_db_waypoints(
                        intent=intent,
                        start_location=start_location,
                        strategy=strategy,
                        target_distance_km=target_distance_km,
                    )
                    if trail_waypoints:
                        specs.append({
                            "label": chr(65 + len(specs)),
                            "routing_profile": discipline,
                            "generation_strategy": f"trail_db_{strategy}",
                            "waypoints": [{"lat": start_location["lat"], "lng": start_location["lng"]}] + trail_waypoints,
                            "confidence": 0.7,
                            "expected_fit": ["unpaved", "scenic"],
                        })

        # If no specs, create a fallback spec using the start location
        if not specs and start_location:
            discipline = intent.hard_constraints.discipline
            if discipline == "any":
                discipline = "gravel"
            specs = [
                {"label": "A", "routing_profile": discipline, "generation_strategy": "balanced", "waypoints": [start_location], "confidence": 0.6, "expected_fit": ["low_traffic"]},
                {"label": "B", "routing_profile": discipline, "generation_strategy": "scenic", "waypoints": [start_location], "confidence": 0.6, "expected_fit": ["scenic"]},
                {"label": "C", "routing_profile": discipline, "generation_strategy": "direct", "waypoints": [start_location], "confidence": 0.5, "expected_fit": []},
            ]
            logger.info("Using fallback route specs with start location", start=start_location)

        specs = self._rank_and_prune_specs(specs, intent)

        candidates: List[CandidateRoute] = []
        total_specs = min(len(specs), 5)
        
        # Assign unique labels if needed
        for idx, spec in enumerate(specs[:5]):
            if "label" not in spec:
                spec["label"] = chr(65 + idx)  # A, B, C, D, E

        async def _build_candidate(spec: Dict[str, Any], idx: int) -> Optional[CandidateRoute]:
            if status_callback:
                await status_callback(
                    "generating_routes",
                    f"Generating route candidate {idx + 1}/{total_specs}...",
                    0.5 + (idx / max(total_specs, 1)) * 0.15,
                )
            waypoints_raw = spec.get("waypoints", [])
            waypoints = []
            for wp in waypoints_raw:
                if isinstance(wp, dict):
                    waypoints.append(wp)
                elif isinstance(wp, list) and len(wp) >= 2:
                    waypoints.append({"lat": wp[0], "lng": wp[1]})

            if not waypoints and start_location:
                waypoints = [start_location]

            if not waypoints:
                logger.warning("No waypoints available, skipping candidate", label=spec.get("label"))
                return None

            avoid_areas = [zone.geometry for zone in ingredients.avoid_zones] if ingredients.avoid_zones else []
            try:
                routing_profile = spec.get("routing_profile", "gravel")
                target_time_minutes = intent.hard_constraints.time_minutes.max or intent.hard_constraints.time_minutes.min
                target_distance_km = self._resolve_target_distance_km(intent, routing_profile)

                route_type = spec.get("route_type") or intent.hard_constraints.route_type
                if route_type == "any" or not route_type:
                    route_type = "loop"
                if route_type == "point_to_point" and len(waypoints) < 2:
                    route_type = "loop"
                spec["route_type"] = route_type

                if route_type in ["loop", "out_and_back"] and len(waypoints) == 1:
                    extra_waypoints = self._default_loop_waypoints(waypoints[0], target_distance_km)
                    if extra_waypoints:
                        waypoints.extend(extra_waypoints)

                options = self._routing_options_from_intent(intent, spec, avoid_areas, target_distance_km, target_time_minutes)
                route = await self._generate_route_with_fallbacks(
                    routing_profile=routing_profile,
                    waypoints=waypoints,
                    options=options,
                )
            except Exception as e:
                logger.warning("Route generation failed for candidate", label=spec.get("label"), error=str(e))
                return None

            if not route:
                logger.warning("Route generation returned no route", label=spec.get("label"))
                return None

            geometry = route.get("geometry")
            if not geometry:
                return None

            if status_callback:
                await status_callback("analyzing_routes", f"Analyzing route {spec.get('label', '?')}...", None)
            analysis = await route_analyze(geometry)
            if status_callback:
                await status_callback("validating_routes", f"Validating route {spec.get('label', '?')}...", None)
            validation = await route_validate(geometry, spec.get("routing_profile", "gravel"))

            candidate = self._build_candidate_from_analysis(
                brief_id=brief.brief_id,
                label=spec.get("label", "A"),
                routing_profile=spec.get("routing_profile", "gravel"),
                generation_strategy=spec.get("generation_strategy", "balanced"),
                geometry=geometry,
                waypoints=waypoints,
                analysis=analysis,
                validation=validation,
                transition_segments=route.get("transition_segments", []),
            )
            return candidate

        quality_threshold = 0.88
        best_score = 0.0
        if is_feature_enabled("parallel_processing"):
            batch_size = 2
            for start_idx in range(0, total_specs, batch_size):
                batch_specs = specs[start_idx:start_idx + batch_size]
                tasks = [asyncio.create_task(_build_candidate(spec, start_idx + idx)) for idx, spec in enumerate(batch_specs)]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    if result:
                        candidates.append(result)
                        score = self._quick_quality_score(result, intent)
                        best_score = max(best_score, score)
                if best_score >= quality_threshold:
                    break
        else:
            for idx, spec in enumerate(specs[:5]):
                candidate = await _build_candidate(spec, idx)
                if candidate:
                    candidates.append(candidate)
                    score = self._quick_quality_score(candidate, intent)
                    best_score = max(best_score, score)
                    if best_score >= quality_threshold:
                        break

        return candidates

    def _extract_start_location(self, intent: IntentObject) -> Optional[Dict[str, float]]:
        """Extract start location from intent."""
        start = intent.hard_constraints.start
        if start.type == "point" and isinstance(start.value, Coordinate):
            return {"lat": start.value.lat, "lng": start.value.lng}
        if start.type == "point" and isinstance(start.value, dict):
            return {"lat": start.value.get("lat"), "lng": start.value.get("lng")}
        return None

    async def _critique_candidates(
        self,
        brief: RideBrief,
        candidates: List[CandidateRoute],
        status_callback: Optional[Callable[[str, str, Optional[float]], Awaitable[None]]] = None,
    ) -> CritiqueReport:
        if not self.client:
            ranked = []
            for idx, candidate in enumerate(candidates):
                ranked.append(RankedCandidate(
                    candidate_id=candidate.candidate_id,
                    score_total=max(60, 90 - (idx * 5)),
                    score_breakdown=[],
                    major_mismatches=[],
                    best_for="default",
                    recommendation="primary" if idx == 0 else "secondary",
                ))
            return CritiqueReport(brief_id=brief.brief_id, ranked_candidates=ranked)

        prompt = f"""Critique and rank candidates.
Return ONLY valid JSON matching the CritiqueReport schema.

RideBrief:
{json.dumps(brief.model_dump(), indent=2)}

Candidates:
{json.dumps([c.model_dump() for c in candidates], indent=2)}
"""
        try:
            payload = await self._llm_json(prompt)
            if isinstance(payload, dict):
                payload.setdefault("brief_id", brief.brief_id)
            return CritiqueReport.model_validate(payload)
        except Exception as e:
            logger.warning("CritiqueReport validation failed, using fallback", error=str(e))
            return CritiqueReport(brief_id=brief.brief_id)

    def _should_accept(
        self,
        critique: CritiqueReport,
        candidates: List[CandidateRoute],
    ) -> Tuple[bool, Optional[str]]:
        if not critique.ranked_candidates:
            return False, None
        ranked = critique.ranked_candidates[0]
        candidate = next((c for c in candidates if c.candidate_id == ranked.candidate_id), None)
        if not candidate:
            return False, None
        has_errors = any(issue.severity == "error" for issue in candidate.validation.issues)
        if ranked.score_total >= 85 and candidate.validation.status == "pass" and not has_errors:
            return True, candidate.candidate_id
        return False, None

    def _critique_updates(self, critique: CritiqueReport) -> Dict[str, Any]:
        updates = {}
        for update in critique.brief_updates:
            updates[update.path] = update.new_value
        return updates

    def _apply_intent_updates(self, intent: IntentObject, updates: Dict[str, Any]) -> IntentObject:
        if not updates:
            return intent
        updated = intent.model_copy(deep=True)
        if "intent.hard_constraints.time_minutes" in updates:
            value = updates["intent.hard_constraints.time_minutes"]
            if isinstance(value, dict):
                updated.hard_constraints.time_minutes = updated.hard_constraints.time_minutes.model_copy(update=value)
        if "intent.hard_constraints.distance_km" in updates:
            value = updates["intent.hard_constraints.distance_km"]
            if isinstance(value, dict):
                updated.hard_constraints.distance_km = updated.hard_constraints.distance_km.model_copy(update=value)
        return updated

    def _apply_brief_updates(self, brief: RideBrief, updates: Dict[str, Any]) -> RideBrief:
        if not updates:
            return brief
        updated = brief.model_copy(deep=True)
        for path, value in updates.items():
            if path in ("$.implicit_defaults.pavement_max_pct.value", "brief.pavement_max_pct"):
                updated.implicit_defaults.pavement_max_pct.value = value
            elif path in ("$.implicit_defaults.technical_max.value", "brief.technical_max"):
                updated.implicit_defaults.technical_max.value = value
            elif path in ("$.implicit_defaults.traffic_stress_max.value", "brief.traffic_stress_max"):
                updated.implicit_defaults.traffic_stress_max.value = value
        return updated

    async def _persist_session(
        self,
        db: AsyncSession,
        request: ChatRequest,
        result: PlanningLoopResult,
        context: Optional[ConversationContext] = None,
    ) -> None:
        session = await self._load_session(db, request.conversation_id)
        if not session:
            session = PlanningSession(
                conversation_id=request.conversation_id,
                user_id=None,
            )
            db.add(session)

        session.intent_object = result.intent.model_dump()
        session.ride_brief = result.ride_brief.model_dump()
        session.discovery_plan = result.discovery_plan.model_dump() if result.discovery_plan else {}
        session.ingredient_set = result.ingredients.model_dump() if result.ingredients else {}
        session.critique_report = result.critique.model_dump() if result.critique else {}
        if context:
            session.conversation_context = context.model_dump()
        session.iteration = result.iteration
        session.status = result.status
        session.selected_candidate_id = UUID(result.selected_candidate_id) if result.selected_candidate_id else None

        await db.flush()

        await db.execute(delete(PlanningCandidate).where(PlanningCandidate.session_id == session.id))
        for candidate in result.candidates:
            geometry = candidate.geometry
            db_candidate = PlanningCandidate(
                session_id=session.id,
                label=candidate.label,
                routing_profile=candidate.routing_profile,
                generation_strategy=candidate.generation_strategy,
                waypoints=[wp.model_dump() for wp in candidate.waypoints],
                computed=candidate.computed.model_dump(),
                validation=candidate.validation.model_dump(),
            )
            if geometry and geometry.get("type") == "LineString":
                from geoalchemy2.shape import from_shape
                from shapely.geometry import LineString

                line = LineString([(c[0], c[1]) for c in geometry.get("coordinates", [])])
                db_candidate.geometry = from_shape(line, srid=4326)
            db.add(db_candidate)

        await db.commit()

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
        candidate_id = str(uuid4())

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

        candidate = CandidateRoute(
            candidate_id=candidate_id,
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
            ],
            computed=computed,
            validation={"status": status, "issues": validation_issues},
            transition_segments=transition_segments or [],
        )
        return candidate

    def _fallback_intent(self, request: ChatRequest, context: Optional[ConversationContext] = None) -> IntentObject:
        from app.schemas.planning import HardConstraint, LocationSpec
        
        # Try to extract start location from current_constraints
        hard_constraints = HardConstraint()
        if request.current_constraints:
            start_data = request.current_constraints.get("start", {})
            if start_data and start_data.get("lat") and start_data.get("lng"):
                hard_constraints.start = LocationSpec(
                    type="point",
                    value=Coordinate(lat=start_data["lat"], lng=start_data["lng"])
                )

        # Use map center if provided
        if hard_constraints.start.type == "none" and request.map_center:
            hard_constraints.start = LocationSpec(
                type="point",
                value=Coordinate(lat=request.map_center.lat, lng=request.map_center.lng),
            )

        # Use context start location if available
        if hard_constraints.start.type == "none" and context:
            stored_start = context.entities.get("start_location") if context.entities else None
            stored_place = context.entities.get("start_place") if context.entities else None
            if isinstance(stored_start, dict) and stored_start.get("lat") is not None and stored_start.get("lng") is not None:
                hard_constraints.start = LocationSpec(
                    type="point",
                    value=Coordinate(lat=stored_start["lat"], lng=stored_start["lng"]),
                )
            elif isinstance(stored_place, str) and stored_place.strip():
                hard_constraints.start = LocationSpec(
                    type="place",
                    value=stored_place.strip(),
                )

        # Attempt to capture a place name for later geocoding
        if hard_constraints.start.type == "none":
            import re
            match = re.search(r"(?:from|starting from|near|in|at)\s+([A-Za-z\s,]+)", request.message, re.IGNORECASE)
            if match:
                hard_constraints.start = LocationSpec(
                    type="place",
                    value=match.group(1).strip(),
                )
        
        # Try to extract discipline from message
        message_lower = request.message.lower()
        if "mtb" in message_lower or "mountain bike" in message_lower or "trail" in message_lower:
            hard_constraints.discipline = "mtb"
        elif "road" in message_lower or "pavement" in message_lower:
            hard_constraints.discipline = "road"
        elif "gravel" in message_lower:
            hard_constraints.discipline = "gravel"

        # Try to extract time from message
        time_minutes = self._parse_time_minutes(request.message)
        if time_minutes:
            hard_constraints.time_minutes.min = time_minutes
            hard_constraints.time_minutes.max = time_minutes

        change_intent = RouteChangeIntent()
        if request.current_route_geometry:
            if self._message_requests_regenerate(request.message):
                change_intent.strategy = "regenerate"
                change_intent.rationale = "User asked to start fresh."
            elif self._message_requests_modify(request.message):
                change_intent.strategy = "modify_existing"
                change_intent.rationale = "User requested a change to the existing route."
        else:
            change_intent.strategy = "regenerate"
            change_intent.rationale = "No current route is available to modify."
        
        return IntentObject(
            intent_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source={"raw_text": request.message, "conversation_id": request.conversation_id, "turn_id": "1"},
            hard_constraints=hard_constraints,
            change_intent=change_intent,
            confidence=0.2,
            notes=["Fallback intent (LLM unavailable)."],
        )

    def _parse_time_minutes(self, message: str) -> Optional[float]:
        if not message:
            return None
        import re

        hours_match = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hours|hr|hrs)\b", message, re.IGNORECASE)
        minutes_match = re.search(r"(\d+(?:\.\d+)?)\s*(minute|minutes|min|mins)\b", message, re.IGNORECASE)

        minutes_total = 0.0
        if hours_match:
            minutes_total += float(hours_match.group(1)) * 60
        if minutes_match:
            minutes_total += float(minutes_match.group(1))

        return minutes_total if minutes_total > 0 else None

    def _resolve_target_distance_km(self, intent: IntentObject, routing_profile: str) -> Optional[float]:
        distance = intent.hard_constraints.distance_km
        if distance and (distance.max or distance.min):
            return distance.max or distance.min

        time_range = intent.hard_constraints.time_minutes
        if time_range and (time_range.max or time_range.min):
            minutes = time_range.max or time_range.min
            speed_kmh = self._profile_speed_kmh(routing_profile)
            return max(5.0, (minutes / 60.0) * speed_kmh)

        return None

    def _default_loop_waypoints(
        self,
        start: Dict[str, float],
        target_distance_km: Optional[float],
    ) -> List[Dict[str, float]]:
        """Generate a simple multi-point via pattern for loop routing."""
        if not start:
            return []
        lat = start.get("lat")
        lng = start.get("lng")
        if lat is None or lng is None:
            return []

        distance_km = target_distance_km or 12.0
        waypoint_distance_m = max(1500.0, distance_km * 1000 * 0.35)
        lat_scale = 111000.0
        lng_scale = 111000.0 * max(0.1, math.cos(math.radians(lat)))

        bearings = [35.0, 165.0]
        waypoints: List[Dict[str, float]] = []
        for bearing in bearings:
            lat_offset = (waypoint_distance_m / lat_scale) * math.cos(math.radians(bearing))
            lng_offset = (waypoint_distance_m / lng_scale) * math.sin(math.radians(bearing))
            waypoints.append({
                "lat": lat + lat_offset,
                "lng": lng + lng_offset,
            })
        return waypoints

    def _profile_speed_kmh(self, routing_profile: str) -> float:
        profile = routing_profile or "gravel"
        speed_kmh_by_profile = {
            "road": 24.0,
            "gravel": 18.0,
            "mtb": 14.0,
            "emtb": 16.0,
            "urban": 16.0,
        }
        return speed_kmh_by_profile.get(profile, 18.0)

    def _routing_attempts(self, routing_profile: str) -> List[Dict[str, str]]:
        profile = routing_profile or "gravel"
        attempts: List[Dict[str, str]] = []

        # Always try the default AUTO path first.
        attempts.append({})

        if profile in ["mtb", "emtb"]:
            attempts.extend([
                {"routing_service": "brouter", "routing_profile": "mtb"},
                {"routing_service": "graphhopper", "routing_profile": "mtb"},
                {"routing_service": "ors", "routing_profile": "cycling-mountain"},
            ])
        elif profile == "gravel":
            attempts.extend([
                {"routing_service": "brouter", "routing_profile": "trekking"},
                {"routing_service": "ors", "routing_profile": "cycling-regular"},
                {"routing_service": "graphhopper", "routing_profile": "bike"},
            ])
        elif profile == "road":
            attempts.extend([
                {"routing_service": "ors", "routing_profile": "driving-car"},
                {"routing_service": "graphhopper", "routing_profile": "bike"},
                {"routing_service": "brouter", "routing_profile": "fastbike"},
            ])
        else:
            attempts.extend([
                {"routing_service": "brouter", "routing_profile": "trekking"},
                {"routing_service": "ors", "routing_profile": "cycling-regular"},
            ])

        return attempts

    async def _generate_route_with_fallbacks(
        self,
        routing_profile: str,
        waypoints: List[Dict[str, Any]],
        options: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        last_error = None
        for attempt in self._routing_attempts(routing_profile):
            attempt_options = dict(options)
            if attempt.get("routing_service"):
                attempt_options["routing_service"] = attempt["routing_service"]
            if attempt.get("routing_profile"):
                attempt_options["routing_profile"] = attempt["routing_profile"]
            try:
                route = await route_generate(
                    profile=routing_profile,
                    waypoints=waypoints,
                    options=attempt_options,
                )
                meta = route.get("meta", {})
                if meta.get("success") is False or not route.get("geometry"):
                    last_error = meta.get("error") or "no_geometry"
                    continue
                return route
            except Exception as e:
                last_error = str(e)
                continue

        logger.warning("All routing attempts failed", error=last_error)
        return None

    async def _trail_db_waypoints(
        self,
        intent: IntentObject,
        start_location: Dict[str, float],
        strategy: str,
        target_distance_km: Optional[float],
    ) -> List[Dict[str, float]]:
        if not start_location:
            return []

        discipline = intent.hard_constraints.discipline
        if discipline == "mtb":
            sport_type = SportType.MTB
        elif discipline == "road":
            sport_type = SportType.ROAD
        else:
            sport_type = SportType.GRAVEL

        start_coord = Coordinate(lat=start_location["lat"], lng=start_location["lng"])
        radius_km = min(40.0, max(10.0, (target_distance_km or 20.0) * 0.6))

        trail_db = await get_trail_database()
        trails = await trail_db.find_suitable_trails(
            location=start_coord,
            sport_type=sport_type,
            radius_km=radius_km,
            limit=60,
        )
        if not trails:
            return []

        waypoints = trail_db.select_waypoints_from_trails(
            trails=trails,
            start_location=start_coord,
            target_distance_km=target_distance_km or 20.0,
            num_waypoints=3,
            strategy=strategy,
        )
        return [{"lat": wp.lat, "lng": wp.lng} for wp in waypoints]

    def _fallback_brief(self, intent: IntentObject) -> RideBrief:
        return RideBrief(
            brief_id=str(uuid4()),
            intent_id=intent.intent_id,
            archetype={"name": "custom", "rationale": "Fallback brief", "confidence": 0.2},
            experience_shape=[],
            implicit_defaults={
                "pavement_max_pct": {"value": 0.4, "source": "ASSUMED", "confidence": 0.3},
                "singletrack_min_pct": {"value": None, "source": "ASSUMED", "confidence": 0.3},
                "traffic_stress_max": {"value": "med", "source": "ASSUMED", "confidence": 0.3},
                "technical_max": {"value": "blue", "source": "ASSUMED", "confidence": 0.3},
                "grade_limits": {
                    "up_max_pct": {"value": None, "source": "ASSUMED", "confidence": 0.3},
                    "down_max_pct": {"value": None, "source": "ASSUMED", "confidence": 0.3},
                },
                "stop_density": {"value": "some", "source": "ASSUMED", "confidence": 0.3},
            },
            success_criteria=[],
            tradeoffs=[],
            fallback_strategies=[],
            ask_user_if_needed=[],
            brief_summary_for_ui={
                "one_liner": "Draft ride brief (LLM unavailable).",
                "bullets": ["Defaults applied", "Will refine on next iteration", "No user questions asked"],
            },
        )

    def _fallback_discovery_plan(self, brief: RideBrief) -> DiscoveryPlan:
        return DiscoveryPlan(
            plan_id=str(uuid4()),
            brief_id=brief.brief_id,
            search_radius_km=15,
            focus_regions=[],
            queries=[],
            stop_when=[],
        )

    async def _enhance_constraints(
        self,
        intent: IntentObject,
        request: ChatRequest,
        user_preferences: Optional[Any],
        knowledge_chunks: List[Any],
    ) -> IntentObject:
        priority_tags = self._priority_tags_from_text(request.message)
        intent = self._apply_priority_tags(intent, priority_tags)

        if not self.client:
            if priority_tags:
                intent.notes.append(f"priority_tags: {', '.join(priority_tags)}")
            return intent

        prompt = f"""Enhance intent constraints using the user request.
Return ONLY valid JSON with keys:
priorities: array of up to 3 tags from [scenic, low_traffic, unpaved, smooth, climb, shorter_drive, poi]
hard_constraints: object with optional fields distance_km{{min,max}}, elevation_gain_m{{min,max}}, discipline, route_type
soft_preferences: object with optional fields scenic_bias, traffic_stress_max, technical_max, navigation_complexity, surface_mix{{pavement, gravel, dirt, singletrack}}
confidence: number 0-1 indicating confidence in the enhancements

User request: "{request.message}"
Current intent: {json.dumps(intent.model_dump(), indent=2)}
"""
        try:
            payload = await asyncio.wait_for(self._llm_json(prompt), timeout=12.0)
        except Exception as e:
            logger.warning("Constraint enhancement failed, using heuristics", error=str(e))
            payload = {}

        if isinstance(payload, dict):
            priority_tags = payload.get("priorities") or priority_tags
            confidence = float(payload.get("confidence", 0.0) or 0.0)
            intent = self._apply_priority_tags(intent, priority_tags)
            if priority_tags:
                intent.notes.append(f"priority_tags: {', '.join(priority_tags)}")
            if confidence >= 0.6:
                intent = self._apply_constraint_overrides(intent, payload)

        return intent

    def _apply_priority_tags(self, intent: IntentObject, priority_tags: List[str]) -> IntentObject:
        if not priority_tags:
            return intent

        updated = intent.model_copy(deep=True)
        prefs = updated.soft_preferences

        if "scenic" in priority_tags and prefs.scenic_bias in {"low", "med"}:
            prefs.scenic_bias = "high"
        if "low_traffic" in priority_tags and prefs.traffic_stress_max in {"unknown", "high", "med"}:
            prefs.traffic_stress_max = "low"
        if "smooth" in priority_tags and prefs.technical_max in {"unknown", "black", "double_black"}:
            prefs.technical_max = "blue"
        if "unpaved" in priority_tags and prefs.surface_mix.pavement is None:
            prefs.surface_mix.pavement = 0.1
            prefs.surface_mix.gravel = 0.5
            prefs.surface_mix.dirt = 0.2
            prefs.surface_mix.singletrack = 0.2

        return updated

    def _apply_constraint_overrides(self, intent: IntentObject, payload: Dict[str, Any]) -> IntentObject:
        updated = intent.model_copy(deep=True)
        hard = payload.get("hard_constraints") or {}
        soft = payload.get("soft_preferences") or {}

        if isinstance(hard, dict):
            distance = hard.get("distance_km", {})
            if isinstance(distance, dict):
                if updated.hard_constraints.distance_km.min is None and distance.get("min") is not None:
                    updated.hard_constraints.distance_km.min = float(distance["min"])
                if updated.hard_constraints.distance_km.max is None and distance.get("max") is not None:
                    updated.hard_constraints.distance_km.max = float(distance["max"])
            elevation = hard.get("elevation_gain_m", {})
            if isinstance(elevation, dict):
                if updated.hard_constraints.elevation_gain_m.min is None and elevation.get("min") is not None:
                    updated.hard_constraints.elevation_gain_m.min = float(elevation["min"])
                if updated.hard_constraints.elevation_gain_m.max is None and elevation.get("max") is not None:
                    updated.hard_constraints.elevation_gain_m.max = float(elevation["max"])
            discipline = hard.get("discipline")
            if discipline and updated.hard_constraints.discipline == "any":
                updated.hard_constraints.discipline = str(discipline)
            route_type = hard.get("route_type")
            if route_type and updated.hard_constraints.route_type == "any":
                updated.hard_constraints.route_type = str(route_type)

        if isinstance(soft, dict):
            if updated.soft_preferences.scenic_bias in {"med", "low"} and soft.get("scenic_bias"):
                updated.soft_preferences.scenic_bias = self._normalize_bias_level(str(soft["scenic_bias"]))
            if updated.soft_preferences.traffic_stress_max in {"unknown", "med", "high"} and soft.get("traffic_stress_max"):
                updated.soft_preferences.traffic_stress_max = self._normalize_bias_level(str(soft["traffic_stress_max"]))
            if updated.soft_preferences.technical_max in {"unknown", "black", "double_black"} and soft.get("technical_max"):
                updated.soft_preferences.technical_max = str(soft["technical_max"])
            if updated.soft_preferences.navigation_complexity in {"unknown"} and soft.get("navigation_complexity"):
                updated.soft_preferences.navigation_complexity = str(soft["navigation_complexity"])
            surface_mix = soft.get("surface_mix", {})
            if isinstance(surface_mix, dict) and updated.soft_preferences.surface_mix.pavement is None:
                updated.soft_preferences.surface_mix.pavement = surface_mix.get("pavement")
                updated.soft_preferences.surface_mix.gravel = surface_mix.get("gravel")
                updated.soft_preferences.surface_mix.dirt = surface_mix.get("dirt")
                updated.soft_preferences.surface_mix.singletrack = surface_mix.get("singletrack")

        return updated

    def _priority_tags_from_text(self, message: str) -> List[str]:
        if not message:
            return []
        msg = message.lower()
        keyword_map = {
            "scenic": ["scenic", "view", "views", "vista", "overlook", "pretty", "beautiful"],
            "low_traffic": ["quiet", "low traffic", "avoid cars", "no cars", "traffic", "safe roads"],
            "unpaved": ["gravel", "dirt", "trail", "singletrack", "unpaved"],
            "smooth": ["smooth", "beginner", "easy", "flowy", "not technical"],
            "climb": ["climb", "climbing", "hilly", "elevation", "vert"],
            "shorter_drive": ["nearby", "close", "local", "near me"],
            "poi": ["coffee", "cafe", "viewpoint", "water", "stop", "poi"],
        }

        scores: Dict[str, int] = {}
        for tag, keywords in keyword_map.items():
            scores[tag] = sum(1 for kw in keywords if kw in msg)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [tag for tag, score in ranked if score > 0][:3]

    def _normalize_bias_level(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"medium", "mid"}:
            return "med"
        if normalized in {"low", "med", "high"}:
            return normalized
        return "med"

    def _priority_tags_from_intent(self, intent: IntentObject) -> List[str]:
        tags = []
        prefs = intent.soft_preferences
        if prefs.scenic_bias == "high":
            tags.append("scenic")
        if prefs.traffic_stress_max == "low":
            tags.append("low_traffic")
        if prefs.surface_mix and prefs.surface_mix.pavement is not None:
            if (prefs.surface_mix.gravel or 0) + (prefs.surface_mix.dirt or 0) + (prefs.surface_mix.singletrack or 0) > 0.6:
                tags.append("unpaved")
        if prefs.technical_max in {"green", "blue"}:
            tags.append("smooth")
        if intent.hard_constraints.elevation_gain_m.min and intent.hard_constraints.elevation_gain_m.min > 400:
            tags.append("climb")
        return tags[:3]

    def _prioritize_discovery_queries(
        self,
        queries: List[DiscoveryQuery],
        priority_tags: List[str],
    ) -> List[DiscoveryQuery]:
        if not queries or not priority_tags:
            return queries

        def _score(query: DiscoveryQuery) -> float:
            score = 0.1
            if query.tool == "pois" and ("poi" in priority_tags or "scenic" in priority_tags):
                score += 0.5
            if query.tool == "overpass" and ("unpaved" in priority_tags or "low_traffic" in priority_tags):
                score += 0.4
            if query.parameters and query.parameters.get("types"):
                types = " ".join(query.parameters.get("types") or []).lower()
                if "view" in types or "scenic" in types:
                    score += 0.3
                if "water" in types or "cafe" in types:
                    score += 0.2
            return score

        scored = []
        for query in queries:
            score = _score(query)
            query.parameters.setdefault("priority", round(score, 2))
            query.parameters.setdefault("priority_tags", priority_tags)
            scored.append((score, query))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [query for _, query in scored]

    def _should_stop_discovery(
        self,
        priority_tags: List[str],
        current_priority: float,
        networks: List[Dict[str, Any]],
        pois: List[Dict[str, Any]],
    ) -> bool:
        if not priority_tags:
            return False
        if len(networks) >= 60 or len(pois) >= 15:
            return current_priority < 0.6
        return False

    def _rank_and_prune_specs(self, specs: List[Dict[str, Any]], intent: IntentObject) -> List[Dict[str, Any]]:
        if not specs:
            return specs

        scored_specs = []
        for spec in specs:
            spec.setdefault("confidence", 0.5)
            spec.setdefault("expected_fit", [])
            score = self._score_spec_for_intent(spec, intent)
            spec["quality_score"] = round(score, 3)
            scored_specs.append((score, spec))

        scored_specs.sort(key=lambda item: item[0], reverse=True)
        filtered = [spec for _, spec in scored_specs if spec.get("quality_score", 0) >= 0.35]
        if len(filtered) < 3:
            filtered = [spec for _, spec in scored_specs][:max(3, len(scored_specs))]
        return filtered

    def _score_spec_for_intent(self, spec: Dict[str, Any], intent: IntentObject) -> float:
        score = float(spec.get("confidence", 0.5)) * 0.6
        expected_fit = set(spec.get("expected_fit") or [])
        priority_tags = set(self._priority_tags_from_intent(intent))

        if priority_tags & expected_fit:
            score += 0.25

        discipline = intent.hard_constraints.discipline
        routing_profile = str(spec.get("routing_profile", "gravel"))
        if discipline != "any" and routing_profile == discipline:
            score += 0.15
        if discipline == "road" and routing_profile in {"gravel", "mtb"}:
            score -= 0.15

        if intent.soft_preferences.scenic_bias == "high" and "scenic" in expected_fit:
            score += 0.1
        if intent.soft_preferences.traffic_stress_max == "low" and "low_traffic" in expected_fit:
            score += 0.1

        return max(0.0, min(1.0, score))

    def _quick_quality_score(self, candidate: CandidateRoute, intent: IntentObject) -> float:
        score = 0.5
        if candidate.computed:
            distance_km = candidate.computed.distance_km
            if distance_km and intent.hard_constraints.distance_km:
                target_min = intent.hard_constraints.distance_km.min
                target_max = intent.hard_constraints.distance_km.max
                if target_min and target_max and target_min <= distance_km <= target_max:
                    score += 0.25
            surface = candidate.computed.surface_mix.model_dump() if candidate.computed.surface_mix else {}
            if surface and intent.soft_preferences.surface_mix.pavement is not None:
                unpaved = surface.get("gravel", 0) + surface.get("dirt", 0) + surface.get("singletrack", 0)
                if unpaved >= 40 and intent.soft_preferences.surface_mix.pavement < 0.3:
                    score += 0.15
        if candidate.validation and candidate.validation.status != "fail":
            score += 0.1
        return min(1.0, score)

    def _routing_options_from_intent(
        self,
        intent: IntentObject,
        spec: Dict[str, Any],
        avoid_areas: List[Dict[str, Any]],
        target_distance_km: Optional[float],
        target_time_minutes: Optional[float],
    ) -> Dict[str, Any]:
        surface_mix = intent.soft_preferences.surface_mix
        surface_preferences = None
        if surface_mix and surface_mix.pavement is not None:
            pavement = float(surface_mix.pavement or 0)
            gravel = float(surface_mix.gravel or 0)
            singletrack = float(surface_mix.singletrack or 0)
            dirt = float(surface_mix.dirt or 0)
            gravel += dirt
            total = max(0.0001, pavement + gravel + singletrack)
            surface_preferences = {
                "pavement": pavement / total,
                "gravel": gravel / total,
                "singletrack": singletrack / total,
            }

        avoid_highways = intent.soft_preferences.traffic_stress_max == "low"
        target_elevation = intent.hard_constraints.elevation_gain_m.min or intent.hard_constraints.elevation_gain_m.max

        return {
            "route_type": spec.get("route_type", "loop"),
            "target_distance_km": target_distance_km,
            "min_distance_km": intent.hard_constraints.distance_km.min,
            "max_distance_km": intent.hard_constraints.distance_km.max,
            "target_time_seconds": (target_time_minutes * 60) if target_time_minutes else None,
            "target_elevation_gain_m": target_elevation,
            "avoid_areas": avoid_areas,
            "avoid_highways": avoid_highways,
            "surface_preferences": surface_preferences,
            "quality_mode": True,
            "num_alternatives": 3,
        }

    async def _llm_json(self, prompt: str) -> Any:
        if not self.client:
            logger.warning("Anthropic client not available, returning empty JSON")
            return {}
        
        try:
            # Add timeout to prevent hanging
            import asyncio
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=30.0,  # 30 second timeout
            )
            text = response.content[0].text if response.content else "{}"
            cleaned = self._extract_json(text)
            try:
                result = json.loads(cleaned)
                # Cache the result (1 hour TTL for LLM responses)
                cache_service = await get_cache_service()
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
                cache_key = f"llm:json:{prompt_hash}"
                await cache_service.set(cache_key, result, ttl_seconds=3600)
                return result
            except json.JSONDecodeError as e:
                logger.warning("JSON decode failed, attempting recovery", error=str(e), text_preview=cleaned[:200])
                # Try to find and parse just the first valid JSON structure
                result = self._parse_first_json(cleaned)
                # Cache even if recovery was needed
                cache_service = await get_cache_service()
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
                cache_key = f"llm:json:{prompt_hash}"
                await cache_service.set(cache_key, result, ttl_seconds=3600)
                return result
        except asyncio.TimeoutError:
            logger.error("Anthropic API call timed out after 30 seconds")
            raise
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}", exc_info=True)
            raise

    def _parse_first_json(self, text: str) -> Any:
        """Attempt to parse the first valid JSON object or array from text."""
        import re
        # Try to find JSON array first
        if "[" in text:
            start = text.find("[")
            depth = 0
            for i, c in enumerate(text[start:], start):
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except:
                            break
        # Try to find JSON object
        if "{" in text:
            start = text.find("{")
            depth = 0
            for i, c in enumerate(text[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except:
                            break
        return {}

    def _extract_json(self, text: str) -> str:
        cleaned = text.strip()
        # Remove markdown code blocks
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                # Skip first line (```json) and last line (```)
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                cleaned = "\n".join(lines)
            else:
                cleaned = cleaned.strip("`")
        # Find JSON array
        if "[" in cleaned:
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1 and end > start:
                return cleaned[start:end + 1]
        # Find JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]
        return cleaned

    async def _load_or_create_context(
        self,
        session: Optional[PlanningSession],
        user_id: Optional[UUID],
        db: AsyncSession,
    ) -> ConversationContext:
        """Load conversation context from session or create new one."""
        context = ConversationContext()
        
        # Try to load from session if available
        if session and hasattr(session, 'conversation_context'):
            try:
                if isinstance(session.conversation_context, dict):
                    # Reconstruct from stored dict
                    context = ConversationContext(**session.conversation_context)
            except Exception as e:
                logger.warning(f"Failed to load context from session: {e}")
        
        # Load user preferences if available
        if user_id:
            try:
                user_context_service = get_user_context_service()
                user_prefs = await user_context_service.get_user_preferences(
                    user_id=user_id,
                    db=db,
                )
                if user_prefs:
                    context.user_preferences = user_prefs
            except Exception as e:
                logger.warning(f"Failed to load user preferences for context: {e}")
        
        return context

    async def _extract_entities(
        self,
        intent: IntentObject,
        request: ChatRequest,
        context: ConversationContext,
    ) -> None:
        """Extract entities from intent and update context."""
        # Extract location entities
        if intent.hard_constraints.start.type == "point" and isinstance(intent.hard_constraints.start.value, Coordinate):
            context.entities["start_location"] = intent.hard_constraints.start.value.model_dump()
        elif intent.hard_constraints.start.type == "place" and isinstance(intent.hard_constraints.start.value, str):
            context.entities["start_place"] = intent.hard_constraints.start.value
        
        if intent.hard_constraints.end.type == "point" and isinstance(intent.hard_constraints.end.value, Coordinate):
            context.entities["end_location"] = intent.hard_constraints.end.value.model_dump()
        elif intent.hard_constraints.end.type == "place" and isinstance(intent.hard_constraints.end.value, str):
            context.entities["end_place"] = intent.hard_constraints.end.value
        
        # Extract sport type
        if intent.hard_constraints.discipline and intent.hard_constraints.discipline != "any":
            context.sport_type = intent.hard_constraints.discipline
        
        # Extract discussed topics from request message
        message_lower = request.message.lower()
        topics = []
        if any(word in message_lower for word in ["scenic", "view", "beautiful", "landscape"]):
            topics.append("scenery")
        if any(word in message_lower for word in ["safe", "traffic", "quiet", "low traffic"]):
            topics.append("safety")
        if any(word in message_lower for word in ["difficult", "challenging", "hard", "technical"]):
            topics.append("difficulty")
        if any(word in message_lower for word in ["easy", "beginner", "casual"]):
            topics.append("difficulty")
        
        for topic in topics:
            if topic not in context.discussed_topics:
                context.discussed_topics.append(topic)
        
        # Extract trail/route names mentioned in request (simple pattern matching)
        import re
        # Look for capitalized words that might be trail names
        trail_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:trail|route|loop|path)'
        trail_matches = re.findall(trail_pattern, request.message)
        for match in trail_matches:
            if match not in context.entities.get("trail_names", []):
                if "trail_names" not in context.entities:
                    context.entities["trail_names"] = []
                context.entities["trail_names"].append(match)


_ride_brief_service: Optional[RideBriefLoopService] = None


async def get_ride_brief_service() -> RideBriefLoopService:
    global _ride_brief_service
    if _ride_brief_service is None:
        _ride_brief_service = RideBriefLoopService()
    return _ride_brief_service
