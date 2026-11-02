"""Replaceable, bounded provider adapters with persistent per-location caches."""
import bisect
import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from django.conf import settings
from django.core.cache import cache
from .errors import PlanningError
from .geometry import interpolate, route_arrays


def cache_key(kind, value):
    return f"spotter-weather-v1:{kind}:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fetch_json(url, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "SpotterWeatherAssessment/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=settings.PROVIDER_TIMEOUT_SECONDS) as response:
            if int(response.headers.get("Content-Length", 0)) > 12_000_000:
                raise PlanningError("provider_response_too_large", "Provider response exceeded the configured safety bound.", 502)
            body = response.read(12_000_001)
            if len(body) > 12_000_000:
                raise PlanningError("provider_response_too_large", "Provider response exceeded the configured safety bound.", 502)
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        raise PlanningError("provider_rate_limit" if exc.code == 429 else "provider_http_error", f"External provider returned HTTP {exc.code}. Please retry later.", 503 if exc.code == 429 else 502) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise PlanningError("provider_unavailable", "External provider timed out or returned an invalid response. Please retry later.", 502) from exc


def location_key(point):
    return f"{point['latitude']:.4f},{point['longitude']:.4f}"


STATES = dict(zip("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(), "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming".split("|")))


def resolve_location(value, stats):
    if isinstance(value, dict):
        try:
            if isinstance(value.get("latitude"), bool) or isinstance(value.get("longitude"), bool):
                raise ValueError
            lat, lon = float(value["latitude"]), float(value["longitude"])
        except (KeyError, TypeError, ValueError):
            raise PlanningError("invalid_location", "Coordinate locations require numeric latitude and longitude.")
        if not math.isfinite(lat) or not math.isfinite(lon) or not -70 <= lat <= 70 or not -170 <= lon <= 170:
            raise PlanningError("unsupported_location", "Supported coordinates are latitude −70..70 and longitude −170..170; polar/dateline routing is outside this demo's scope.")
        return {"name": f"{lat:.4f}, {lon:.4f}", "latitude": lat, "longitude": lon}
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 160:
        raise PlanningError("invalid_location", "Provide a city name or an explicit latitude/longitude object.")
    parts = [x.strip() for x in value.split(",") if x.strip()]
    key = cache_key("geocoding", [settings.OPEN_METEO_GEOCODING_URL, value.strip().casefold()])
    saved = cache.get(key)
    if saved is not None:
        stats["cache_hits"]["geocoding"] += 1
        return saved
    stats["provider_requests"]["geocoding"] += 1
    params = {"name": parts[0], "count": 10, "language": "en", "format": "json"}
    state = STATES.get(parts[1].upper()) if len(parts) > 1 else None
    if state:
        params["countryCode"] = "US"
    data = fetch_json(settings.OPEN_METEO_GEOCODING_URL, params)
    if not isinstance(data,dict) or not isinstance(data.get("results",[]),list):
        raise PlanningError("invalid_geocoding_response","Geocoding provider returned an invalid response.",502)
    results = [r for r in data.get("results",[]) if isinstance(r,dict) and "latitude" in r and "longitude" in r]
    if state:
        results = [r for r in results if r.get("admin1", "").casefold() == state.casefold()]
    elif len(parts) > 1:
        suffix = parts[-1].casefold()
        matches = [r for r in results if suffix in {str(r.get(k, "")).casefold() for k in ("admin1", "country", "country_code")}]
        if matches:
            results = matches
        elif suffix not in ("usa", "us", "united states"):
            raise PlanningError("location_not_found", f"No city matched {value!r}. Try city, state abbreviation or coordinates.", 404)
    if not results:
        raise PlanningError("location_not_found", f"No city matched {value!r}. Try city, state abbreviation or coordinates.", 404)
    result = results[0]
    resolved = resolve_location({"latitude": result["latitude"], "longitude": result["longitude"]}, stats)
    resolved["name"] = ", ".join(str(result[k]) for k in ("name", "admin1", "country_code") if result.get(k))
    cache.set(key, resolved, 86400)
    return resolved


def _route_request(points, alternatives, stats):
    coordinates = ";".join(f"{p['longitude']:.6f},{p['latitude']:.6f}" for p in points)
    key = cache_key("route", [settings.OSRM_URL, coordinates, alternatives])
    result = cache.get(key)
    if result is not None:
        stats["cache_hits"]["routing"] += 1
        return result
    stats["provider_requests"]["routing"] += 1
    result = fetch_json(settings.OSRM_URL + "/route/v1/driving/" + coordinates, {
        "alternatives": alternatives, "geometries": "geojson", "overview": "full", "steps": "false", "annotations": "distance,duration",
    })
    if not isinstance(result,dict):
        raise PlanningError("invalid_route_response","Routing provider returned an invalid response.",502)
    if result.get("code") != "Ok" or not result.get("routes"):
        raise PlanningError("no_route", "No driving route could be found between these locations.", 422)
    try:
        for route in result["routes"]:
            if not all(isinstance(route[k],(int,float)) and math.isfinite(route[k]) and route[k] > 0 for k in ("distance","duration")):
                raise ValueError
            geometry=route["geometry"]
            if geometry["type"]!="LineString" or len(geometry["coordinates"])<2:
                raise ValueError
            if not all(len(c)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in c) for c in geometry["coordinates"]):
                raise ValueError
    except (KeyError,TypeError,ValueError):
        raise PlanningError("invalid_route_response","Routing provider returned invalid road geometry or route totals.",502)
    cache.set(key, result, 3600)
    return result


def route_signature(route):
    coords = route["geometry"]["coordinates"]
    # A provider may return the same geometry with a few extra points. Sample by
    # distance at 21 positions and quantize to ~1km to reject equivalent options.
    points, miles, seconds, _ = route_arrays(route)
    shape = [tuple(round(v, 2) for v in interpolate(points,miles,seconds,miles[-1]*i/20)[:2]) for i in range(21)]
    return json.dumps(shape)


def get_routes(origin, destination, stats, warnings):
    routes = []
    signatures = set()
    for route in _route_request([origin, destination], "3", stats)["routes"]:
        signature = route_signature(route)
        if signature not in signatures:
            signatures.add(signature)
            routes.append(route)
    if len(routes) < 3:
        warnings.append("OSRM returned fewer than three natural alternatives. Additional distinct options are provider-routed via explicit corridor waypoints; these are not claims of three fastest or truck-legal alternatives.")
        points, miles, seconds, _ = route_arrays(routes[0])
        mid_lon, mid_lat, _ = interpolate(points,miles,seconds,miles[-1]/2)
        cos_lat = max(.1, math.cos(math.radians(mid_lat)))
        dx = (destination["longitude"]-origin["longitude"]) * cos_lat
        dy = destination["latitude"]-origin["latitude"]
        norm = math.hypot(dx,dy) or 1
        for direction in (1,-1):
            if len(routes) >= 3:
                break
            via = {"latitude":mid_lat+direction*(dx/norm)*45/69.093,"longitude":mid_lon-direction*(dy/norm)*45/(69.093*cos_lat)}
            try:
                candidate = _route_request([origin,via,destination], "false", stats)["routes"][0]
                signature = route_signature(candidate)
                if signature not in signatures:
                    signatures.add(signature)
                    candidate = dict(candidate, _label=f"Via corridor waypoint {'A' if direction == 1 else 'B'}", _waypoint=via)
                    routes.append(candidate)
            except PlanningError:
                warnings.append("One corridor waypoint could not be routed; only successful distinct options are shown.")
    if len(routes) < 3:
        warnings.append(f"Only {len(routes)} distinct driving route(s) are available. This trip does not demonstrate the required three options.")
    return routes[:3]


def _number(value):
    return float(value) if isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0 else None


def normalize_forecast(data):
    if not isinstance(data,dict) or not isinstance(data.get("hourly",{}),dict) or not isinstance(data.get("hourly_units",{}),dict):
        raise PlanningError("invalid_weather_response","Weather provider returned invalid hourly data.",502)
    hourly, units = data.get("hourly", {}), data.get("hourly_units", {})
    result = {"times": [], "values": []}
    for i, timestamp in enumerate(hourly.get("time", [])):
        def read(name):
            values = hourly.get(name, [])
            return _number(values[i]) if i < len(values) else None
        wind,rain,showers,snow = (read(k) for k in ("wind_speed_10m","rain","showers","snowfall"))
        wind_unit=units.get("wind_speed_10m")
        rain_unit, shower_unit, snow_unit = units.get("rain"),units.get("showers"),units.get("snowfall")
        wind = wind if wind_unit in ("mp/h","mph") else wind/1.609344 if wind is not None and wind_unit=="km/h" else wind*2.2369362920544 if wind is not None and wind_unit=="m/s" else None
        rain = rain/25.4 if rain is not None and rain_unit=="mm" else rain if rain_unit in ("inch","in") else None
        showers = showers/25.4 if showers is not None and shower_unit=="mm" else showers if shower_unit in ("inch","in") else None
        snow = snow/2.54 if snow is not None and snow_unit=="cm" else snow if snow_unit in ("inch","in") else None
        if not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp):
            continue
        result["times"].append(timestamp)
        result["values"].append(None if any(v is None for v in (wind,rain,showers,snow)) else {
            "wind_mph":wind,"rain_in_hr":rain+showers,"snow_in_hr":snow,
            "forecast_time":datetime.fromtimestamp(timestamp,tz=timezone.utc).isoformat().replace("+00:00","Z"),
        })
    return result


def forecast_at(series, when):
    timestamp = when.timestamp()
    times = series.get("times", [])
    i = bisect.bisect_left(times, timestamp)
    # Accumulation at H describes (H-1h,H]; use that covering interval. Never
    # extrapolate beyond the returned data or skip over a missing hour.
    if i >= len(times) or timestamp < times[0] or times[i]-timestamp >= 3600:
        return None
    return series["values"][i]


def get_forecasts(points, stats):
    unique = {location_key(point): point for point in points}
    forecasts, missing = {}, []
    day = datetime.now(timezone.utc).date().isoformat()
    for key, point in unique.items():
        saved = cache.get(cache_key("weather", [settings.OPEN_METEO_URL,day,key]))
        if saved is not None:
            forecasts[key] = saved
            stats["cache_hits"]["weather"] += 1
        else:
            missing.append((key,point))
    batches=[missing[i:i+40] for i in range(0,len(missing),40)]
    stats["provider_requests"]["weather"] += len(batches)

    def fetch_batch(batch):
        params={"latitude":",".join(f"{p['latitude']:.4f}" for _,p in batch),
                "longitude":",".join(f"{p['longitude']:.4f}" for _,p in batch),
                "hourly":"wind_speed_10m,rain,showers,snowfall","wind_speed_unit":"mph","precipitation_unit":"mm",
                "timeformat":"unixtime","timezone":"UTC","forecast_days":8,"past_days":1}
        if settings.OPEN_METEO_API_KEY:
            params["apikey"]=settings.OPEN_METEO_API_KEY
        payload=fetch_json(settings.OPEN_METEO_URL,params)
        values=payload if isinstance(payload,list) else [payload]
        if len(values)!=len(batch):
            raise PlanningError("invalid_weather_response","Weather provider returned a different number of forecast locations than requested.",502)
        return [(key,normalize_forecast(value)) for (key,_),value in zip(batch,values)]

    # At most three in-flight requests. Slider changes use this already-fetched
    # data in the browser and never trigger requests.
    if batches:
        with ThreadPoolExecutor(max_workers=3) as executor:
            for result in executor.map(fetch_batch,batches):
                for key,series in result:
                    forecasts[key]=series
                    cache.set(cache_key("weather",[settings.OPEN_METEO_URL,day,key]),series,900)
    return forecasts
