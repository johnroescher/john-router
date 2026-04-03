/**
 * API client for John Router backend
 */
import axios, { AxiosInstance } from 'axios';
import type {
  Route,
  RouteConstraints,
  RouteCandidate,
  RouteAnalysis,
  RouteValidation,
  ChatRequest,
  ChatResponse,
  StatusUpdate,
  CyclingFactsResponse,
  User,
  UserPreferences,
  SurfaceMatchResponse,
} from '@/types';
import { normalizeSurfaceBreakdown } from '@/lib/surfaceMix';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ROUTE_TRACE_ENABLED = (process.env.NEXT_PUBLIC_ROUTE_TRACE ?? 'true') !== 'false';

const logRouteTrace = (level: 'debug' | 'info' | 'warn' | 'error', message: string, data?: Record<string, unknown>) => {
  if (!ROUTE_TRACE_ENABLED) return;
  const payload = { message, ...data };
  console[level](`[route-trace] ${message}`, payload);
};

const createRequestId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const isUuid = (value?: string | null) => {
  if (!value) return false;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
};

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: `${API_URL}/api`,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 35000,
    });
    if (process.env.NODE_ENV === 'development') {
      console.log('[ApiClient] baseURL', this.client.defaults.baseURL);
      this.client.interceptors.request.use((config) => {
        console.log('[ApiClient] request', {
          method: config.method,
          url: config.url,
          baseURL: config.baseURL,
        });
        return config;
      });
    }
  }

  setAuthToken(token: string | null) {
    if (token) {
      this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete this.client.defaults.headers.common['Authorization'];
    }
  }

  // Health
  async healthCheck() {
    const response = await this.client.get('/health');
    return response.data;
  }

  // Routes
  async listRoutes(params?: {
    sportType?: string;
    tags?: string[];
    skip?: number;
    limit?: number;
  }) {
    const response = await this.client.get('/routes', { params });
    return (response.data as any[]).map((route) => this.routeFromApi(route));
  }

  async getRoute(routeId: string) {
    const response = await this.client.get(`/routes/${routeId}`);
    return this.routeFromApi(response.data);
  }

  async createRoute(route: {
    name: string;
    description?: string;
    sportType: string;
    geometry: { type: 'LineString'; coordinates: number[][] };
    tags?: string[];
    isPublic?: boolean;
  }) {
    const response = await this.client.post('/routes', route);
    return this.routeFromApi(response.data);
  }

  async updateRoute(routeId: string, updates: Partial<Route>) {
    const response = await this.client.put(`/routes/${routeId}`, updates);
    return this.routeFromApi(response.data);
  }

  async deleteRoute(routeId: string) {
    await this.client.delete(`/routes/${routeId}`);
  }

  async generateRoutes(constraints: RouteConstraints) {
    const response = await this.client.post('/routes/generate', this.constraintsToApi(constraints));
    return (response.data as any[]).map((candidate) => this.routeCandidateFromApi(candidate));
  }

  async analyzeRoute(routeId: string) {
    const response = await this.client.get(`/routes/${routeId}/analyze`);
    return response.data as RouteAnalysis;
  }

  async analyzeGeometry(geometry: { type: 'LineString'; coordinates: number[][] }) {
    const response = await this.client.post('/routes/analyze-geometry', { geometry });
    return this.routeAnalysisFromApi(response.data);
  }

  async surfaceMatch(geometry: { type: 'LineString'; coordinates: number[][] }) {
    const response = await this.client.post('/routes/surface-match', { geometry });
    return response.data as SurfaceMatchResponse;
  }

  async validateRoute(routeId: string) {
    const response = await this.client.get(`/routes/${routeId}/validate`);
    return response.data as RouteValidation;
  }

  async exportGpx(routeId: string) {
    const response = await this.client.get(`/routes/${routeId}/export/gpx`, {
      responseType: 'blob',
    });
    return response.data as Blob;
  }

  async getCyclingFacts(count: number = 6) {
    const response = await this.client.get('/facts/cycling', { params: { count } });
    return response.data as CyclingFactsResponse;
  }

  async importGpx(file: File, name?: string, sportType?: string) {
    const formData = new FormData();
    formData.append('file', file);
    if (name) formData.append('name', name);
    if (sportType) formData.append('sport_type', sportType);

    const response = await this.client.post('/routes/import/gpx', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async routePointToPoint(coordinates: { lat: number; lng: number }[], sportType: string = 'mtb') {
    const startedAt = Date.now();
    const requestId = createRequestId();
    try {
      logRouteTrace('info', 'routePointToPoint start', {
        requestId,
        sportType,
        pointCount: coordinates.length,
        start: coordinates[0],
        end: coordinates[coordinates.length - 1],
      });
      const response = await this.client.post('/routes/point-to-point', {
        coordinates: coordinates.map(c => ({ lat: c.lat, lng: c.lng })),
        sport_type: sportType,
      }, {
        headers: {
          'X-Request-Id': requestId,
        },
      });
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/289a778b-ae89-4d23-bfca-5fa553683dd9',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId:'debug-session',runId:'pre-fix',hypothesisId:'H1',location:'api.ts:129',message:'routePointToPoint success',data:{status:response.status,elapsedMs:Date.now()-startedAt,pointCount:coordinates.length,sportType},timestamp:Date.now()})}).catch(()=>{});
      // #endregion agent log
      logRouteTrace('info', 'routePointToPoint success', {
        requestId,
        status: response.status,
        elapsedMs: Date.now() - startedAt,
        pointCount: coordinates.length,
        sportType,
        degraded: response.data?.degraded ?? false,
        degradedReason: response.data?.degraded_reason ?? null,
      });
      return response.data as {
        geometry: { type: 'LineString'; coordinates: number[][] };
        distance_meters: number;
        duration_seconds: number;
        elevation_gain: number;
        surface_breakdown: {
          paved: number;
          unpaved: number;
          gravel: number;
          ground: number;
          unknown: number;
        };
        degraded?: boolean;
        degraded_reason?: string | null;
      };
    } catch (error) {
      const err = error as any;
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/289a778b-ae89-4d23-bfca-5fa553683dd9',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId:'debug-session',runId:'pre-fix',hypothesisId:'H1',location:'api.ts:140',message:'routePointToPoint error',data:{status:err?.response?.status ?? null,elapsedMs:Date.now()-startedAt,pointCount:coordinates.length,sportType,message:err?.message ?? String(error)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion agent log
      logRouteTrace('error', 'routePointToPoint error', {
        requestId,
        status: err?.response?.status ?? null,
        elapsedMs: Date.now() - startedAt,
        pointCount: coordinates.length,
        sportType,
        message: err?.message ?? String(error),
      });
      throw error;
    }
  }

  // Chat
  async sendMessage(request: ChatRequest) {
    const requestId = createRequestId();
    const response = await this.client.post('/chat/message', {
      message: request.message,
      conversation_id: isUuid(request.conversationId) ? request.conversationId : undefined,
      route_id: isUuid(request.routeId) ? request.routeId : undefined,
      current_constraints: request.currentConstraints
        ? this.constraintsToApi(request.currentConstraints as RouteConstraints)
        : undefined,
      current_route_geometry: request.currentRouteGeometry,
      map_center: request.mapCenter,
      quality_mode: true,
      explain_mode: true,
    }, {
      headers: {
        'X-Request-Id': requestId,
      },
    });
    return this.chatResponseFromApi(response.data);
  }

  async sendMessageStream(
    request: ChatRequest,
    onStatus: (status: StatusUpdate) => void
  ): Promise<ChatResponse> {
    const requestId = createRequestId();
    const url = `${this.client.defaults.baseURL}/chat/message/stream`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': requestId,
        ...(this.client.defaults.headers.common['Authorization'] && {
          'Authorization': this.client.defaults.headers.common['Authorization'] as string,
        }),
      },
      body: JSON.stringify({
        message: request.message,
        conversation_id: isUuid(request.conversationId) ? request.conversationId : undefined,
        route_id: isUuid(request.routeId) ? request.routeId : undefined,
        current_constraints: request.currentConstraints
          ? this.constraintsToApi(request.currentConstraints as RouteConstraints)
          : undefined,
        current_route_geometry: request.currentRouteGeometry,
        map_center: request.mapCenter,
        quality_mode: true,
        explain_mode: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResponse: ChatResponse | null = null;

    if (!reader) {
      throw new Error('Response body is not readable');
    }

    while (true) {
      const { done, value } = await reader.read();
      
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) {
          continue;
        }

        let data: any;
        try {
          data = JSON.parse(line.slice(6));
        } catch (e) {
          console.error('Error parsing SSE event:', e, line);
          continue;
        }

        if (data.type === 'status' && data.data) {
          const status: StatusUpdate = {
            stage: data.data.stage,
            message: data.data.message,
            progress: data.data.progress,
            timestamp: data.data.timestamp,
          };
          onStatus(status);
        } else if (data.type === 'response' && data.data) {
          finalResponse = this.chatResponseFromApi(data.data);
        } else if (data.type === 'error' && data.data) {
          throw new Error(data.data.message || 'Unknown error');
        }
      }
    }

    if (!finalResponse) {
      throw new Error('No response received from stream');
    }

    return finalResponse;
  }

  async getConversations(skip?: number, limit?: number) {
    const response = await this.client.get('/chat/conversations', {
      params: { skip, limit },
    });
    return response.data;
  }

  async getConversation(conversationId: string) {
    const response = await this.client.get(`/chat/conversations/${conversationId}`);
    return response.data;
  }

  // Users
  async register(email: string, password: string, name?: string) {
    const response = await this.client.post('/users/register', {
      email,
      password,
      name,
    });
    return response.data as User;
  }

  async login(email: string, password: string) {
    const params = new URLSearchParams();
    params.append('username', email);
    params.append('password', password);

    const response = await this.client.post('/users/token', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return response.data as { access_token: string; token_type: string; expires_in: number };
  }

  async getCurrentUser() {
    const response = await this.client.get('/users/me');
    return response.data as User;
  }

  async updateUser(updates: { name?: string; preferences?: UserPreferences }) {
    const response = await this.client.put('/users/me', updates);
    return response.data as User;
  }

  async getPreferences() {
    const response = await this.client.get('/users/preferences');
    return response.data as UserPreferences;
  }

  async updatePreferences(preferences: UserPreferences) {
    const response = await this.client.put('/users/preferences', preferences);
    return response.data as UserPreferences;
  }

  // Helper methods for API conversion
  private constraintsToApi(constraints: RouteConstraints) {
    return {
      start: constraints.start,
      end: constraints.end,
      route_type: constraints.routeType,
      via_points: constraints.viaPoints,
      avoid_areas: constraints.avoidAreas,
      sport_type: constraints.sportType,
      routing_service: constraints.routingService,
      routing_profile: constraints.routingProfile,
      target_distance_meters: constraints.targetDistanceMeters,
      min_distance_meters: constraints.minDistanceMeters,
      max_distance_meters: constraints.maxDistanceMeters,
      distance_hard_constraint: constraints.distanceHardConstraint,
      target_time_seconds: constraints.targetTimeSeconds,
      time_hard_constraint: constraints.timeHardConstraint,
      target_elevation_gain_meters: constraints.targetElevationGainMeters,
      max_elevation_gain_meters: constraints.maxElevationGainMeters,
      elevation_hard_constraint: constraints.elevationHardConstraint,
      climb_emphasis: constraints.climbEmphasis,
      surface_preferences: constraints.surfacePreferences,
      allow_hike_a_bike: constraints.allowHikeABike,
      prefer_bike_lanes: constraints.preferBikeLanes,
      prefer_designated_mtb_trails: constraints.preferDesignatedMtbTrails,
      mtb_difficulty_target: constraints.mtbDifficultyTarget,
      max_downhill_grade_percent: constraints.maxDownhillGradePercent,
      max_uphill_grade_percent: constraints.maxUphillGradePercent,
      mtb_features: {
        flow: constraints.mtbFeatures.flow,
        berms: constraints.mtbFeatures.berms,
        jumps: constraints.mtbFeatures.jumps,
        drops: constraints.mtbFeatures.drops,
        rock_gardens: constraints.mtbFeatures.rockGardens,
        roots: constraints.mtbFeatures.roots,
        technical_climbs: constraints.mtbFeatures.technicalClimbs,
        chunk: constraints.mtbFeatures.chunk,
      },
      hazard_avoidances: {
        exposure: constraints.hazardAvoidances.exposure,
        cliff_edges: constraints.hazardAvoidances.cliffEdges,
        loose_terrain: constraints.hazardAvoidances.looseTerrain,
        water_crossings: constraints.hazardAvoidances.waterCrossings,
        high_speed_road_crossings: constraints.hazardAvoidances.highSpeedRoadCrossings,
        night_unsafe: constraints.hazardAvoidances.nightUnsafe,
      },
      avoid_highways: constraints.avoidHighways,
      avoid_unpaved_when_road: constraints.avoidUnpavedWhenRoad,
      avoid_private: constraints.avoidPrivate,
      require_bicycle_legal: constraints.requireBicycleLegal,
      quality_mode: constraints.qualityMode,
      num_alternatives: constraints.numAlternatives,
    };
  }

  private chatResponseFromApi(data: any): ChatResponse {
    return {
      conversationId: data.conversation_id,
      message: {
        role: data.message.role,
        content: data.message.content,
        timestamp: data.message.timestamp,
        toolCalls: data.message.tool_calls,
        actionChips: data.message.action_chips?.map((c: any) => ({
          id: c.id,
          label: c.label,
          action: c.action,
          data: c.data,
        })),
        confidence: data.message.confidence,
      },
      routeId: data.route_id,
      routeUpdated: data.route_updated,
      routeDiff: data.route_diff,
      routeData: data.route_data,
      suggestedPrompts: data.suggested_prompts,
      planning: data.planning,
      routeCandidates: data.route_candidates
        ? data.route_candidates.map((candidate: any) => this.routeCandidateFromApi(candidate))
        : undefined,
      needsClarification: data.needs_clarification,
      clarificationQuestion: data.clarification_question,
      planningMeta: data.planning_meta,
    };
  }

  private routeCandidateFromApi(data: any): RouteCandidate {
    return {
      route: this.routeFromApi(data.route),
      analysis: this.routeAnalysisFromApi(data.analysis),
      validation: this.routeValidationFromApi(data.validation),
      rank: data.rank,
      explanation: data.explanation,
      tradeoffs: data.tradeoffs || {},
      routerUsed: data.router_used ?? undefined,
      surfaceSource: data.surface_source ?? undefined,
      fallbackReason: data.fallback_reason ?? undefined,
    };
  }

  private routeFromApi(data: any): Route {
    return {
      id: data.id,
      userId: data.user_id ?? undefined,
      name: data.name,
      description: data.description ?? undefined,
      sportType: data.sport_type,
      geometry: data.geometry ?? undefined,
      distanceMeters: data.distance_meters ?? undefined,
      elevationGainMeters: data.elevation_gain_meters ?? undefined,
      elevationLossMeters: data.elevation_loss_meters ?? undefined,
      estimatedTimeSeconds: data.estimated_time_seconds ?? undefined,
      maxElevationMeters: data.max_elevation_meters ?? undefined,
      minElevationMeters: data.min_elevation_meters ?? undefined,
      surfaceBreakdown: normalizeSurfaceBreakdown(data.surface_breakdown),
      mtbDifficultyBreakdown: data.mtb_difficulty_breakdown || {
        green: 0,
        blue: 0,
        black: 0,
        double_black: 0,
        unknown: 100,
      },
      physicalDifficulty: data.physical_difficulty ?? undefined,
      technicalDifficulty: data.technical_difficulty ?? undefined,
      riskRating: data.risk_rating ?? undefined,
      overallDifficulty: data.overall_difficulty ?? undefined,
      tags: data.tags || [],
      isPublic: data.is_public ?? false,
      confidenceScore: data.confidence_score ?? 0,
      validationStatus: data.validation_status ?? 'pending',
      validationResults: this.routeValidationFromApi(
        data.validation_results || {
          status: data.validation_status,
          errors: [],
          warnings: [],
          info: [],
          confidence_score: data.confidence_score,
        }
      ),
      waypoints: (data.waypoints || []).map((waypoint: any) => ({
        id: waypoint.id,
        idx: waypoint.idx,
        waypointType: waypoint.waypoint_type,
        point: waypoint.point,
        name: waypoint.name ?? undefined,
        lockStrength: waypoint.lock_strength,
      })),
      createdAt: data.created_at ?? new Date().toISOString(),
      updatedAt: data.updated_at ?? new Date().toISOString(),
    };
  }

  private routeAnalysisFromApi(data: any): RouteAnalysis {
    return {
      distanceMeters: data.distance_meters,
      elevationGainMeters: data.elevation_gain_meters,
      elevationLossMeters: data.elevation_loss_meters,
      estimatedTimeSeconds: data.estimated_time_seconds,
      maxElevationMeters: data.max_elevation_meters,
      minElevationMeters: data.min_elevation_meters,
      avgGradePercent: data.avg_grade_percent,
      maxGradePercent: data.max_grade_percent,
      longestClimbMeters: data.longest_climb_meters,
      steepest100mPercent: data.steepest_100m_percent,
      steepest1kmPercent: data.steepest_1km_percent,
      climbingAbove8PercentMeters: data.climbing_above_8_percent_meters,
      surfaceBreakdown: normalizeSurfaceBreakdown(data.surface_breakdown),
      mtbDifficultyBreakdown: data.mtb_difficulty_breakdown,
      maxTechnicalRating: data.max_technical_rating ?? undefined,
      hikeABikeSections: data.hike_a_bike_sections,
      hikeABikeDistanceMeters: data.hike_a_bike_distance_meters,
      physicalDifficulty: data.physical_difficulty,
      technicalDifficulty: data.technical_difficulty,
      riskRating: data.risk_rating,
      overallDifficulty: data.overall_difficulty,
      elevationProfile: (data.elevation_profile || []).map((point: any) => ({
        distanceMeters: point.distance_meters,
        elevationMeters: point.elevation_meters,
        gradePercent: point.grade_percent,
        coordinate: point.coordinate,
      })),
      confidenceScore: data.confidence_score,
      dataCompleteness: data.data_completeness,
    };
  }

  private routeValidationFromApi(data: any): RouteValidation {
    return {
      status: data.status || 'valid',
      errors: (data.errors || []).map((issue: any) => ({
        type: issue.type,
        severity: issue.severity,
        message: issue.message,
        segmentIdx: issue.segment_idx ?? undefined,
        location: issue.location ?? undefined,
        fixSuggestion: issue.fix_suggestion ?? undefined,
      })),
      warnings: (data.warnings || []).map((issue: any) => ({
        type: issue.type,
        severity: issue.severity,
        message: issue.message,
        segmentIdx: issue.segment_idx ?? undefined,
        location: issue.location ?? undefined,
        fixSuggestion: issue.fix_suggestion ?? undefined,
      })),
      info: (data.info || []).map((issue: any) => ({
        type: issue.type,
        severity: issue.severity,
        message: issue.message,
        segmentIdx: issue.segment_idx ?? undefined,
        location: issue.location ?? undefined,
        fixSuggestion: issue.fix_suggestion ?? undefined,
      })),
      confidenceScore: data.confidence_score ?? 0,
    };
  }

}

export const api = new ApiClient();
