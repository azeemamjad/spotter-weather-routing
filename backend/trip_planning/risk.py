"""Employer thresholds plus explicitly documented shared-boundary policy."""
import math

LEVELS = ("low", "moderate", "high", "severe", "no_travel")


def classify(weather, load_weight_lb):
    if weather is None or any(weather.get(k) is None or not math.isfinite(weather[k]) or weather[k] < 0 for k in ("wind_mph", "rain_in_hr", "snow_in_hr")):
        return {"level": "unknown", "score": None, "reasons": ["Forecast unavailable for this location and arrival time."]}
    wind, rain, snow = (weather[k] for k in ("wind_mph", "rain_in_hr", "snow_in_hr"))
    w = 4 if wind >= 55 else 3 if wind >= 45 else 2 if wind >= 35 else 1 if wind >= 25 else 0
    r = 4 if rain > 1 else 3 if rain >= .5 else 2 if rain >= .25 else 1 if rain >= .1 else 0
    s = 4 if snow > 3 else 3 if snow >= 2 else 2 if snow >= 1 else 1 if snow >= .5 else 0
    reasons = [f"Wind {wind:.1f} mph: {LEVELS[w].replace('_', ' ')}", f"Rain {rain:.3f} in/hr: {LEVELS[r].replace('_', ' ')}", f"Snow {snow:.3f} in/hr: {LEVELS[s].replace('_', ' ')}"]
    if 45 <= wind < 55 and load_weight_lb > 30000:
        w = 4
        reasons.append("Wind ≥45 mph with load >30,000 lb: no travel.")
    elif 35 <= wind < 45 and load_weight_lb > 40000:
        w = 3
        reasons.append("Wind ≥35 mph with load >40,000 lb: severe.")
    score = max(w, r, s)
    return {"level": LEVELS[score], "score": score, "reasons": reasons}


def summarize(checkpoints, distance_miles):
    exposure = dict.fromkeys((*LEVELS, "unknown"), 0.0)
    weighted = 0.0
    for checkpoint in checkpoints:
        miles = checkpoint["segment_miles"]
        risk = checkpoint["risk"]
        exposure[risk["level"]] += miles
        if risk["score"] is not None:
            weighted += miles * risk["score"]
    known = max(0.0, distance_miles - exposure["unknown"])
    # A destination is a terminal checkpoint, but a dangerous/unknown arrival still
    # prevents recommending the trip even though it represents zero extra miles.
    unknown_checkpoint = any(cp["risk"]["level"] == "unknown" for cp in checkpoints)
    blocked_checkpoint = any(cp["risk"]["level"] == "no_travel" for cp in checkpoints)
    known_scores = [cp["risk"]["score"] for cp in checkpoints if cp["risk"]["score"] is not None]
    return {
        "severe_miles": exposure["severe"], "high_miles": exposure["high"],
        "no_travel_miles": exposure["no_travel"], "unknown_miles": exposure["unknown"],
        "average_risk": weighted / distance_miles if distance_miles > 0 and not unknown_checkpoint else None,
        "coverage_percent": max(0.0,min(100.0,100 * known / distance_miles)) if distance_miles else (0 if unknown_checkpoint else 100),
        "feasible": not unknown_checkpoint and not blocked_checkpoint,
        "worst_risk": "unknown" if unknown_checkpoint else LEVELS[max(known_scores, default=0)],
        "exposure_miles": exposure,
    }


def recommend(routes):
    feasible = [r for r in routes if r["summary"]["feasible"]]
    if not feasible:
        return {"route_id": None, "reason": "No suitable route: every option has No Travel conditions or incomplete ETA forecasts."}
    best = min(feasible, key=lambda r: (r["summary"]["severe_miles"], r["summary"]["high_miles"], r["summary"]["average_risk"], r["duration_seconds"]))
    return {"route_id": best["id"], "reason": "Among routes with complete forecasts and no No Travel checkpoints, this route has the fewest Severe miles, then High miles, then lowest distance-weighted average risk, then shortest travel time."}
