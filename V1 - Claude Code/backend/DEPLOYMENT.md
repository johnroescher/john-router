# Deployment Guide

## Enhanced Route Planning System Deployment

This guide covers deployment of the enhanced route planning system with all new features.

## Prerequisites

- Docker and Docker Compose
- PostgreSQL 15+ with PostGIS 3.3+ and pgvector extension
- Redis 7+
- API Keys:
  - Anthropic Claude API key
  - OpenRouteService API key
  - OpenAI API key (for embeddings, optional)
  - Trailforks API key (optional)

## Database Setup

### 1. Enable Extensions

The system requires PostgreSQL extensions:
- PostGIS
- pg_trgm
- **pgvector** (new)

Ensure your PostgreSQL image supports pgvector. The `docker/init-db.sql` script enables it automatically.

### 2. Run Migrations

The new tables are created via `docker/init-db.sql` on first startup. For existing databases:

```bash
# Apply new schema
psql -U johnrouter -d johnrouter -f docker/init-db.sql
```

### 3. Seed Initial Data

```bash
# Seed location knowledge for pilot locations
python backend/scripts/seed_location_knowledge.py

# Ingest initial knowledge chunks (requires OpenAI API key)
python backend/scripts/ingest_initial_knowledge.py
```

## Environment Variables

Add to `.env`:

```bash
# Existing
ANTHROPIC_API_KEY=your_key
ORS_API_KEY=your_key

# New
OPENAI_API_KEY=your_key  # For embeddings
TRAILFORKS_API_KEY=your_key  # Optional
REDIS_URL=redis://localhost:6379/0

# Feature Flags (optional, defaults to enabled)
FEATURE_USER_PREFERENCES=true
FEATURE_VECTOR_SEARCH=true
FEATURE_ROUTE_EVALUATION=true
# ... etc
```

## Docker Compose

The existing `docker-compose.yml` should work. Ensure:
- PostgreSQL image supports pgvector (postgis/postgis:15-3.3 should work)
- Redis is running
- All environment variables are set

## Celery Tasks

New Celery tasks are registered:
- `knowledge.ingest_trailforks` - Ingest Trailforks data
- `knowledge.ingest_location_knowledge` - Ingest location knowledge
- `prefetch.location_data` - Prefetch location data

Ensure Celery worker is running:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

## Feature Flags

Features can be toggled via environment variables or `backend/app/core/feature_flags.py`:

```python
# Disable a feature
FEATURE_EXTERNAL_APIS=false
```

## Monitoring

Monitor:
- Route evaluation logs in `route_evaluation_logs` table
- Cache hit rates (Redis)
- LLM token usage
- Performance metrics (response times)

## Rollback

If issues occur, disable features via feature flags:
```python
FEATURE_ROUTE_EVALUATION=false
FEATURE_ROUTE_IMPROVEMENT=false
```

The system will fall back to original behavior.
