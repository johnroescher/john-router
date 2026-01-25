import { useRouteStore } from '@/stores/routeStore';
import type { ManualRouteSegment } from '@/lib/routeSegmentation';

const buildSegment = (coordinates: number[][]): ManualRouteSegment => ({
  coordinates,
  distanceMeters: 0,
  elevationGain: 0,
  durationSeconds: 0,
  surfaceBreakdown: { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 },
});

const resetRouteStore = () => {
  useRouteStore.setState({
    manualSegments: [],
    segmentedImportedRoute: false,
    manualUndoStack: [],
    manualRedoStack: [],
  });
};

describe('routeStore segment validation', () => {
  beforeEach(() => {
    resetRouteStore();
  });

  it('filters out long two-point segments', () => {
    const longSegment = buildSegment([
      [-97.0, 30.0],
      [-97.0, 30.001], // ~111m
    ]);

    useRouteStore.getState().setManualSegments([longSegment]);

    const { manualSegments } = useRouteStore.getState();
    expect(manualSegments).toHaveLength(0);
  });

  it('keeps short two-point segments', () => {
    const shortSegment = buildSegment([
      [-97.0, 30.0],
      [-97.0, 30.00005], // ~5.5m
    ]);

    useRouteStore.getState().setManualSegments([shortSegment]);

    const { manualSegments } = useRouteStore.getState();
    expect(manualSegments).toHaveLength(1);
    expect(manualSegments[0].coordinates).toEqual(shortSegment.coordinates);
  });
});
