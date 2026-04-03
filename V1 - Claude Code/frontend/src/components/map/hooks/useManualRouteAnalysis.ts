/**
 * Hook for fetching elevation analysis for manually drawn routes
 * 
 * This hook watches the route geometry and triggers an analysis API call
 * when a manual route is being built, populating the manualAnalysis state
 * which is used by the Elevation tab in the Route Inspector Panel.
 */
import { useEffect, useRef, useCallback } from 'react';
import { useRouteStore } from '@/stores/routeStore';
import { api } from '@/lib/api';

// Debounce delay in milliseconds - wait for user to finish adding points
const ANALYSIS_DEBOUNCE_MS = 500;

export function useManualRouteAnalysis() {
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const currentRoute = useRouteStore((state) => state.currentRoute);
  const candidates = useRouteStore((state) => state.candidates);
  const selectedCandidateIndex = useRouteStore((state) => state.selectedCandidateIndex);
  const setManualAnalysis = useRouteStore((state) => state.setManualAnalysis);
  const setIsAnalyzing = useRouteStore((state) => state.setIsAnalyzing);
  const manualSegments = useRouteStore((state) => state.manualSegments);

  // Keep track of the last analyzed geometry to avoid redundant calls
  const lastAnalyzedGeometryRef = useRef<string | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const analyzeRoute = useCallback(async (geometry: number[][]) => {
    // Create a geometry hash to compare
    const geometryHash = JSON.stringify(geometry);
    
    // Skip if we've already analyzed this exact geometry
    if (geometryHash === lastAnalyzedGeometryRef.current) {
      return;
    }

    // Abort any pending request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Create new abort controller for this request
    abortControllerRef.current = new AbortController();

    try {
      setIsAnalyzing(true);
      
      const analysis = await api.analyzeGeometry({
        type: 'LineString',
        coordinates: geometry,
      });

      // Only update if we haven't been aborted
      if (!abortControllerRef.current?.signal.aborted) {
        setManualAnalysis(analysis);
        lastAnalyzedGeometryRef.current = geometryHash;
      }
    } catch (error: any) {
      // Ignore abort errors
      if (error?.name !== 'AbortError' && error?.code !== 'ERR_CANCELED') {
        console.error('[useManualRouteAnalysis] Failed to analyze route:', error);
      }
    } finally {
      setIsAnalyzing(false);
    }
  }, [setManualAnalysis, setIsAnalyzing]);

  useEffect(() => {
    const candidateAnalysis = candidates[selectedCandidateIndex]?.analysis;
    const hasCandidateElevation = Boolean(candidateAnalysis?.elevationProfile?.length);
    const isManualRoute = currentRoute?.id === 'manual-route';
    const hasValidGeometry = routeGeometry && routeGeometry.length >= 2;
    const hasSegments = manualSegments.length > 0;

    if (hasCandidateElevation) {
      lastAnalyzedGeometryRef.current = null;
      return;
    }

    const shouldAnalyzeManual = isManualRoute && hasValidGeometry && hasSegments;
    const shouldAnalyzeImported = !isManualRoute && hasValidGeometry;

    if (!shouldAnalyzeManual && !shouldAnalyzeImported) {
      // Clear analysis if no longer a valid route
      if (!hasValidGeometry) {
        lastAnalyzedGeometryRef.current = null;
      }
      return;
    }

    // Clear any pending debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Debounce the analysis call to avoid hammering the API
    debounceTimerRef.current = setTimeout(() => {
      analyzeRoute(routeGeometry);
    }, ANALYSIS_DEBOUNCE_MS);

    // Cleanup
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [routeGeometry, currentRoute?.id, manualSegments.length, candidates, selectedCandidateIndex, analyzeRoute]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);
}
