"""Application orchestration. No provider calls in deterministic risk functions."""
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .errors import PlanningError
from .geometry import corridor_grid, sample_route, METERS_PER_MILE
from .providers import resolve_location, get_routes, get_forecasts, forecast_at, location_key
from .risk import classify, summarize, recommend

ASSUMPTIONS = [
    "General driving routes, not commercial-truck height, weight, hazmat, or road-legality certification. Load affects weather risk only.",
    "At a shared precipitation boundary use the higher severity; rain >1.00 and snow >3.00 in/hr alone trigger their No Travel thresholds. Load comparisons are strict >.",
    "Combined checkpoint risk is the maximum wind, rain, snow, and load severity. Unknown forecasts are not Low. Any No Travel or unknown checkpoint, including arrival, excludes recommendation.",
    "Each checkpoint represents the following road-distance segment; destination is terminal. Risk miles use segment lengths, not point counts. Average scores are Low=0, Moderate=1, High=2, Severe=3, No Travel=4.",
    "ETA interpolation uses OSRM annotated segment travel times, rescaled to include the route's total turn penalties. If annotations are absent, distance-proportional constant-speed timing is disclosed.",
    "Wind is sustained wind at 10m. Liquid rain includes rain + showers. Rain mm/hour is divided by 25.4; snowfall cm/hour by 2.54. Snow depth and snow water equivalent are not used.",
    "Hourly precipitation at timestamp H covers the preceding hour; choose the first forecast timestamp at or after ETA and use wind at that same interval end. Missing/out-of-horizon values remain unknown.",
    "The heatmap samples a uniform spatial grid within a 30-mile-wide corridor and shows relative hazard, not a precise road-segment risk surface. It is separate from ETA checkpoint risk.",
    "Heatmap hours 0–48 are anchored at selected departure. Changing this view does not change departure, ETAs, or recommendation and requires no new weather calls.",
    "Live city search selects the provider's first match after any supplied US state/country filter and displays its resolved name. Explicit coordinates avoid ambiguous city names. Polar/dateline regions and routes over 2,000 miles are unsupported.",
]


def validate_request(data, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(data, dict):
        raise PlanningError("invalid_request", "The request body must be a JSON object.")
    for field in ("origin", "destination", "departure_time", "load_weight_lb"):
        if field not in data:
            raise PlanningError("missing_field", f"{field} is required.")
    try:
        departure = datetime.fromisoformat(data["departure_time"].replace("Z", "+00:00"))
        if departure.tzinfo is None or departure.utcoffset() is None:
            raise ValueError
        departure = departure.astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        raise PlanningError("invalid_departure_time", "departure_time must be ISO 8601 with an explicit timezone offset or Z.")
    if isinstance(data["load_weight_lb"], bool):
        raise PlanningError("invalid_load", "load_weight_lb must be a number from 0 to 100,000.")
    try:
        load = float(data["load_weight_lb"])
    except (TypeError,ValueError):
        raise PlanningError("invalid_load", "load_weight_lb must be a number from 0 to 100,000.")
    if not math.isfinite(load) or not 0 <= load <= 100000:
        raise PlanningError("invalid_load", "load_weight_lb must be a finite number from 0 to 100,000.")
    interval = data.get("sample_interval_miles",25)
    if isinstance(interval,bool) or interval not in (10,25,50):
        raise PlanningError("invalid_interval", "sample_interval_miles must be 10, 25, or 50.")
    mode = data.get("mode", "live")
    if mode not in ("live","demo"):
        raise PlanningError("invalid_mode", "mode must be live or demo.")
    if mode == "live" and not now-timedelta(hours=1) <= departure <= now+timedelta(days=5):
        raise PlanningError("unsupported_departure", "Live departure must be within the next 5 days (with a one-hour grace period). The heatmap needs a further 48 hours of forecast coverage.")
    return departure,load,interval,mode


def demo_location(value, expected, latitude, longitude):
    if isinstance(value,str):
        matches=value.split(",")[0].strip().casefold() == expected.casefold()
    elif isinstance(value,dict):
        try:
            matches=abs(float(value["latitude"])-latitude)<.2 and abs(float(value["longitude"])-longitude)<.2
        except (KeyError,ValueError,TypeError):
            matches=False
    else:
        matches=False
    if not matches:
        raise PlanningError("demo_route_only", "Offline demo mode is the saved Chicago, IL → Detroit, MI trip. Use live mode for other locations.")
    return {"name":f"{expected}, {'IL' if expected=='Chicago' else 'MI'}, US","latitude":latitude,"longitude":longitude}


def demo_weather(point, when, departure):
    """Clearly synthetic, deterministic moving field; never used by live mode."""
    hour=(when-departure).total_seconds()/3600
    lat,lon=point["latitude"],point["longitude"]
    storm=math.exp(-((lat-42.05)/.28)**2-((lon+85.9)/.85)**2)
    wind=18 + 6*(1+math.sin((lon+90)*2+hour/9))/2 + 28*storm*(.75+.25*math.sin(hour/10+.5))
    rain=.012 + .38*storm*(.7+.3*math.sin(hour/10+1))
    snow=max(0,.72*math.exp(-((lat-43.15)/.22)**2)*(.5+.5*math.sin(hour/14+.3)))
    forecast_time=datetime.fromtimestamp(math.ceil(when.timestamp()/3600)*3600,tz=timezone.utc)
    return {"wind_mph":wind,"rain_in_hr":rain,"snow_in_hr":snow,"forecast_time":forecast_time.isoformat().replace("+00:00","Z")}


def build_plan(data):
    started=time.perf_counter()
    departure,load,interval,mode=validate_request(data)
    stats={"provider_requests":dict.fromkeys(("routing","weather","geocoding"),0),"cache_hits":dict.fromkeys(("routing","weather","geocoding"),0)}
    warnings=[]
    if mode == "demo":
        origin=demo_location(data["origin"],"Chicago",41.8781,-87.6298)
        destination=demo_location(data["destination"],"Detroit",42.3314,-83.0458)
        path=Path(__file__).parent/"fixtures"/"demo_routes.json"
        provider_data=json.loads(path.read_text(encoding="utf-8"))
        raw_routes=provider_data["routes"][:3]
        warnings.append("OFFLINE DEMO: saved real OSRM Chicago–Detroit road geometries captured 2026-11-02; weather is synthetic and must not be used for driving decisions. The third route uses a Grand Rapids corridor waypoint.")
    else:
        origin=resolve_location(data["origin"],stats)
        destination=resolve_location(data["destination"],stats)
        if abs(origin["latitude"]-destination["latitude"])+abs(origin["longitude"]-destination["longitude"]) < 1e-5:
            raise PlanningError("same_location", "Choose different origin and destination locations.",422)
        raw_routes=get_routes(origin,destination,stats,warnings)
    routes=[]
    for i,raw in enumerate(raw_routes):
        route_id=f"route-{i+1}"
        checkpoints,annotated=sample_route(raw,interval,departure,route_id)
        if not annotated:
            warnings.append(f"{route_id}: missing segment annotations; ETA uses a constant-speed distance-proportional approximation.")
        routes.append({"id":route_id,"name":raw.get("_label",f"Route {i+1}"),"geometry":raw["geometry"],
                       "distance_miles":raw["distance"]/METERS_PER_MILE,"duration_seconds":raw["duration"],"checkpoints":checkpoints,
                       "via_waypoint":raw.get("_waypoint")})
    grid,spacing=corridor_grid(raw_routes)
    all_points=[cp for route in routes for cp in route["checkpoints"]]+grid
    if len({location_key(p) for p in all_points}) > 800:
        raise PlanningError("too_many_samples","This trip requires too many forecast points. Choose a shorter trip or larger checkpoint interval.",422)
    forecasts=get_forecasts(all_points,stats) if mode=="live" else None

    def weather(point, when):
        return demo_weather(point,when,departure) if mode=="demo" else forecast_at(forecasts.get(location_key(point),{}),when)

    for route in routes:
        for checkpoint in route["checkpoints"]:
            when=datetime.fromisoformat(checkpoint["eta"].replace("Z","+00:00"))
            checkpoint["weather"]=weather(checkpoint,when)
            checkpoint["risk"]=classify(checkpoint["weather"],load)
        route["summary"]=summarize(route["checkpoints"],route["distance_miles"])
        if route["summary"]["coverage_percent"] < 100 or any(cp["risk"]["level"]=="unknown" for cp in route["checkpoints"]):
            warnings.append(f"{route['name']}: incomplete ETA forecasts; this route cannot be recommended.")
    for point in grid:
        values=[]
        for hour in range(49):
            sample=weather(point,departure+timedelta(hours=hour))
            risk=classify(sample,load)
            values.append(None if sample is None else {"wind_mph":sample["wind_mph"],"rain_in_hr":sample["rain_in_hr"],"snow_in_hr":sample["snow_in_hr"],"risk":risk["level"],"score":risk["score"]})
        point["values"]=values
    coverage=[sum(point["values"][hour] is not None for point in grid)/len(grid)*100 if grid else 0 for hour in range(49)]
    if any(value < 100 for value in coverage):
        warnings.append("Some corridor forecast hours are unavailable. Missing heatmap cells are unknown, not low risk.")
    return {
        "request":{"origin":origin,"destination":destination,"departure_time":departure.isoformat().replace("+00:00","Z"),"load_weight_lb":load,"sample_interval_miles":interval,"mode":mode},
        "routes":routes,"recommendation":recommend(routes),
        "heatmap":{"base_time":departure.isoformat().replace("+00:00","Z"),"hours":list(range(49)),"corridor_width_miles":30,"grid_spacing_miles":spacing,"coverage_percent_by_hour":coverage,"points":grid},
        "metadata":{"providers":{"routing":"OSRM saved road geometries" if mode=="demo" else "OSRM","weather":"Synthetic demonstration weather" if mode=="demo" else "Open-Meteo","geocoding":"Fixed demo endpoints" if mode=="demo" else "Open-Meteo / explicit coordinates"},
                    "elapsed_ms":round((time.perf_counter()-started)*1000,2),**stats,"warnings":warnings,"assumptions":ASSUMPTIONS,"demo":mode=="demo"},
    }
