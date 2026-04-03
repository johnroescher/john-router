# Architecture Documentation

## Enhanced Chat-Based Route Planning System

This document describes the architecture of the enhanced route planning system with AI-powered features.

## System Overview

The system extends the original 6-phase Ride Brief Loop with additional intelligence layers:

1. **Context Intelligence** - User preferences, conversation memory, location knowledge
2. **External Knowledge Integration (RAG)** - Vector search, external APIs
3. **Creative Route Generation** - Multiple strategies, named routes
4. **Intelligent Evaluation & Refinement** - Self-critique and improvement loop
5. **Conversational Excellence** - Natural language, proactive suggestions
6. **Performance Optimization** - Caching, parallel processing, prefetching

## Core Components

### User Context System

**Files:**
- `backend/app/services/user_context.py` - UserContextService
- `backend/app/models/user_context.py` - UserPreference, RouteHistory models
- `backend/app/schemas/user_context.py` - UserPreferences, RouteFeedback schemas

**Purpose:** Remembers user preferences and learns from route history to personalize planning.

**Key Methods:**
- `get_user_preferences()` - Retrieve preferences by user and location
- `update_preferences_from_route()` - Learn from completed routes

### Location Knowledge System

**Files:**
- `backend/app/services/location_knowledge.py` - LocationKnowledgeService
- `backend/app/models/location_knowledge.py` - LocationKnowledge model
- `backend/app/schemas/knowledge.py` - AreaInsights, NamedRoute schemas

**Purpose:** Provides local cycling knowledge (famous routes, trail systems, local tips).

**Key Methods:**
- `get_area_insights()` - Get local knowledge for an area
- `suggest_named_routes()` - Find famous routes matching constraints

### Knowledge Retrieval (RAG)

**Files:**
- `backend/app/services/knowledge_retrieval.py` - KnowledgeRetrievalService
- `backend/app/models/knowledge_chunk.py` - KnowledgeChunk model
- `backend/app/services/external_apis/trailforks.py` - Trailforks API integration

**Purpose:** Retrieves relevant knowledge using vector similarity search and external APIs.

**Key Methods:**
- `retrieve_knowledge()` - Semantic search for relevant knowledge chunks
- `_vector_search()` - pgvector similarity search
- `_retrieve_from_external_apis()` - Fetch from Trailforks, etc.

### Route Strategy System

**Files:**
- `backend/app/services/route_strategies.py` - RouteStrategy base and implementations
- `backend/app/services/named_routes.py` - NamedRouteService

**Purpose:** Generates diverse route types (Explorer, Classic, Hidden Gem).

**Strategies:**
- `ExplorerStrategy` - Exploration-focused routes
- `ClassicStrategy` - Well-known, popular routes
- `HiddenGemStrategy` - Lesser-known but excellent routes

### Route Evaluation & Improvement

**Files:**
- `backend/app/services/route_evaluator.py` - RouteEvaluator
- `backend/app/services/route_improver.py` - RouteImprover
- `backend/app/schemas/evaluation.py` - Evaluation schemas
- `backend/app/models/route_evaluation.py` - RouteEvaluationLog model

**Purpose:** Self-critique and improvement loop for routes.

**Key Methods:**
- `evaluate_route_against_intent()` - Evaluate route quality and intent match
- `improve_route()` - Automatically improve routes based on evaluation
- `improve_and_reevaluate()` - Iterative improvement with re-evaluation

### Conversational Features

**Files:**
- `backend/app/services/response_generator.py` - ResponseGenerator
- `backend/app/services/conversation_agent.py` - ConversationAgent
- `backend/app/services/route_modifier.py` - RouteModifier

**Purpose:** Natural language responses, proactive suggestions, route modifications.

## Data Flow

```
User Request
    ↓
Intent Extraction (with user preferences + knowledge)
    ↓
Ride Brief Expansion (with location knowledge)
    ↓
Discovery Plan (using external knowledge)
    ↓
Trail Discovery (cached OSM queries)
    ↓
Route Generation (multiple strategies in parallel)
    ↓
Evaluation & Improvement Loop
    ↓
Critique & Selection
    ↓
Response Generation (natural language + suggestions)
    ↓
User Response
```

## Database Schema

### New Tables

- `user_preferences` - User preferences by region
- `route_history` - Completed route logs
- `location_knowledge` - Local cycling knowledge
- `knowledge_chunks` - Vector embeddings for RAG
- `route_evaluation_logs` - Evaluation analytics

## Feature Flags

Features can be enabled/disabled via `backend/app/core/feature_flags.py`:
- `user_preferences`
- `location_knowledge`
- `vector_search`
- `external_apis`
- `route_strategies`
- `route_evaluation`
- `route_improvement`
- `clarification_questions`
- `response_generation`
- `proactive_suggestions`
- `caching`
- `parallel_processing`
- `prefetching`

## Performance Optimizations

1. **Caching:** OSM queries (24h TTL), knowledge retrieval (1h TTL), LLM responses (1h TTL)
2. **Parallel Processing:** Candidate evaluation, route improvement, knowledge retrieval
3. **Prefetching:** Background prefetch of trail data and knowledge for user location

## External Dependencies

- PostgreSQL with PostGIS and pgvector
- Redis for caching
- Anthropic Claude API
- OpenRouteService API
- Trailforks API (optional)
- OpenAI API (for embeddings, optional)
