# John Router — True V1 Program

**Owner:** CPO (AI agent session)  
**Audience:** CEO, functional VPs  
**Last updated:** 2026-04-03  

## What “True V1” means

V1 is **not** every idea in `PRODUCT_DOCUMENTATION.md`. It is a **shippable product** where:

1. **Routing quality (P1)** is **measurable, repeatable, and defensible** across sport types and route shapes (loop, out-and-back, point-to-point).
2. **LLM-assisted planning (P2)** is **reliable**: intent is parsed correctly, the system **admits uncertainty**, timeouts degrade gracefully, and copy explains **what happened** (not generic fluff).

**V1 exit criteria (binary):**

| Criterion | Evidence |
|-----------|----------|
| **Routing** | Golden-set scenarios pass in CI or scripted checks; surface/elevation/validation agree with manual review for a defined region set |
| **Routers** | Documented engine policy per `sport_type` + `routing_service`; Stadia/Valhalla key present where surface trace is required; fallbacks logged and tested |
| **Chat planning** | Ride Brief Loop completes under timeout for standard prompts; no silent empty routes without user-visible explanation |
| **Quality bar** | Inspector shows **confidence + warnings** where data is thin; user never thinks a bad route is “blessed” |

---

## Executive team (roles)

| Role | Mandate | First deliverables |
|------|---------|-------------------|
| **CPO** | Scope V1, resolve tradeoffs, sequence P1 → P2 | This program, weekly CEO notes |
| **VP Engineering** | Routing pipeline, tests, perf, observability | Engine matrix, golden routes, CI gates |
| **VP Design** | Trust UI: quality signals, failure states, inspector clarity | Spec for “data confidence” surfaces |
| **VP Product / PM** | V1 user stories, acceptance, beta criteria | Short V1 story list + UAT refresh |
| **VP Data / Routing science** | Segment quality, Valhalla vs ORS vs BRouter behavior | Benchmark notebook + region fixtures |

---

## P1 — Deep routing quality (priority 1)

### Current technical reality (audit 2026-04-03)

- **Multi-engine:** `routing.py` orchestrates **BRouter** (MTB/gravel bias in AUTO), **ORS**, **GraphHopper**, **Valhalla** per `RoutingServiceType` and `route_type`.
- **Surface enrichment:** `_attach_valhalla_surface` + `trace_attributes` is wired through Valhalla/Stadia paths and several generation helpers; **point-to-point** API also races routers then attaches Valhalla surface (`routes.py`).
- **Downstream:** `/api/routes/generate` runs `generate_route` → per-candidate **metadata**, **analysis**, **validation**, **constraint scoring** (`routes.py`).
- **Gap risk:** Quality depends on **API keys** (`VALHALLA_API_KEY`, `ORS_API_KEY`, etc.) and **AUTO** vs explicit engine selection; behavior differs by path (manual map vs chat).

### P1 workstreams

1. **Router policy matrix** — **Done:** [`ROUTER_POLICY_MATRIX.md`](./ROUTER_POLICY_MATRIX.md) (`sport_type` × `route_type` × engine, P2P specifics, env keys).
2. **Golden routes** — Versioned fixtures (GeoJSON + expected bands for distance, surface %, max grade). Run in pytest or smoke script.
3. **Failure taxonomy** — Classify: no candidates, degraded surface, validation hard-fail, timeout; map each to **user-visible** messages (VP Design).
4. **Observability** — Structured logs + **`/routes/point-to-point`** and **`/routes/generate`** return `router_used`, `surface_source`, `fallback_reason` (see `ROUTER_POLICY_MATRIX.md`).

### P1 success metrics

- **Constraint hit rate** on golden set (distance ±X%, elevation band).
- **Surface unknown %** below threshold for defined urban + rural fixtures.
- **Zero** “looks fine on map but illegal/ absurd” routes in golden set (validation must catch).

---

## P2 — High intelligence & LLM quality (priority 2)

### Current technical reality

- **Primary chat path:** `RideBriefLoopService` (`ride_brief_loop.py`) — intent → brief → strategies → candidates → **optional** parallel **evaluation / improvement** with **knowledge chunks** and **feature flags** (e.g. `route_improvement`).
- **Legacy tool-calling:** Large `ai_copilot.py` still contains tool definitions and `_generate_route` logic used in some flows; **wrapper** at top marks old `chat` as deprecated — **consolidation** is a P2 engineering task to avoid two truths.
- **Chat API:** `chat.py` uses timeout + fallback when planning fails or returns no candidates.

### P2 workstreams

1. **Prompt + schema hardening** — Intent JSON and LLM-generated specs (`_llm_json` in `_compose_candidates`) need **validation**, retries, and **refusal** when parse fails.
2. **Single planning brain** — Make Ride Brief Loop the only production path; trim or gate duplicate copilot logic.
3. **Evaluation loop discipline** — When `route_improvement` is on, define **max latency** and **max LLM calls** per request.
4. **Transparency** — Final user message lists: intent summary, router/surface confidence, and what was improved (VP Design copy).

### P2 success metrics

- **Clarification rate** when ambiguous (target band from execution plan: ~10–20% of ambiguous asks).
- **Fallback rate** drops; **timeout rate** drops.
- **User-trust proxy:** fewer “wrong sport / wrong distance” reports in UAT.

---

## Dependencies

- P2 assumes P1 **routing is trustworthy**; otherwise the LLM will confidently describe bad geometry.
- Both depend on **keys and quotas** documented in `.env.example` and checked at startup where possible.

---

## 30-day sequence (proposal)

| Week | Focus |
|------|--------|
| 1 | P1: Golden routes + router matrix + fix top failures |
| 2 | P1: Validation + surface edge cases; Design: confidence UI spec |
| 3 | P2: Ride brief prompt/parse hardening; reduce duplicate copilot surface |
| 4 | Integration: UAT pass, freeze V1 scope, bugfix-only |

---

## CEO decisions needed

1. **V1 geography:** One region (e.g. Front Range + one urban) vs “US-wide” marketing — affects golden sets and Stadia coverage assumptions.
2. **LLM budget:** Max cost per planning session (drives parallel eval vs sequential).
3. **Ship channel:** Web-only V1 vs any mobile wrapper — affects scope for Design.

---

## Changelog

- **2026-04-03:** Program created from codebase audit and executive priorities (P1 routing, P2 LLM).
- **2026-04-03:** Added `ROUTER_POLICY_MATRIX.md` and P2P API observability fields (`router_used`, `surface_source`, `fallback_reason`).
- **2026-04-03:** `/routes/generate` candidates include the same observability fields; ORS parses include `source`; AUTO fallbacks tag `fallback_reason`; expanded golden tests + `candidate_routing_observability` helper.
