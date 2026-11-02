"""Distance-aligned checkpoints and a uniformly spaced corridor sample grid."""
import bisect
import math
from datetime import timedelta
from .errors import PlanningError

METERS_PER_MILE = 1609.344
EARTH_RADIUS_MILES = 3958.7613


def haversine(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    x = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1, math.sqrt(x)))


def cumulative(values):
    out = [0.0]
    for value in values:
        out.append(out[-1] + value)
    return out


def route_arrays(route):
    coords = route["geometry"]["coordinates"]
    if len(coords) < 2:
        raise PlanningError("invalid_route", "Routing provider returned an incomplete geometry.", 502)
    distances = [d for leg in route.get("legs", []) for d in leg.get("annotation", {}).get("distance", [])]
    durations = [d for leg in route.get("legs", []) for d in leg.get("annotation", {}).get("duration", [])]
    valid_values = all(isinstance(v,(int,float)) and math.isfinite(v) and v >= 0 for v in distances+durations)
    annotated = valid_values and len(distances) == len(coords)-1 and len(durations) == len(coords)-1 and sum(distances) > 0 and sum(durations) > 0
    if not annotated:
        distances = [haversine(a, b) * METERS_PER_MILE for a, b in zip(coords, coords[1:])]
        durations = distances[:]
    total_distance = sum(distances)
    total_duration = sum(durations)
    if total_distance <= 0 or total_duration <= 0:
        raise PlanningError("route_too_short", "Choose two different locations with a nonzero driving route.", 422)
    # OSRM segment timings omit some turn penalties. Preserve relative annotated
    # speeds while rescaling to the provider's authoritative route totals.
    miles = cumulative([d / total_distance * route["distance"] / METERS_PER_MILE for d in distances])
    seconds = cumulative([d / total_duration * route["duration"] for d in durations])
    return coords, miles, seconds, annotated


def interpolate(coords, miles, seconds, target):
    i = min(max(0, bisect.bisect_right(miles, target)-1), len(coords)-2)
    span = miles[i+1] - miles[i]
    ratio = (target-miles[i])/span if span > 0 else 0
    lon = coords[i][0] + ratio * (coords[i+1][0]-coords[i][0])
    lat = coords[i][1] + ratio * (coords[i+1][1]-coords[i][1])
    elapsed = seconds[i] + ratio * (seconds[i+1]-seconds[i])
    return lon, lat, elapsed


def sample_route(route, interval, departure, route_id):
    coords, miles, seconds, annotated = route_arrays(route)
    total = miles[-1]
    if total > 2000:
        raise PlanningError("route_too_long", "This assessment service supports routes up to 2,000 miles to bound forecast sampling.", 422)
    positions = [float(i*interval) for i in range(int(total//interval)+1)]
    if total - positions[-1] > 1e-7:
        positions.append(total)
    else:
        positions[-1] = total
    checkpoints = []
    for i, position in enumerate(positions):
        lon, lat, elapsed = interpolate(coords, miles, seconds, position)
        checkpoints.append({"id": f"{route_id}-cp-{i}", "longitude": lon, "latitude": lat, "distance_miles": position,
                            "segment_miles": positions[i+1]-position if i+1 < len(positions) else 0.0,
                            "eta": (departure+timedelta(seconds=elapsed)).isoformat().replace("+00:00", "Z")})
    return checkpoints, annotated


def point_segment_distance(px, py, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((px-a[0])*dx + (py-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(px-a[0]-t*dx, py-a[1]-t*dy)


def corridor_grid(routes, width_miles=30):
    coords = [c for route in routes for c in route["geometry"]["coordinates"]]
    ref_lat = sum(c[1] for c in coords)/len(coords)
    lon_scale = 69.093 * max(.1, math.cos(math.radians(ref_lat)))
    lat_scale = 69.093
    lines = []
    # Preserve actual shape at <=5-mile intervals; use provider distances rather
    # than sampling a fixed count of points on very uneven geometries.
    for route in routes:
        xy, miles, seconds, _ = route_arrays(route)
        positions = [i*5 for i in range(int(miles[-1]//5)+1)] + [miles[-1]]
        points = [interpolate(xy,miles,seconds,p)[:2] for p in positions]
        projected = [(c[0]*lon_scale,c[1]*lat_scale) for c in points]
        lines.extend(zip(projected, projected[1:]))
    half = width_miles/2
    xs, ys = [c[0]*lon_scale for c in coords], [c[1]*lat_scale for c in coords]
    spacing = 12.0
    while True:
        minx,maxx = math.floor((min(xs)-half)/spacing)*spacing, max(xs)+half
        miny,maxy = math.floor((min(ys)-half)/spacing)*spacing, max(ys)+half
        nx,ny = int((maxx-minx)//spacing)+1,int((maxy-miny)//spacing)+1
        if nx*ny > 15000:
            spacing *= 1.3
            continue
        samples=[]
        for ix in range(nx):
            x=minx+ix*spacing
            for iy in range(ny):
                y=miny+iy*spacing
                if any(point_segment_distance(x,y,a,b) <= half for a,b in lines):
                    samples.append({"longitude":round(x/lon_scale,5),"latitude":round(y/lat_scale,5)})
        if len(samples) <= 200:
            return samples, spacing
        spacing *= 1.2
