const postMock = jest.fn();
const createMock = jest.fn(() => ({
  post: postMock,
  defaults: { headers: { common: {} } },
}));

jest.mock('axios', () => ({
  __esModule: true,
  default: { create: createMock },
  create: createMock,
}));

import { api } from '@/lib/api';

describe('api.routePointToPoint', () => {
  const infoSpy = jest.spyOn(console, 'info').mockImplementation(() => {});
  const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

  beforeEach(() => {
    postMock.mockReset();
    infoSpy.mockClear();
    errorSpy.mockClear();
    process.env.NEXT_PUBLIC_ROUTE_TRACE = 'true';
  });

  afterAll(() => {
    infoSpy.mockRestore();
    errorSpy.mockRestore();
  });

  it('adds X-Request-Id and logs start/success', async () => {
    postMock.mockResolvedValue({
      status: 200,
      data: {
        geometry: { type: 'LineString', coordinates: [[0, 0], [0.001, 0.001]] },
        distance_meters: 100,
        duration_seconds: 20,
        elevation_gain: 5,
        surface_breakdown: { paved: 100, unpaved: 0, gravel: 0, ground: 0, unknown: 0 },
        degraded: false,
        degraded_reason: null,
      },
    });

    await api.routePointToPoint(
      [
        { lat: 30.0, lng: -97.0 },
        { lat: 30.001, lng: -97.001 },
      ],
      'road'
    );

    const headers = postMock.mock.calls[0][2]?.headers ?? {};
    expect(headers['X-Request-Id']).toEqual(expect.any(String));
    expect(infoSpy.mock.calls.some(([message]) =>
      String(message).includes('[route-trace] routePointToPoint start')
    )).toBe(true);
    expect(infoSpy.mock.calls.some(([message]) =>
      String(message).includes('[route-trace] routePointToPoint success')
    )).toBe(true);
  });
});
