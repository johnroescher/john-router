"""Map routing engine exceptions to HTTP errors for /api/routes/generate."""
from __future__ import annotations

import re
from fastapi import HTTPException


def http_exception_from_routing_error(exc: Exception) -> HTTPException:
    """Classify a routing failure without always blaming OpenRouteService."""
    error_msg = str(exc)
    lower = error_msg.lower()

    if "401" in error_msg or "unauthorized" in lower or "invalid api" in lower:
        if "stadia" in lower or "valhalla" in lower:
            detail = "Routing provider rejected the request (check VALHALLA_API_KEY / Stadia configuration)."
        elif "graphhopper" in lower:
            detail = "GraphHopper API rejected the request (check GRAPHOPPER_API_KEY)."
        elif "brouter" in lower:
            detail = "BRouter request was rejected. Try again or switch routing profile."
        else:
            detail = (
                "OpenRouteService API key invalid or unauthorized. "
                "Check ORS_API_KEY in .env. https://openrouteservice.org/dev/#/signup"
            )
        return HTTPException(status_code=401, detail=detail)

    if "403" in error_msg or "forbidden" in lower:
        if "stadia" in lower or "valhalla" in lower:
            detail = "Valhalla/Stadia access denied. Verify API key permissions and quota."
        elif "graphhopper" in lower:
            detail = "GraphHopper access denied. Verify API key permissions."
        else:
            detail = "Routing API access denied. Your API key may lack required permissions."
        return HTTPException(status_code=403, detail=detail)

    if "429" in error_msg or "rate limit" in lower:
        return HTTPException(
            status_code=429,
            detail="Routing provider rate limit exceeded. Wait and retry.",
        )

    if re.search(r"\b503\b|unavailable|timeout", lower):
        return HTTPException(
            status_code=503,
            detail=f"Routing provider temporarily unavailable: {error_msg[:200]}",
        )

    if "valhalla" in lower or "stadia" in lower:
        return HTTPException(
            status_code=502,
            detail=f"Valhalla routing error: {error_msg[:300]}",
        )
    if "graphhopper" in lower:
        return HTTPException(
            status_code=502,
            detail=f"GraphHopper routing error: {error_msg[:300]}",
        )
    if "brouter" in lower:
        return HTTPException(
            status_code=502,
            detail=f"BRouter routing error: {error_msg[:300]}",
        )

    return HTTPException(status_code=500, detail=f"Routing service error: {error_msg[:500]}")
