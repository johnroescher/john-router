# Router policy matrix (V1)

Single source for **which engine runs** for which sport, route shape, and `routing_service` override.  
Implementation: `backend/app/services/routing.py` (`RoutingService.generate_route`), ORS/BRouter/GraphHopper/Valhalla profile dicts, and `backend/app/api/routes.py` (`POST /api/routes/point-to-point`).

Related: `ROUTING_SYSTEM.md` (pipeline detail), `V1_PROGRAM.md` (P1 exit criteria).

---

## 1. Constraints and enums

| Field | Values |
|--------|--------|
| `sport_type` | `road`, `gravel`, `mtb`, `emtb` |
| `route_type` | `loop`, `out_and_back`, `point_to_point` |
| `routing_service` | `auto`, `ors`, `brouter`, `graphhopper`, `valhalla` |

**AUTO trail bias:** `use_brouter = true` when `sport_type` ∈ {`gravel`, `mtb`, `emtb`}. For `road`, `use_brouter = false` (ORS-first).  
Explicit `routing_service` overrides the AUTO choice (e.g. `ors` forces ORS).

---

## 2. Default profiles (by sport)

| Sport | ORS profile | BRouter profile | GraphHopper profile | Valhalla profile |
|-------|-------------|-----------------|---------------------|------------------|
| road | `driving-car` | `fastbike` | `bike` | `bicycle` |
| gravel | `cycling-regular` | `trekking` | `bike` | `bicycle` |
| mtb | `cycling-mountain` | `mtb` | `mtb` | `bicycle` |
| emtb | `cycling-electric` | `mtb` | `mtb` | `bicycle` |

`routing_profile` on `RouteConstraints` overrides the profile for the selected engine.

---

## 3. `generate_route` engine selection (AUTO and explicit)

| `routing_service` | Primary engine | Notes |
|-------------------|----------------|-------|
| `auto` | See §4 | BRouter for MTB/gravel/eMTB; ORS for road. Fallback to ORS when BRouter fails and `routing_service == auto`. |
| `ors` | ORS | |
| `brouter` | BRouter | |
| `graphhopper` | GraphHopper | Requires `GRAPHOPPER_API_KEY`. |
| `valhalla` | Valhalla/Stadia | Requires `VALHALLA_API_KEY`. |

**Loop (AUTO, BRouter path):** if BRouter returns no candidates, **fallback to ORS** loop generation.  
**Point-to-point / out-and-back (AUTO, BRouter path):** if BRouter throws, **fallback to ORS** for that shape.

---

## 4. Route shape × engine (when `routing_service` is explicit)

| `route_type` | `graphhopper` | `valhalla` | `brouter` | `ors` |
|--------------|----------------|------------|-----------|-------|
| `point_to_point` | GraphHopper direct | Valhalla direct | BRouter direct (or ORS fallback if AUTO) | ORS direct |
| `out_and_back` | GraphHopper OAB | Valhalla OAB | BRouter OAB (or ORS fallback if AUTO) | ORS OAB |
| `loop` | GraphHopper loop candidates | Valhalla loop candidates | BRouter loop candidates (or ORS fallback if AUTO) | ORS loop candidates |

---

## 5. Interactive point-to-point (`POST /api/routes/point-to-point`)

This path **does not** use `RouteConstraints` / `generate_route`. It:

1. Runs **ORS** and **BRouter** in parallel (always).
2. If `sport_type` ∈ {MTB, gravel, eMTB} **and** `GRAPHOPPER_API_KEY` is set, also runs **GraphHopper** (for metrics).
3. Picks the **winning geometry** between **ORS and BRouter** (score/heuristics in `routes.py`; see `point_to_point_router_selection.py`). GraphHopper is **not** currently scored into the winner.
4. Attaches **Valhalla `trace_attributes`** surface when `VALHALLA_API_KEY` is set (`_attach_valhalla_surface`).

**Surface source after attach:** `valhalla_trace` when trace succeeds; otherwise breakdown may remain router-estimated or unknown.

---

## 6. Observability (API)

| Field | Where | Meaning |
|-------|--------|---------|
| `router_used` | `PointToPointResponse` | Which engine produced the chosen geometry (`ors`, `brouter`, or `graphhopper` if it ever wins). |
| `surface_source` | `PointToPointResponse` | `valhalla_trace` when trace enriched; else `unknown` (or future sources). |
| `fallback_reason` | `PointToPointResponse` | Reserved for AUTO fallback reasons; optional. |

Structured logs (`structlog`) also emit `route_attempt`, `route_candidate_metrics`, `valhalla_surface_attach_*`, and `route_point_to_point_success`.

---

## 7. Required environment (for intended behavior)

| Key | Role |
|-----|------|
| `ORS_API_KEY` | ORS directions |
| `VALHALLA_API_KEY` | Valhalla route + surface trace (Stadia) |
| `GRAPHOPPER_API_KEY` | Optional GraphHopper on P2P |

---

## Changelog

- **2026-04-03:** Initial matrix aligned with `routing.py` + `routes.py` point-to-point.
