import { NextResponse } from 'next/server';

type LocalSearchRequest = {
  lat: number;
  lng: number;
  radiusKm?: number;
  prefix: string;
  limit?: number;
};

const toNumber = (value: unknown) => (typeof value === 'number' ? value : Number(value));

const getLayer = (tags: Record<string, string> | undefined) => {
  if (!tags) return undefined;
  if (tags.highway) return 'street';
  if (tags.leisure || tags.park) return 'park';
  if (tags.natural || tags.amenity || tags.tourism) return 'venue';
  return undefined;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const OVERPASS_ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.nchc.org.tw/api/interpreter',
];
const cache = new Map<string, { expiresAt: number; results: any[] }>();
const cacheTtlMs = 2 * 60 * 1000;
const roundCoord = (value: number) => Math.round(value * 100) / 100;

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as LocalSearchRequest;
    const lat = toNumber(body.lat);
    const lng = toNumber(body.lng);
    const radiusKm = clamp(toNumber(body.radiusKm ?? 30), 5, 200);
    const limit = clamp(toNumber(body.limit ?? 15), 5, 50);
    const prefix = String(body.prefix || '').trim();

    if (!Number.isFinite(lat) || !Number.isFinite(lng) || !prefix) {
      return NextResponse.json({ results: [] });
    }

    const cacheKey = `${roundCoord(lat)}:${roundCoord(lng)}:${radiusKm}:${prefix.toLowerCase()}`;
    const cached = cache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return NextResponse.json({ results: cached.results });
    }

    const radiusMeters = Math.round(radiusKm * 1000);
    const safePrefix = prefix.replace(/"/g, '');
    const fetchOverpass = async (query: string) => {
      for (const endpoint of OVERPASS_ENDPOINTS) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
          const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ data: query }),
            signal: controller.signal,
          });
          if (!response.ok) {
            continue;
          }
          const data = await response.json();
          if (Array.isArray(data?.elements)) {
            return data.elements;
          }
        } catch {
          // try next endpoint
        } finally {
          clearTimeout(timeout);
        }
      }
      return [];
    };

    const queries = [
      `[out:json][timeout:8];(way["highway"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng}););out tags center;`,
      `[out:json][timeout:8];(way["waterway"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng});way["leisure"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng});way["natural"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng});way["tourism"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng}););out tags center;`,
      `[out:json][timeout:8];(node["place"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng});node["amenity"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng});node["tourism"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng});node["leisure"]["name"~"^${safePrefix}",i](around:${radiusMeters},${lat},${lng}););out tags center;`,
    ];

    const elementSets = await Promise.all(queries.map((q) => fetchOverpass(q)));
    const elements = elementSets.flat();

    const results = elements
      .map((el: any) => {
        const name = el?.tags?.name;
        if (!name) return null;
        const latValue = el?.lat ?? el?.center?.lat;
        const lonValue = el?.lon ?? el?.center?.lon;
        if (typeof latValue !== 'number' || typeof lonValue !== 'number') return null;
        return {
          id: `${el.type}-${el.id}`,
          label: name,
          lat: latValue,
          lon: lonValue,
          layer: getLayer(el.tags),
        };
      })
      .filter(Boolean);

    const deduped = new Map<string, any>();
    for (const item of results) {
      const key = `${item.label.toLowerCase()}-${item.lat.toFixed(4)}-${item.lon.toFixed(4)}`;
      if (!deduped.has(key)) {
        deduped.set(key, item);
      }
    }

    const finalResults = Array.from(deduped.values()).slice(0, limit);
    cache.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, results: finalResults });
    return NextResponse.json({ results: finalResults });
  } catch {
    return NextResponse.json({ results: [] });
  }
}
