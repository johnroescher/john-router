# John Router

AI-powered cycling route builder for every kind of ride—road, gravel, mountain bike, urban adventures, bikepacking, and more.

## Overview

John Router is a chat-first route planning application that combines AI assistance with professional-grade map editing tools. It honors the diversity of cycling by providing deep, thoughtful analysis for every discipline—whether you seek technical singletrack, quiet backroads, smooth pavement, or urban exploration.

### Key Features

- **Chat-First Planning**: Describe your ideal ride in natural language and let AI generate optimized routes for your style of cycling
- **Every Ride Matters**: Comprehensive intelligence across all disciplines—MTB trail ratings, road traffic analysis, gravel surface quality, urban neighborhood character, bikepacking infrastructure
- **Professional Map Editor**: Drag routes, lock segments, set avoidance areas, manual waypoint control—accessible to beginners, powerful for experts
- **Data-Dense Analysis**: Elevation profiles, surface breakdowns, grade analysis, time estimates, confidence scores—tailored to your cycling discipline
- **Multi-Discipline Support**: Road, Gravel, MTB, eMTB, Urban, Bikepacking, Endurance routing profiles
- **Quality Mode**: Multi-step pipeline generating multiple candidates with full validation across all cycling contexts

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend                                 │
│  Next.js 14 • TypeScript • MapLibre GL JS • MUI • Zustand      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API                                 │
│              FastAPI • Python 3.11 • Async                      │
├─────────────────────────────────────────────────────────────────┤
│  Services:                                                       │
│  • Routing (OpenRouteService)    • Analysis (elevation, surface)│
│  • AI Copilot (Claude)           • Validation (connectivity)    │
│  • Export (GPX)                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│   PostgreSQL     │ │    Redis     │ │   Celery     │
│    + PostGIS     │ │    Cache     │ │   Workers    │
└──────────────────┘ └──────────────┘ └──────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenRouteService API key (free at https://openrouteservice.org)
- Anthropic API key (for AI features)

### Setup

1. **Clone and configure environment**

```bash
cd "V1 - Claude Code"
cp .env.example .env
```

2. **Edit `.env` with your API keys**

```env
# Required
ORS_API_KEY=your_openrouteservice_key
ANTHROPIC_API_KEY=your_anthropic_key

# Optional
MAPBOX_ACCESS_TOKEN=your_mapbox_token  # For satellite imagery
```

3. **Start with Docker Compose**

```bash
docker-compose up -d
```

4. **Access the application**

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Development Setup

For local development without Docker:

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `ORS_API_KEY` | OpenRouteService API key for routing |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI copilot |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `MAPBOX_ACCESS_TOKEN` | - | Mapbox token for satellite tiles |
| `SECRET_KEY` | auto-generated | JWT signing key |
| `DEBUG` | false | Enable debug mode |
| `ORS_BASE_URL` | https://api.openrouteservice.org | ORS API endpoint |
| `QUALITY_MODE_DEFAULT` | true | Enable quality mode by default |
| `MAX_ROUTE_CANDIDATES` | 3 | Candidates to generate in quality mode |

## API Overview

### Routes

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/routes/generate` | POST | Generate a new route |
| `/api/routes/{id}` | GET | Get route details |
| `/api/routes/analyze` | POST | Analyze route geometry |
| `/api/routes/validate` | POST | Validate route constraints |
| `/api/routes/export/gpx` | POST | Export route as GPX |

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/message` | POST | Send message to AI copilot |
| `/api/chat/conversations/{id}` | GET | Get conversation history |

### Geocoding

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/geocode` | GET | Forward geocode address |
| `/api/geocode/reverse` | GET | Reverse geocode coordinates |

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/routes/        # API endpoints
│   │   ├── core/              # Config, security
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   └── services/          # Business logic
│   │       ├── routing.py     # ORS integration
│   │       ├── analysis.py    # Route analysis
│   │       ├── validation.py  # Route validation
│   │       └── ai_copilot.py  # Claude integration
│   ├── scripts/
│   │   └── seed_data.py       # Example routes
│   └── tests/                 # Test suite
│
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js pages
│   │   ├── components/        # React components
│   │   │   ├── chat/          # Chat interface
│   │   │   ├── controls/      # Route controls
│   │   │   ├── inspector/     # Route inspector
│   │   │   └── map/           # Map components
│   │   ├── stores/            # Zustand stores
│   │   ├── lib/               # Utilities
│   │   └── types/             # TypeScript types
│   └── public/                # Static assets
│
├── docker/
│   └── init-db.sql            # Database schema
│
├── docker-compose.yml
└── .env.example
```

## AI Copilot Tools

The AI copilot has access to these tools for route planning:

| Tool | Description |
|------|-------------|
| `geocode` | Convert address/place name to coordinates |
| `reverse_geocode` | Convert coordinates to place name |
| `search_places` | Find POIs near coordinates |
| `generate_route` | Generate route with constraints |
| `analyze_route` | Get detailed route analysis |
| `validate_route` | Check route against constraints |
| `apply_avoidance` | Add area to avoid |
| `export_gpx` | Export route to GPX format |

## Route Analysis

### Surface Breakdown

Routes are analyzed for surface types:
- **Pavement**: asphalt, concrete, paved
- **Gravel**: gravel, fine_gravel, compacted
- **Dirt**: dirt, earth, ground
- **Singletrack**: path, trail (narrow)

### MTB Difficulty Mapping

OSM mtb:scale values mapped to trail ratings:

| mtb:scale | Rating | Description |
|-----------|--------|-------------|
| 0 | Green | Easy, smooth |
| 1 | Blue | Intermediate |
| 2 | Black | Difficult, technical |
| 3+ | Double Black | Expert only |

### Validation Checks

- **Connectivity**: No gaps > 500m in route
- **Legality**: Bicycle access allowed on all segments
- **Safety**: Grade limits, traffic levels
- **Difficulty**: Matches user skill level

## Testing

```bash
# Backend tests
cd backend
pytest

# With coverage
pytest --cov=app --cov-report=html

# Frontend tests
cd frontend
npm test
```

## Seed Data

Load example routes:

```bash
cd backend
python scripts/seed_data.py
```

Includes 5 example routes:
- Golden Gate Canyon Loop (MTB, Colorado)
- Marin Headlands Gravel Epic (Bay Area)
- Moab Slickrock Trail (Expert MTB, Utah)
- Boulder Road Climbing Loop (Road, Colorado)
- Bentonville Flow Trails (Beginner MTB, Arkansas)

## Design Principles

### Quality Over Speed

- Never hallucinate route geometry or conditions
- Generate multiple candidates, validate all, present best options
- Explain AI decisions and cite data sources
- Allow manual override of any AI decision

### Every Cycling Discipline Deserves Excellence

- All disciplines treated with equal depth and care
- MTB: Trail difficulty ratings, technical features, flow analysis
- Road: Traffic levels, pavement quality, bike infrastructure
- Gravel: Surface composition, quality assessment, tire suitability
- Urban: Neighborhood character, stress levels, cultural points of interest
- Bikepacking: Infrastructure spacing, water/camping access
- No discipline is an afterthought

### Data Transparency

- Show confidence levels on all derived data
- Cite sources for conditions/closures
- Clear distinction between OSM data vs. estimates
- Research credibility scoring (official > trail_org > community)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- OpenRouteService for routing API
- OpenStreetMap contributors for map data
- MapLibre for open-source mapping
- Anthropic for Claude AI
