# Valhalla Surface Integration Test Plan

## Manual Checks

- Configure `VALHALLA_API_KEY` and `VALHALLA_BASE_URL` (US endpoint).
- Generate a route via `POST /routes/generate` and verify:
  - `surface_breakdown` is populated and `unknown` is not 100.
  - Validation warnings do not include missing surface data when Valhalla is available.
- Update an existing route geometry and verify `surface_breakdown` is persisted.
- Call `POST /routes/surface-match` and verify:
  - Response `segmentedSurface.enrichmentSource` is `routing_api`.
  - Segment surfaces are present and `dataQuality` > 0 for known areas.
- Use the frontend route inspector:
  - No client-side Overpass call occurs (network tab).
  - Map coloring and elevation chart use backend segments when available.

