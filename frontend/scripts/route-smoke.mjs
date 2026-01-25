const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const fetchWithTimeout = async (url, options = {}, timeoutMs = 10000) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
};

const run = async () => {
  const health = await fetchWithTimeout(`${API_URL}/api/health`, {}, 5000);
  if (!health.ok) {
    throw new Error(`Health check failed: ${health.status}`);
  }

  const routeResponse = await fetchWithTimeout(
    `${API_URL}/api/routes/point-to-point`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        coordinates: [
          { lat: 30.1971, lng: -97.8814 },
          { lat: 30.1971, lng: -97.8803 },
        ],
        sport_type: 'road',
      }),
    },
    15000
  );

  if (!routeResponse.ok) {
    const text = await routeResponse.text();
    throw new Error(`Route request failed: ${routeResponse.status} ${text}`);
  }

  const data = await routeResponse.json();
  if (!data?.geometry?.coordinates?.length) {
    throw new Error('Route response missing geometry');
  }

  console.log('[route-smoke] ok', {
    distance_meters: data.distance_meters,
    points: data.geometry.coordinates.length,
  });
};

run().catch((error) => {
  console.error('[route-smoke] failed', error);
  process.exit(1);
});
