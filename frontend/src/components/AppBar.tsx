'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AppBar as MuiAppBar,
  Toolbar,
  Typography,
  Box,
  Button,
  IconButton,
  TextField,
  InputAdornment,
  Menu,
  MenuItem,
  Avatar,
  CircularProgress,
  Paper,
  List,
  ListItemButton,
  ListItemText,
  ClickAwayListener,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import FileUploadIcon from '@mui/icons-material/FileUpload';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import SaveIcon from '@mui/icons-material/Save';
import PersonIcon from '@mui/icons-material/Person';
import { useRouteStore } from '@/stores/routeStore';
import { useUIStore } from '@/stores/uiStore';
import { usePreferencesStore } from '@/stores/preferencesStore';
import { api } from '@/lib/api';
import { buildGpxBlob, downloadBlob } from '@/lib/utils';

export default function AppBar() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<Array<{
    id: string;
    label: string;
    lat: number;
    lon: number;
    layer?: string;
    confidence?: number;
    score?: number;
  }>>([]);
  const [lastNonEmptySuggestions, setLastNonEmptySuggestions] = useState<typeof suggestions>([]);
  const [lastQuery, setLastQuery] = useState('');
  const [fallbackCenter, setFallbackCenter] = useState<{ lat: number; lng: number; zoom: number } | null>(null);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [isHoveringSuggestions, setIsHoveringSuggestions] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState<null | HTMLElement>(null);

  const { currentRoute, resetRoute, isSaving, setIsSaving } = useRouteStore();
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const routeSnapshot = useRouteStore((state) => ({
    viaPointsCount: state.constraints.viaPoints.length,
    routeGeometryLength: state.routeGeometry?.length ?? 0,
    manualSegmentsLength: state.manualSegments.length,
    hasEnd: Boolean(state.constraints.end),
  }));
  const { flyMapTo, mapCenter, setSearchMarker } = useUIStore();
  const { setGpxImportOpen, setRouteLibraryOpen, setSettingsOpen } = useUIStore();
  const { isAuthenticated, setAuthenticated } = usePreferencesStore();
  const router = useRouter();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchRequestIdRef = useRef(0);
  const searchCacheRef = useRef(new Map<string, { expiresAt: number; results: any[] }>());
  useEffect(() => {
    if (mapCenter) {
      setFallbackCenter(mapCenter);
      return;
    }
    try {
      const saved = localStorage.getItem('john-router-map-position');
      if (!saved) return;
      const parsed = JSON.parse(saved);
      if (
        typeof parsed.longitude === 'number' &&
        typeof parsed.latitude === 'number' &&
        typeof parsed.zoom === 'number'
      ) {
        setFallbackCenter({ lng: parsed.longitude, lat: parsed.latitude, zoom: parsed.zoom });
      }
    } catch {
      // ignore invalid localStorage data
    }
  }, [mapCenter]);

  const handleExportGpx = async () => {
    if (!currentRoute) return;
    const geometry = routeGeometry ?? currentRoute.geometry?.coordinates ?? [];
    const safeName = (currentRoute.name || 'route')
      .trim()
      .replace(/\s+/g, '_')
      .replace(/[^a-zA-Z0-9_-]+/g, '');
    const filename = `${safeName || 'route'}.gpx`;

    if (geometry.length > 0) {
      const blob = buildGpxBlob({ name: currentRoute.name || 'Route', coordinates: geometry });
      downloadBlob(blob, filename);
      return;
    }

    try {
      const blob = await api.exportGpx(currentRoute.id);
      downloadBlob(blob, filename);
    } catch (error) {
      console.error('Failed to export GPX:', error);
    }
  };

  const handleSave = async () => {
    if (!currentRoute) return;

    setIsSaving(true);
    try {
      // Save logic would go here
      await new Promise((resolve) => setTimeout(resolve, 1000));
    } catch (error) {
      console.error('Failed to save:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    try {
      const results = await fetchGeocodeResults(searchQuery, 1, undefined, { mode: 'search' });
      if (results.length > 0) {
        const result = results[0];
        flyMapTo({
          lat: result.lat,
          lng: result.lon,
          zoom: 14,
          name: result.label,
          reason: 'search',
        });
        setSearchMarker({
          position: { lat: result.lat, lng: result.lon },
          label: result.label,
          layer: result.layer,
          routeSnapshot,
        });
      } else {
        console.log('No results found for:', searchQuery);
      }
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault();
      e.stopPropagation();
      const input = searchInputRef.current;
      if (input) {
        const length = input.value.length;
        input.setSelectionRange(0, length);
      }
      return;
    }
    if (e.key === 'Enter') {
      setShowSuggestions(false);
      setSuggestions([]);
      handleSearch();
    }
  };

  const formatSuggestion = useMemo(
    () => (label: string, layer?: string) => {
      const parts = label.split(',').map((part) => part.trim()).filter(Boolean);
      const [primary, ...rest] = parts;
      const layerLabel = layer
        ? {
            venue: 'Landmark',
            street: 'Road',
            address: 'Address',
            neighbourhood: 'Neighborhood',
            locality: 'Town',
            localadmin: 'City',
            county: 'County',
            region: 'Region',
            country: 'Country',
          }[layer]
        : undefined;
      const secondary = rest.join(', ');
      return {
        primary: primary || label,
        secondary: layerLabel ? `${layerLabel}${secondary ? ` · ${secondary}` : ''}` : secondary,
      };
    },
    []
  );

  const handleSelectSuggestion = (result: { label: string; lat: number; lon: number; layer?: string }) => {
    flyMapTo({
      lat: result.lat,
      lng: result.lon,
      zoom: 14,
      name: result.label,
      reason: 'search',
    });
    setSearchMarker({
      position: { lat: result.lat, lng: result.lon },
      label: result.label,
      layer: result.layer,
      routeSnapshot,
    });
    setSearchQuery('');
    setSuggestions([]);
    setShowSuggestions(false);
  };

  const fetchGeocodeResults = useMemo(() => {
    const geocodeEarthKey = process.env.NEXT_PUBLIC_GEOCODE_EARTH_KEY;
    const layers = [
      'venue',
      'street',
      'address',
      'neighbourhood',
      'locality',
      'localadmin',
      'county',
      'region',
      'country',
    ];
    const effectiveCenter = mapCenter ?? fallbackCenter;

    const getDistanceKm = (from: { lat: number; lng: number }, to: { lat: number; lng: number }) => {
      const toRad = (value: number) => (value * Math.PI) / 180;
      const earthRadiusKm = 6371;
      const dLat = toRad(to.lat - from.lat);
      const dLng = toRad(to.lng - from.lng);
      const lat1 = toRad(from.lat);
      const lat2 = toRad(to.lat);
      const a =
        Math.sin(dLat / 2) ** 2 +
        Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      return earthRadiusKm * c;
    };

    const normalizeText = (value: string) =>
      value
        .toLowerCase()
        .replace(/[^\w\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    const getQueryIntent = (query: string) => {
      const normalized = normalizeText(query);
      const tokens = normalized.split(' ').filter(Boolean);
      const hasNumber = /\d/.test(query);
      const streetSuffixes = [
        'st',
        'street',
        'rd',
        'road',
        'ave',
        'avenue',
        'blvd',
        'boulevard',
        'dr',
        'drive',
        'ln',
        'lane',
        'ct',
        'court',
        'way',
        'hwy',
        'highway',
      ];
      const hasStreetSuffix = tokens.some((token) => streetSuffixes.includes(token));
      const hasComma = query.includes(',');
      const isExplicit =
        hasComma ||
        tokens.length >= 3 ||
        hasNumber ||
        hasStreetSuffix ||
        (tokens.length >= 2 && normalized.length >= 10);
      const allowGlobal =
        hasComma ||
        hasNumber ||
        hasStreetSuffix ||
        tokens.length >= 3 ||
        (tokens.length >= 2 && normalized.length >= 10);
      return {
        normalized,
        tokens,
        isAddress: hasNumber || hasStreetSuffix,
        specificity: Math.min(1, tokens.length / 4) + (hasComma ? 0.2 : 0),
        isExplicit,
        allowGlobal,
      };
    };

    const getLocalRadiusKm = (zoom?: number, queryLength = 0) => {
      const effectiveZoom = zoom ?? 10;
      const shortQueryBoost = queryLength <= 3 ? 2 : queryLength <= 4 ? 1.5 : 1;
      if (effectiveZoom >= 13) return 20 * shortQueryBoost;
      if (effectiveZoom >= 11) return 45 * shortQueryBoost;
      if (effectiveZoom >= 9) return 110 * shortQueryBoost;
      return 220 * shortQueryBoost;
    };

    const getDistanceScore = (distanceKm: number | null, zoom?: number, specificity = 0) => {
      if (distanceKm == null) return 0.5;
      const effectiveZoom = zoom ?? 10;
      const baseRadiusKm =
        effectiveZoom >= 12 ? 6 : effectiveZoom >= 10 ? 16 : effectiveZoom >= 8 ? 45 : 120;
      const radiusKm = baseRadiusKm * (1 + specificity * 1.25);
      const normalized = distanceKm / radiusKm;
      const score = Math.exp(-Math.pow(normalized, 1.6));
      if (distanceKm > radiusKm * 3 && specificity < 0.7) {
        return score * 0.15;
      }
      return score;
    };

    const getTextScore = (label: string, intent: ReturnType<typeof getQueryIntent>) => {
      if (!intent.normalized) return 0;
      const labelNormalized = normalizeText(label);
      if (!labelNormalized) return 0;
      if (labelNormalized.startsWith(intent.normalized)) return 1;
      const labelTokens = labelNormalized.split(' ').filter(Boolean);
      const tokensPresent = intent.tokens.filter((token) => labelNormalized.includes(token)).length;
      const prefixMatches = intent.tokens.filter((token) =>
        labelTokens.some((labelToken) => labelToken.startsWith(token))
      ).length;
      if (prefixMatches === intent.tokens.length) {
        return 0.9;
      }
      if (tokensPresent === intent.tokens.length) return 0.8;
      if (labelNormalized.includes(intent.normalized)) return 0.6;
      const matchScore = Math.max(tokensPresent, prefixMatches);
      return matchScore ? 0.35 + (matchScore / intent.tokens.length) * 0.35 : 0;
    };

    const getLayerWeight = (layer?: string) => {
      const weights: Record<string, number> = {
        venue: 0.9,
        street: 0.8,
        address: 0.7,
        neighbourhood: 0.7,
        locality: 0.9,
        localadmin: 0.8,
        county: 0.6,
        region: 0.5,
        country: 0.4,
      };
      return layer ? weights[layer] ?? 0.5 : 0.5;
    };

    const getCategoryScore = (label: string, intent: ReturnType<typeof getQueryIntent>) => {
      const keywordGroups = [
        ['trail', 'trails', 'path', 'greenway'],
        ['park', 'reserve', 'forest', 'state park', 'national park'],
        ['road', 'rd', 'street', 'st', 'avenue', 'ave', 'boulevard', 'blvd', 'drive', 'dr'],
        ['lake', 'river', 'creek', 'mount', 'mt', 'hill'],
      ];
      const labelNormalized = normalizeText(label);
      const queryNormalized = intent.normalized;
      const labelHasKeyword = keywordGroups.some((group) =>
        group.some((keyword) => labelNormalized.includes(keyword))
      );
      const queryHasKeyword = keywordGroups.some((group) =>
        group.some((keyword) => queryNormalized.includes(keyword))
      );
      if (labelHasKeyword && queryHasKeyword) return 0.3;
      if (labelHasKeyword) return 0.15;
      return 0;
    };

    const getAddressIntentScore = (layer: string | undefined, intent: ReturnType<typeof getQueryIntent>) => {
      if (!layer) return 0;
      if (intent.isAddress) {
        return layer === 'address' || layer === 'street' ? 0.2 : -0.05;
      }
      return layer === 'address' ? -0.1 : 0;
    };

    const scoreResult = (
      result: { label: string; lat: number; lon: number; layer?: string; confidence?: number },
      intent: ReturnType<typeof getQueryIntent>,
      center: { lat: number; lng: number; zoom: number } | null
    ) => {
      const distanceKm = center
        ? getDistanceKm({ lat: center.lat, lng: center.lng }, { lat: result.lat, lng: result.lon })
        : null;
      const distanceScore = getDistanceScore(distanceKm, center?.zoom, intent.specificity);
      const textScore = getTextScore(result.label, intent);
      const confidenceScore = Math.max(0, Math.min(1, result.confidence ?? 0.5));
      const layerScore = getLayerWeight(result.layer);
      const majorScore = confidenceScore * 0.6 + layerScore * 0.4;
      const categoryScore = getCategoryScore(result.label, intent);
      const addressIntentScore = getAddressIntentScore(result.layer, intent);
      return (
        distanceScore * 0.55 +
        majorScore * 0.2 +
        textScore * 0.2 +
        categoryScore +
        addressIntentScore
      );
    };

    return async (
      query: string,
      limit: number,
      signal?: AbortSignal,
      options?: { mode?: 'suggest' | 'search' }
    ) => {
      const mode = options?.mode ?? 'search';
      const isSuggestMode = mode === 'suggest';
      const requestTimeoutMs = isSuggestMode ? 2500 : 7000;
      const localTimeoutMs = isSuggestMode ? 1500 : 3500;
      const cacheTtlMs = isSuggestMode ? 15_000 : 60_000;
      const intent = getQueryIntent(query);
      const queryLength = intent.normalized.length;
      const focusParams =
        effectiveCenter && Number.isFinite(effectiveCenter.lat) && Number.isFinite(effectiveCenter.lng)
          ? `&focus.point.lat=${effectiveCenter.lat}&focus.point.lon=${effectiveCenter.lng}`
          : '';
      const localRadiusKm = getLocalRadiusKm(effectiveCenter?.zoom, queryLength);
      const boundaryCircleParams =
        effectiveCenter && Number.isFinite(effectiveCenter.lat) && Number.isFinite(effectiveCenter.lng)
          ? `&boundary.circle.lat=${effectiveCenter.lat}&boundary.circle.lon=${effectiveCenter.lng}&boundary.circle.radius=${localRadiusKm}`
          : '';

      const cacheKeyParts = [
        mode,
        intent.normalized,
        effectiveCenter ? effectiveCenter.lat.toFixed(3) : 'na',
        effectiveCenter ? effectiveCenter.lng.toFixed(3) : 'na',
        effectiveCenter ? Math.round(effectiveCenter.zoom) : 'na',
      ];
      const cacheKey = cacheKeyParts.join(':');
      const cached = searchCacheRef.current.get(cacheKey);
      if (cached && cached.expiresAt > Date.now()) {
        return cached.results.slice(0, limit);
      }

      const withTimeout = async <T,>(
        runner: (activeSignal: AbortSignal) => Promise<T>,
        timeoutMs: number
      ): Promise<T | null> => {
        const controller = new AbortController();
        const abortHandler = () => controller.abort();
        if (signal) {
          if (signal.aborted) {
            controller.abort();
          } else {
            signal.addEventListener('abort', abortHandler, { once: true });
          }
        }
        const timeout = setTimeout(() => controller.abort(), timeoutMs);
        try {
          return await runner(controller.signal);
        } catch (error) {
          if ((error as Error).name !== 'AbortError') {
            console.warn('Search request failed:', error);
          }
          return null;
        } finally {
          clearTimeout(timeout);
          if (signal) {
            signal.removeEventListener('abort', abortHandler);
          }
        }
      };

      const firstNonEmpty = async <T,>(promises: Array<Promise<T[]>>): Promise<T[]> =>
        new Promise((resolve) => {
          let pending = promises.length;
          if (pending === 0) return resolve([]);
          let resolved = false;
          promises.forEach((promise) => {
            promise
              .then((results) => {
                if (resolved) return;
                if (Array.isArray(results) && results.length > 0) {
                  resolved = true;
                  resolve(results);
                  return;
                }
                pending -= 1;
                if (pending === 0) resolve([]);
              })
              .catch(() => {
                pending -= 1;
                if (pending === 0) resolve([]);
              });
          });
        });

      const rankResults = (items: any[]) => {
        const center = effectiveCenter ?? null;
        const effectiveZoom = center?.zoom ?? 10;
        const maxDistanceKm = effectiveZoom >= 12 ? 35 : effectiveZoom >= 10 ? 90 : 180;
        const distanceCutoffKm = intent.isExplicit ? maxDistanceKm * 3.5 : maxDistanceKm;
        const toRanked = (list: any[]) =>
          list
            .map((result: any) => ({
              ...result,
              distanceKm: center
                ? getDistanceKm({ lat: center.lat, lng: center.lng }, { lat: result.lat, lng: result.lon })
                : null,
              score: scoreResult(result, intent, center),
            }))
            .sort((a: any, b: any) => b.score - a.score);

        const ranked = toRanked(items);
        const filtered = ranked.filter((result: any) => {
          if (result.distanceKm == null) return true;
          return result.distanceKm <= distanceCutoffKm;
        });

        const relaxed = filtered.length > 0
          ? filtered
          : ranked.filter((result: any) => {
              if (result.distanceKm == null) return true;
              return result.distanceKm <= distanceCutoffKm * 2;
            });

        const finalList = relaxed.length > 0 ? relaxed : ranked;

        const deduped = new Map<string, any>();
        for (const result of finalList) {
          const key = `${result.label.toLowerCase()}-${result.lat.toFixed(3)}-${result.lon.toFixed(3)}`;
          const existing = deduped.get(key);
          if (!existing || result.score > existing.score) {
            deduped.set(key, result);
          }
        }
        return Array.from(deduped.values());
      };

      const fetchLocalPrefix = async () => {
        if (queryLength < 2 || queryLength > 6 || !effectiveCenter) return [];
        const localResults = await withTimeout(
          async (activeSignal) => {
            const response = await fetch('/api/local-search', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                lat: effectiveCenter.lat,
                lng: effectiveCenter.lng,
                radiusKm: localRadiusKm,
                prefix: intent.normalized,
                limit: limit * 4,
              }),
              signal: activeSignal,
            });
            if (!response.ok) return [];
            const data = await response.json();
            return Array.isArray(data?.results) ? data.results : [];
          },
          localTimeoutMs
        );
        return Array.isArray(localResults) ? localResults : [];
      };

      const fetchGeocodeEarth = async (
        endpoint: 'autocomplete' | 'search',
        useBoundary: boolean,
        text: string = query
      ) => {
        if (!geocodeEarthKey) return [];
        const boundaryParams = useBoundary ? boundaryCircleParams : '';
        const data = await withTimeout(
          async (activeSignal) => {
            const response = await fetch(
              `https://api.geocode.earth/v1/${endpoint}?text=${encodeURIComponent(text)}&size=${limit * 2}&layers=${layers.join(',')}${focusParams}${boundaryParams}&api_key=${geocodeEarthKey}`,
              { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
            );
            if (!response.ok) return null;
            return response.json();
          },
          requestTimeoutMs
        );
        if (!Array.isArray(data?.features)) return [];
        return data.features
          .map((feature: any) => {
            const label = feature?.properties?.label || feature?.properties?.name;
            const coordinates = feature?.geometry?.coordinates;
            if (!label || !Array.isArray(coordinates) || coordinates.length < 2) return null;
            return {
              id: feature?.properties?.gid || `${label}-${coordinates[1]}-${coordinates[0]}`,
              label,
              lat: Number(coordinates[1]),
              lon: Number(coordinates[0]),
              layer: feature?.properties?.layer,
              confidence: typeof feature?.properties?.confidence === 'number' ? feature.properties.confidence : undefined,
            };
          })
          .filter(Boolean);
      };

      const fetchPhotonResults = async (text: string = query) => {
        const url = new URL('https://photon.komoot.io/api/');
        url.searchParams.set('q', text);
        url.searchParams.set('limit', String(limit * 3));
        if (effectiveCenter) {
          url.searchParams.set('lat', String(effectiveCenter.lat));
          url.searchParams.set('lon', String(effectiveCenter.lng));
        }
        const data = await withTimeout(
          async (activeSignal) => {
            const response = await fetch(url.toString(), {
              headers: { 'User-Agent': 'JohnRouter/1.0' },
              signal: activeSignal,
            });
            if (!response.ok) return null;
            return response.json();
          },
          requestTimeoutMs
        );
        if (!Array.isArray(data?.features)) return [];
        return data.features
          .map((feature: any) => {
            const props = feature?.properties ?? {};
            const name = props?.name;
            const coordinates = feature?.geometry?.coordinates;
            if (!name || !Array.isArray(coordinates) || coordinates.length < 2) return null;
            const labelParts = [
              name,
              props?.city,
              props?.state,
              props?.country,
            ].filter(Boolean);
            return {
              id: props?.osm_id ? `photon-${props.osm_id}` : `${name}-${coordinates[1]}-${coordinates[0]}`,
              label: labelParts.join(', '),
              lat: Number(coordinates[1]),
              lon: Number(coordinates[0]),
              layer: props?.osm_key,
            };
          })
          .filter(Boolean);
      };

      const localResults = await fetchLocalPrefix();
      if (Array.isArray(localResults) && localResults.length > 0 && !isSuggestMode) {
        const rankedLocal = rankResults(localResults).slice(0, limit);
        searchCacheRef.current.set(cacheKey, {
          expiresAt: Date.now() + cacheTtlMs,
          results: rankedLocal,
        });
        return rankedLocal;
      }

      if (geocodeEarthKey) {
        if (isSuggestMode) {
          const suggestionCandidates = await firstNonEmpty([
            Promise.resolve(localResults),
            fetchGeocodeEarth('autocomplete', true),
            fetchGeocodeEarth('autocomplete', false),
            fetchPhotonResults(),
          ]);
          if (suggestionCandidates.length > 0) {
            const ranked = rankResults(suggestionCandidates).slice(0, limit);
            searchCacheRef.current.set(cacheKey, {
              expiresAt: Date.now() + cacheTtlMs,
              results: ranked,
            });
            return ranked;
          }
        } else {
          const localResults = await fetchGeocodeEarth('autocomplete', true);
          const localFallback = localResults.length === 0 ? await fetchGeocodeEarth('search', true) : [];
          const combinedLocal = [...localResults, ...localFallback];
          const rankedLocal = combinedLocal.length > 0 ? rankResults(combinedLocal) : [];

          if (!intent.allowGlobal) {
            if (rankedLocal.length > 0) {
              const trimmed = rankedLocal.slice(0, limit);
              searchCacheRef.current.set(cacheKey, {
                expiresAt: Date.now() + cacheTtlMs,
                results: trimmed,
              });
              return trimmed;
            }

            if (queryLength <= 4) {
              const wildcardText = `${query}*`;
              const wildcardLocal = await fetchGeocodeEarth('search', true, wildcardText);
              if (wildcardLocal.length > 0) {
                const rankedWildcard = rankResults(wildcardLocal);
                if (rankedWildcard.length > 0) {
                  const trimmed = rankedWildcard.slice(0, limit);
                  searchCacheRef.current.set(cacheKey, {
                    expiresAt: Date.now() + cacheTtlMs,
                    results: trimmed,
                  });
                  return trimmed;
                }
              }
            }

            // If boundary.circle is too strict for short prefixes, retry without boundary
            const unboundedAuto = await fetchGeocodeEarth('autocomplete', false);
            const unboundedSearch = unboundedAuto.length === 0 ? await fetchGeocodeEarth('search', false) : [];
            const combinedUnbounded = [...unboundedAuto, ...unboundedSearch];
            if (combinedUnbounded.length > 0) {
              const localFiltered = rankResults(combinedUnbounded).filter((result: any) => {
                if (result.distanceKm == null) return false;
                return result.distanceKm <= localRadiusKm * 1.5;
              });
              if (localFiltered.length > 0) {
                const trimmed = localFiltered.slice(0, limit);
                searchCacheRef.current.set(cacheKey, {
                  expiresAt: Date.now() + cacheTtlMs,
                  results: trimmed,
                });
                return trimmed;
              }
            }

            const expandedBoundary =
              effectiveCenter && Number.isFinite(effectiveCenter.lat) && Number.isFinite(effectiveCenter.lng)
                ? `&boundary.circle.lat=${effectiveCenter.lat}&boundary.circle.lon=${effectiveCenter.lng}&boundary.circle.radius=${localRadiusKm * 2}`
                : '';
            if (expandedBoundary) {
              const expandedData = await withTimeout(
                async (activeSignal) => {
                  const expanded = await fetch(
                    `https://api.geocode.earth/v1/search?text=${encodeURIComponent(query)}&size=${limit * 2}&layers=${layers.join(',')}${focusParams}${expandedBoundary}&api_key=${geocodeEarthKey}`,
                    { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
                  );
                  if (!expanded.ok) return null;
                  return expanded.json();
                },
                requestTimeoutMs
              );
              if (Array.isArray(expandedData?.features)) {
                const expandedResults = expandedData.features
                  .map((feature: any) => {
                    const label = feature?.properties?.label || feature?.properties?.name;
                    const coordinates = feature?.geometry?.coordinates;
                    if (!label || !Array.isArray(coordinates) || coordinates.length < 2) return null;
                    return {
                      id: feature?.properties?.gid || `${label}-${coordinates[1]}-${coordinates[0]}`,
                      label,
                      lat: Number(coordinates[1]),
                      lon: Number(coordinates[0]),
                      layer: feature?.properties?.layer,
                      confidence: typeof feature?.properties?.confidence === 'number' ? feature.properties.confidence : undefined,
                    };
                  })
                  .filter(Boolean);
                const rankedExpanded = rankResults(expandedResults);
                if (rankedExpanded.length > 0) {
                  const trimmed = rankedExpanded.slice(0, limit);
                  searchCacheRef.current.set(cacheKey, {
                    expiresAt: Date.now() + cacheTtlMs,
                    results: trimmed,
                  });
                  return trimmed;
                }
              }
            }
          } else {
            const globalResults = await fetchGeocodeEarth('autocomplete', false);
            const globalFallback = globalResults.length === 0 ? await fetchGeocodeEarth('search', false) : [];
            const combined = [...combinedLocal, ...globalResults, ...globalFallback];
            const ranked = combined.length > 0 ? rankResults(combined) : [];
            if (ranked.length > 0) {
              const trimmed = ranked.slice(0, limit);
              searchCacheRef.current.set(cacheKey, {
                expiresAt: Date.now() + cacheTtlMs,
                results: trimmed,
              });
              return trimmed;
            }
          }
        }
      }

      const buildViewbox = (radiusKm: number) => {
        if (!effectiveCenter) return '';
        const lat = effectiveCenter.lat;
        const km = radiusKm;
        const latDelta = km / 110.574;
        const lngDelta = km / (111.32 * Math.cos((lat * Math.PI) / 180));
        const minLat = lat - latDelta;
        const maxLat = lat + latDelta;
        const minLng = effectiveCenter.lng - lngDelta;
        const maxLng = effectiveCenter.lng + lngDelta;
        return `&viewbox=${minLng},${maxLat},${maxLng},${minLat}&bounded=1`;
      };

      if (isSuggestMode) {
        const nominatimResults = !geocodeEarthKey
          ? await withTimeout(
              async (activeSignal) => {
                const response = await fetch(
                  `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=${limit * 3}${intent.allowGlobal ? '' : buildViewbox(localRadiusKm)}`,
                  { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
                );
                if (!response.ok) return [];
                return response.json();
              },
              requestTimeoutMs
            )
          : [];
        const nominatimCandidates = Array.isArray(nominatimResults)
          ? nominatimResults
              .map((result: any) => {
                if (!result?.display_name || result?.lat == null || result?.lon == null) return null;
                return {
                  id: `${result.place_id || result.display_name}-${result.lat}-${result.lon}`,
                  label: result.display_name,
                  lat: parseFloat(result.lat),
                  lon: parseFloat(result.lon),
                  layer: result?.type,
                };
              })
              .filter(Boolean)
          : [];
        const suggestionCandidates = await firstNonEmpty([
          Promise.resolve(localResults),
          fetchPhotonResults(),
          Promise.resolve(nominatimCandidates),
        ]);
        if (suggestionCandidates.length > 0) {
          const ranked = rankResults(suggestionCandidates).slice(0, limit);
          searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: ranked });
          return ranked;
        }
        searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: [] });
        return [];
      }

      const results = await withTimeout(
        async (activeSignal) => {
          const response = await fetch(
            `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=${limit * 3}${intent.allowGlobal ? '' : buildViewbox(localRadiusKm)}`,
            { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
          );
          if (!response.ok) return [];
          return response.json();
        },
        requestTimeoutMs
      );
      if (!Array.isArray(results)) return [];
      const ranked = results
        .map((result: any) => {
          if (!result?.display_name || result?.lat == null || result?.lon == null) return null;
          return {
            id: `${result.place_id || result.display_name}-${result.lat}-${result.lon}`,
            label: result.display_name,
            lat: parseFloat(result.lat),
            lon: parseFloat(result.lon),
            layer: result?.type,
          };
        })
        .filter(Boolean);
      const rankedResults = rankResults(ranked);
      if (rankedResults.length > 0) {
        const trimmed = rankedResults.slice(0, limit);
        searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: trimmed });
        return trimmed;
      }

      if (!intent.allowGlobal && effectiveCenter && queryLength <= 4) {
        const unboundedResults = await withTimeout(
          async (activeSignal) => {
            const unboundedResponse = await fetch(
              `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=${limit * 4}`,
              { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
            );
            if (!unboundedResponse.ok) return [];
            return unboundedResponse.json();
          },
          requestTimeoutMs
        );
        if (Array.isArray(unboundedResults)) {
          const unboundedRanked = rankResults(
            unboundedResults
              .map((result: any) => {
                if (!result?.display_name || result?.lat == null || result?.lon == null) return null;
                return {
                  id: `${result.place_id || result.display_name}-${result.lat}-${result.lon}`,
                  label: result.display_name,
                  lat: parseFloat(result.lat),
                  lon: parseFloat(result.lon),
                  layer: result?.type,
                };
              })
              .filter(Boolean)
          ).filter((result: any) => {
            if (result.distanceKm == null) return false;
            return result.distanceKm <= localRadiusKm * 2;
          });
          if (unboundedRanked.length > 0) {
            const trimmed = unboundedRanked.slice(0, limit);
            searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: trimmed });
            return trimmed;
          }
        }
      }

      if (!intent.allowGlobal && effectiveCenter && queryLength <= 4) {
        const wildcardResults = await withTimeout(
          async (activeSignal) => {
            const wildcardResponse = await fetch(
              `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(`${query}*`)}&limit=${limit * 4}${buildViewbox(localRadiusKm)}`,
              { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
            );
            if (!wildcardResponse.ok) return [];
            return wildcardResponse.json();
          },
          requestTimeoutMs
        );
        if (Array.isArray(wildcardResults)) {
          const wildcardRanked = rankResults(
            wildcardResults
              .map((result: any) => {
                if (!result?.display_name || result?.lat == null || result?.lon == null) return null;
                return {
                  id: `${result.place_id || result.display_name}-${result.lat}-${result.lon}`,
                  label: result.display_name,
                  lat: parseFloat(result.lat),
                  lon: parseFloat(result.lon),
                  layer: result?.type,
                };
              })
              .filter(Boolean)
          );
          if (wildcardRanked.length > 0) {
            const trimmed = wildcardRanked.slice(0, limit);
            searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: trimmed });
            return trimmed;
          }
        }
      }

      if (!intent.allowGlobal && effectiveCenter) {
        const expandedRadius = localRadiusKm * 2.5;
        const expandedResults = await withTimeout(
          async (activeSignal) => {
            const expandedResponse = await fetch(
              `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=${limit * 3}${buildViewbox(expandedRadius)}`,
              { headers: { 'User-Agent': 'JohnRouter/1.0' }, signal: activeSignal }
            );
            if (!expandedResponse.ok) return [];
            return expandedResponse.json();
          },
          requestTimeoutMs
        );
        if (Array.isArray(expandedResults)) {
          const expandedRanked = rankResults(
            expandedResults
              .map((result: any) => {
                if (!result?.display_name || result?.lat == null || result?.lon == null) return null;
                return {
                  id: `${result.place_id || result.display_name}-${result.lat}-${result.lon}`,
                  label: result.display_name,
                  lat: parseFloat(result.lat),
                  lon: parseFloat(result.lon),
                  layer: result?.type,
                };
              })
              .filter(Boolean)
          );
          if (expandedRanked.length > 0) {
            const trimmed = expandedRanked.slice(0, limit);
            searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: trimmed });
            return trimmed;
          }
        }
      }

      searchCacheRef.current.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: [] });
      return rankedResults.slice(0, limit);
    };
  }, [mapCenter, fallbackCenter]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (query.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      setIsSuggesting(false);
      return;
    }

    const controller = new AbortController();
    const requestId = ++searchRequestIdRef.current;
    const timer = setTimeout(async () => {
      setIsSuggesting(true);
      try {
        const results = await fetchGeocodeResults(query, 5, controller.signal, { mode: 'suggest' });
        if (!controller.signal.aborted && requestId === searchRequestIdRef.current) {
          if (results.length > 0) {
            setSuggestions(results);
            setLastNonEmptySuggestions(results);
            setLastQuery(query);
            setShowSuggestions(true);
          } else {
            const normalizedQuery = query.toLowerCase();
            const normalizedLast = lastQuery.toLowerCase();
            const shouldFallback =
              lastNonEmptySuggestions.length > 0 &&
              (normalizedQuery.startsWith(normalizedLast) ||
                normalizedLast.startsWith(normalizedQuery) ||
                Math.abs(normalizedQuery.length - normalizedLast.length) <= 2);
            if (shouldFallback) {
              const filtered = lastNonEmptySuggestions.filter((item) =>
                item.label.toLowerCase().includes(normalizedQuery)
              );
              if (filtered.length > 0) {
                setSuggestions(filtered);
                setShowSuggestions(true);
              } else if (!isSearchFocused && !isHoveringSuggestions) {
                setSuggestions([]);
              }
            } else if (!isSearchFocused && !isHoveringSuggestions) {
              setSuggestions([]);
            }
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          console.error('Autocomplete failed:', error);
        }
      } finally {
        if (requestId === searchRequestIdRef.current) {
          setIsSuggesting(false);
        }
      }
    }, 150);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [searchQuery, isSearchFocused, isHoveringSuggestions, lastNonEmptySuggestions, lastQuery]);

  const handleMenuNavigate = (path: string) => {
    setUserMenuAnchor(null);
    router.push(path);
  };

  const handleLogout = () => {
    api.setAuthToken(null);
    setAuthenticated(null);
    setUserMenuAnchor(null);
    router.push('/');
  };

  return (
    <MuiAppBar
      position="static"
      sx={{
        bgcolor: 'background.paper',
      }}
      elevation={0}
    >
      <Toolbar sx={{ gap: 1.5, minHeight: 56, px: 2, mt: '0px' }}>
        {/* Logo */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            mr: 1.5,
            height: 40,
          }}
        >
          <Typography
            component="div"
            sx={{
              fontFamily: '"Honk", system-ui',
              textTransform: 'uppercase',
              lineHeight: 0.6,
              letterSpacing: '0.02em',
              color: '#B3472D',
              textAlign: 'left',
              fontSize: '1.32rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              height: '100%',
            }}
          >
            <Box component="span" sx={{ display: 'block' }}>
              JOHN
            </Box>
            <Box component="span" sx={{ display: 'block' }}>
              ROUTER
            </Box>
          </Typography>
        </Box>

        {/* Global Search */}
        <ClickAwayListener onClickAway={() => {
          if (!isHoveringSuggestions) {
            setShowSuggestions(false);
          }
        }}>
          <Box sx={{ position: 'relative', width: 280 }}>
            <TextField
              size="small"
              placeholder="Places, trails, addresses..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => {
                setIsSearchFocused(true);
                if (suggestions.length > 0 || searchQuery.trim().length >= 2) {
                  setShowSuggestions(true);
                }
              }}
              onBlur={() => {
                setIsSearchFocused(false);
                setTimeout(() => {
                  if (!isHoveringSuggestions) {
                    setShowSuggestions(false);
                  }
                }, 100);
              }}
              onKeyDown={handleSearchKeyDown}
              onKeyDownCapture={handleSearchKeyDown}
              disabled={isSearching}
              inputRef={searchInputRef}
              sx={{
                width: '100%',
                '& .MuiOutlinedInput-root': {
                  bgcolor: 'transparent',
                  '& fieldset': {
                    borderColor: 'transparent',
                  },
                  '&:hover fieldset': {
                    borderColor: 'transparent',
                  },
                  '&.Mui-focused fieldset': {
                    borderColor: 'transparent',
                  },
                },
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Box sx={{ width: 18, height: 18, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {isSearching || isSuggesting ? (
                        <CircularProgress size={16} sx={{ color: 'text.secondary' }} />
                      ) : (
                        <SearchIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                      )}
                    </Box>
                  </InputAdornment>
                ),
              }}
            />
            {showSuggestions && suggestions.length > 0 && (
              <Paper
                elevation={3}
                sx={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  mt: 0.75,
                  zIndex: 1300,
                  maxHeight: 320,
                  overflowY: 'auto',
                  borderRadius: 1.5,
                }}
                onMouseEnter={() => {
                  setIsHoveringSuggestions(true);
                  setShowSuggestions(true);
                }}
                onMouseLeave={() => {
                  setIsHoveringSuggestions(false);
                  if (!isSearchFocused) {
                    setShowSuggestions(false);
                  }
                }}
              >
                <List dense disablePadding>
                  {suggestions.map((result) => {
                    const { primary, secondary } = formatSuggestion(result.label, result.layer);
                    return (
                      <ListItemButton
                        key={result.id}
                        onClick={() => handleSelectSuggestion(result)}
                        sx={{ px: 1.5, py: 1 }}
                      >
                        <ListItemText
                          primary={primary}
                          secondary={secondary || undefined}
                          primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: 600 }}
                          secondaryTypographyProps={{ fontSize: '0.75rem', color: 'text.secondary' }}
                        />
                      </ListItemButton>
                    );
                  })}
                </List>
              </Paper>
            )}
          </Box>
        </ClickAwayListener>

        {/* Spacer */}
        <Box sx={{ flex: 1 }} />

        {/* Action Buttons */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 2 }}>
          <Button
            startIcon={<AddIcon sx={{ fontSize: 18 }} />}
            variant="text"
            size="small"
            onClick={resetRoute}
            sx={{ 
              color: 'text.primary',
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
            }}
          >
            New
          </Button>

          <Button
            startIcon={<FileUploadIcon sx={{ fontSize: 18 }} />}
            variant="text"
            size="small"
            onClick={() => setGpxImportOpen(true)}
            sx={{ 
              color: 'text.primary',
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
            }}
          >
            Import
          </Button>

          <Button
            startIcon={<FileDownloadIcon sx={{ fontSize: 18 }} />}
            variant="text"
            size="small"
            onClick={handleExportGpx}
            disabled={
              !currentRoute ||
              ((routeGeometry?.length ?? 0) === 0 && (currentRoute.geometry?.coordinates?.length ?? 0) === 0)
            }
            sx={{ 
              color: 'text.primary',
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
            }}
          >
            Export
          </Button>

          <Button
            startIcon={isSaving ? undefined : <SaveIcon sx={{ fontSize: 18 }} />}
            variant="contained"
            size="small"
            onClick={handleSave}
            disabled={!currentRoute || isSaving}
            sx={{ 
              px: 2,
              minWidth: 80,
            }}
          >
            {isSaving ? <CircularProgress size={16} sx={{ color: 'inherit' }} /> : 'Save'}
          </Button>
        </Box>

        {/* User Menu */}
        <IconButton
          onClick={(e) => setUserMenuAnchor(e.currentTarget)}
          size="small"
          sx={{
            ml: 1,
            '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
          }}
        >
          {isAuthenticated ? (
            <Avatar sx={{ width: 28, height: 28, bgcolor: 'primary.main', fontSize: '0.8rem' }}>
              <PersonIcon sx={{ fontSize: 16 }} />
            </Avatar>
          ) : (
            <PersonIcon sx={{ color: 'text.secondary' }} />
          )}
        </IconButton>

        <Menu
          anchorEl={userMenuAnchor}
          open={Boolean(userMenuAnchor)}
          onClose={() => setUserMenuAnchor(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        >
          {isAuthenticated ? (
            [
              <MenuItem
                key="profile"
                onClick={() => {
                  setUserMenuAnchor(null);
                  setSettingsOpen(true);
                }}
              >
                Settings
              </MenuItem>,
              <MenuItem
                key="routes"
                onClick={() => {
                  setUserMenuAnchor(null);
                  setRouteLibraryOpen(true);
                }}
              >
                My Routes
              </MenuItem>,
              <MenuItem key="logout" onClick={handleLogout}>
                Sign Out
              </MenuItem>,
            ]
          ) : (
            [
              <MenuItem key="login" onClick={() => handleMenuNavigate('/login')}>
                Sign In
              </MenuItem>,
              <MenuItem key="register" onClick={() => handleMenuNavigate('/register')}>
                Create Account
              </MenuItem>,
            ]
          )}
        </Menu>
      </Toolbar>
    </MuiAppBar>
  );
}
