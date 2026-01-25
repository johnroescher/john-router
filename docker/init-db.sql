-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    google_id VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    preferences JSONB DEFAULT '{
        "bike_type": "mtb",
        "fitness_level": "intermediate",
        "ftp": null,
        "typical_speed_mph": 12,
        "max_climb_tolerance_ft": 3000,
        "mtb_skill": "intermediate",
        "risk_tolerance": "medium",
        "surface_preferences": {"pavement": 0.2, "gravel": 0.3, "singletrack": 0.5},
        "avoidances": [],
        "units": "imperial"
    }'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Routes table
CREATE TABLE IF NOT EXISTS routes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    sport_type VARCHAR(50) NOT NULL DEFAULT 'mtb' CHECK (sport_type IN ('road', 'gravel', 'mtb', 'emtb')),
    geometry GEOMETRY(LineString, 4326),

    -- Computed stats
    distance_meters FLOAT,
    elevation_gain_meters FLOAT,
    elevation_loss_meters FLOAT,
    estimated_time_seconds INTEGER,
    max_elevation_meters FLOAT,
    min_elevation_meters FLOAT,

    -- Surface breakdown (percentages)
    surface_breakdown JSONB DEFAULT '{"pavement": 0, "gravel": 0, "dirt": 0, "singletrack": 0, "unknown": 100}'::jsonb,

    -- Difficulty ratings (0-5 scale)
    physical_difficulty FLOAT,
    technical_difficulty FLOAT,
    risk_rating FLOAT,
    overall_difficulty FLOAT,

    -- MTB-specific
    mtb_difficulty_breakdown JSONB DEFAULT '{"green": 0, "blue": 0, "black": 0, "double_black": 0, "unknown": 100}'::jsonb,

    -- Metadata
    tags TEXT[] DEFAULT '{}',
    is_public BOOLEAN DEFAULT false,
    confidence_score FLOAT DEFAULT 0,

    -- Validation
    validation_status VARCHAR(50) DEFAULT 'pending' CHECK (validation_status IN ('pending', 'valid', 'warnings', 'errors')),
    validation_results JSONB DEFAULT '{"errors": [], "warnings": [], "info": []}'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Route waypoints
CREATE TABLE IF NOT EXISTS route_waypoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id UUID REFERENCES routes(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    waypoint_type VARCHAR(50) NOT NULL DEFAULT 'via' CHECK (waypoint_type IN ('start', 'end', 'via', 'poi', 'coffee', 'water', 'restroom', 'viewpoint', 'bike_shop')),
    point GEOMETRY(Point, 4326) NOT NULL,
    name VARCHAR(255),
    lock_strength VARCHAR(20) DEFAULT 'soft' CHECK (lock_strength IN ('soft', 'hard')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Route segments (for detailed analysis)
CREATE TABLE IF NOT EXISTS route_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id UUID REFERENCES routes(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    geometry GEOMETRY(LineString, 4326) NOT NULL,
    source VARCHAR(50) DEFAULT 'router' CHECK (source IN ('router', 'manual', 'imported')),

    -- Segment stats
    distance_meters FLOAT,
    elevation_gain_meters FLOAT,
    elevation_loss_meters FLOAT,
    avg_grade FLOAT,
    max_grade FLOAT,
    min_grade FLOAT,

    -- Surface and type
    surface VARCHAR(100),
    highway_type VARCHAR(100),
    way_name VARCHAR(255),

    -- MTB ratings
    mtb_scale FLOAT,
    mtb_scale_uphill FLOAT,
    sac_scale VARCHAR(50),
    smoothness VARCHAR(50),
    tracktype VARCHAR(50),

    -- Access and legal
    bicycle_access VARCHAR(50) DEFAULT 'unknown',
    foot_access VARCHAR(50),

    -- Hazards
    hazards JSONB DEFAULT '[]'::jsonb,

    -- Confidence
    confidence_score FLOAT DEFAULT 0,
    data_completeness FLOAT DEFAULT 0,

    -- Raw OSM data
    osm_way_ids BIGINT[] DEFAULT '{}',
    osm_tags JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trail metadata cache (from OSM and other sources)
CREATE TABLE IF NOT EXISTS trail_metadata_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    osm_way_id BIGINT UNIQUE,
    external_id VARCHAR(255),
    external_source VARCHAR(100),
    geometry GEOMETRY(LineString, 4326),

    -- Core attributes
    name VARCHAR(255),
    surface VARCHAR(100),
    smoothness VARCHAR(50),
    tracktype VARCHAR(50),
    highway VARCHAR(100),

    -- MTB-specific
    mtb_scale FLOAT,
    mtb_scale_uphill FLOAT,
    mtb_description TEXT,
    sac_scale VARCHAR(50),

    -- Access
    access VARCHAR(50),
    bicycle VARCHAR(50),
    foot VARCHAR(50),

    -- Physical
    width FLOAT,
    incline VARCHAR(50),
    trail_visibility VARCHAR(50),

    -- Computed
    avg_grade FLOAT,
    max_grade FLOAT,

    -- Management
    operator VARCHAR(255),
    land_manager VARCHAR(255),

    -- Raw tags
    all_tags JSONB DEFAULT '{}'::jsonb,

    -- Freshness
    last_osm_update TIMESTAMP WITH TIME ZONE,
    last_verified TIMESTAMP WITH TIME ZONE,
    confidence_score FLOAT DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Research runs
CREATE TABLE IF NOT EXISTS research_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id UUID REFERENCES routes(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    query TEXT NOT NULL,
    bbox GEOMETRY(Polygon, 4326),
    time_window_days INTEGER DEFAULT 60,

    -- Results
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    citations JSONB DEFAULT '[]'::jsonb,
    extracted_facts JSONB DEFAULT '{
        "closures": [],
        "conditions": [],
        "hazards": [],
        "restrictions": []
    }'::jsonb,

    -- Metadata
    sources_checked INTEGER DEFAULT 0,
    execution_time_ms INTEGER,
    error_message TEXT,

    executed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chat conversations
CREATE TABLE IF NOT EXISTS chat_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    route_id UUID REFERENCES routes(id) ON DELETE SET NULL,

    messages JSONB DEFAULT '[]'::jsonb,

    -- Current state
    current_constraints JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Elevation cache (to reduce API calls)
CREATE TABLE IF NOT EXISTS elevation_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    point GEOMETRY(Point, 4326) NOT NULL,
    elevation_meters FLOAT NOT NULL,
    source VARCHAR(100) DEFAULT 'unknown',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create spatial indices
CREATE INDEX IF NOT EXISTS idx_routes_geometry ON routes USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_route_waypoints_point ON route_waypoints USING GIST (point);
CREATE INDEX IF NOT EXISTS idx_route_segments_geometry ON route_segments USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_trail_metadata_geometry ON trail_metadata_cache USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_research_runs_bbox ON research_runs USING GIST (bbox);
CREATE INDEX IF NOT EXISTS idx_elevation_cache_point ON elevation_cache USING GIST (point);

-- Text search indices
CREATE INDEX IF NOT EXISTS idx_routes_name_trgm ON routes USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_trail_metadata_name_trgm ON trail_metadata_cache USING GIN (name gin_trgm_ops);

-- User preferences table
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    location_region VARCHAR(100),
    sport_type VARCHAR(20),
    typical_distance_km FLOAT,
    preferred_surfaces JSONB,
    avoided_areas JSONB,
    favorite_trails JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Route history table
CREATE TABLE IF NOT EXISTS route_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    route_id UUID,
    sport_type VARCHAR(20),
    distance_km FLOAT,
    elevation_gain_m FLOAT,
    rating INTEGER,
    feedback_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Location knowledge table
CREATE TABLE IF NOT EXISTS location_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_region VARCHAR(100),
    sport_type VARCHAR(20),
    knowledge_type VARCHAR(50),
    name VARCHAR(255),
    description TEXT,
    geometry JSONB,
    metadata JSONB,
    confidence FLOAT,
    source VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Knowledge chunks table for RAG (with vector embeddings)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI ada-002 dimension, adjust if using different model
    metadata JSONB,
    source VARCHAR(100),
    location_region VARCHAR(100),
    sport_type VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding ON knowledge_chunks 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Foreign key indices
CREATE INDEX IF NOT EXISTS idx_routes_user_id ON routes (user_id);
CREATE INDEX IF NOT EXISTS idx_route_waypoints_route_id ON route_waypoints (route_id);
CREATE INDEX IF NOT EXISTS idx_route_segments_route_id ON route_segments (route_id);
CREATE INDEX IF NOT EXISTS idx_research_runs_route_id ON research_runs (route_id);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_id ON chat_conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences (user_id);
CREATE INDEX IF NOT EXISTS idx_user_preferences_region ON user_preferences (location_region);
CREATE INDEX IF NOT EXISTS idx_route_history_user_id ON route_history (user_id);
CREATE INDEX IF NOT EXISTS idx_route_history_route_id ON route_history (route_id);
CREATE INDEX IF NOT EXISTS idx_location_knowledge_region ON location_knowledge (location_region);
CREATE INDEX IF NOT EXISTS idx_location_knowledge_sport_type ON location_knowledge (sport_type);
CREATE INDEX IF NOT EXISTS idx_location_knowledge_type ON location_knowledge (knowledge_type);

-- Route evaluation logs table
CREATE TABLE IF NOT EXISTS route_evaluation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    route_id UUID,
    intent JSONB,
    initial_scores JSONB,
    final_scores JSONB,
    issues_found JSONB,
    improvements_made JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_route_evaluation_logs_user_id ON route_evaluation_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_route_evaluation_logs_route_id ON route_evaluation_logs (route_id);
CREATE INDEX IF NOT EXISTS idx_route_evaluation_logs_timestamp ON route_evaluation_logs (timestamp);

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_routes_updated_at BEFORE UPDATE ON routes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trail_metadata_updated_at BEFORE UPDATE ON trail_metadata_cache
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chat_conversations_updated_at BEFORE UPDATE ON chat_conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
