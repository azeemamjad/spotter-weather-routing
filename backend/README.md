# Weather routing API

Stateless Django 6.1.2 service for the Spotter Full Stack Developer assessment. The React application lives in the adjacent `frontend/` directory. This service needs Python 3.12 or newer; local verification used Python 3.14.7. No database, migrations, provider key, or fuel-price CSV is required for this separate assessment.

## Run and verify

From this directory, on Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python` instead. The frontend's development server proxies `/api` to port 8001. For a production build, Django serves the adjacent `frontend/dist/index.html` and WhiteNoise serves its assets. The repository's deployment files build that directory first.

Configuration comes from process environment variables; `.env.example` lists all names, but Django does **not** automatically load `.env` files. For example, PowerShell `$env:PROVIDER_TIMEOUT_SECONDS='15'` sets a variable for the current session. Production requires a private `SECRET_KEY`, `DEBUG=false`, and an explicit comma-separated `ALLOWED_HOSTS`. Do not commit real secrets. An Open-Meteo commercial deployment should set the licensed customer endpoint and its `OPEN_METEO_API_KEY`.

## API

`GET /api/health/` returns `{ "status": "ok", "service": "spotter-weather-routing", "version": "1.0.0" }`.

`POST /api/weather-route-plan/` requires `Content-Type: application/json`:

```json
{
  "origin": "Chicago, IL",
  "destination": "Detroit, MI",
  "departure_time": "2026-11-03T08:00:00-06:00",
  "load_weight_lb": 35000,
  "sample_interval_miles": 25,
  "mode": "live"
}
```

Use a departure within the next five days, with an explicit UTC offset. A one-hour grace period allows an already-filled form. Both locations also accept `{ "latitude": 41.8781, "longitude": -87.6298 }`. City search supports US state abbreviations and country/state names, displays the resolved choice, and is not street-address geocoding. The application selects the first provider result after the supplied state/country filter; use coordinates for ambiguous place names.

The response contains:

- `request`: resolved names/coordinates, UTC departure, load, spacing and mode.
- `routes`: stable IDs, actual GeoJSON `LineString` geometry, miles/seconds, and ordered checkpoints. Each checkpoint includes its UTC ETA, road-distance position, following segment length, normalized weather and risk with reasons.
- `summary` per route: exposure miles by level, Severe/High/No Travel/unknown miles, distance-weighted average risk, coverage, feasibility and worst risk.
- `recommendation`: chosen route ID and explanation, or `null` when no suitable option exists.
- `heatmap`: departure base time, integer hours 0 through 48, uniform corridor grid points with 49 weather/risk values, grid spacing, and hourly coverage.
- `metadata`: provider names, measured processing milliseconds, actual external **HTTP request** counts, per-item cache hits, warnings, model assumptions and explicit demo status. Weather service quota accounting may count multiple locations separately from HTTP batches.

Errors consistently use `{ "error": { "code": "...", "message": "..." } }`. Invalid input is 400, unresolved locations 404, unsupported/no road trips 422, invalid method 405, body over 16 KB 413, wrong content type 415, provider failure 502 and rate limiting 503. Successful partial forecast responses retain unknown cells and cannot recommend an incomplete route. Live failures never silently substitute demonstration data.

## Routing, sampling and forecasts

The adapter requests OSRM alternatives, full GeoJSON and per-segment distance/duration annotations. OSRM does not guarantee three alternatives: eight live US city-pair probes returned only one or two natural alternatives. If needed, this implementation makes up to two additional provider requests through explicit corridor waypoints 45 miles perpendicular to the base route's midpoint. All results are genuine routed road geometries; equivalent shapes are deduplicated, waypoint options are labeled, and a warning discloses the choice. This is not a claim that those options are the three fastest roads. If fewer than three distinct options remain, the actual count and limitation are returned.

Checkpoints interpolate along annotated cumulative **road distance** at 10/25/50 miles and include both endpoints once. Segment durations are rescaled to the authoritative route duration because OSRM annotation sums can omit turn penalties. If annotations are unavailable, geometry distance and constant-speed timing are used with an explicit warning. No traffic, driver breaks or truck restrictions are modeled.

Open-Meteo forecasts use UTC Unix timestamps, sustained 10m wind and hourly liquid `rain + showers` and snowfall. Wind is requested in mph; rain millimeters are divided by 25.4, snowfall centimeters by 2.54. Returned units are checked; unknown units or null values become unknown. For a checkpoint ETA, select the first hourly timestamp at or after arrival, whose precipitation accumulation covers the preceding hour. Wind uses the same interval-end sample. Out-of-horizon hours are never extrapolated.

## Risk and recommendation policy

Wind thresholds are 25/35/45/55 mph; rain is Moderate at 0.10, High at 0.25, Severe at 0.50 and No Travel only **above** 1.00 in/hr. Snow is Moderate at 0.5, High at 1.0, Severe at 2.0 and No Travel only **above** 3.0 in/hr. Shared printed boundaries use the higher severity; this is an explicit resolution of the assignment's overlapping ranges.

Wind 45–<55 mph with load **>30,000 lb** becomes No Travel; 35–<45 mph with load **>40,000 lb** becomes Severe. Wind ≥55 mph is No Travel at any load. Combined risk is the maximum component severity. Scores for averaging are Low=0, Moderate=1, High=2, Severe=3 and No Travel=4.

A checkpoint represents the following segment; destination contributes no invented miles. Any unknown or No Travel checkpoint, including arrival, excludes recommendation. Eligible routes are compared lexicographically by Severe miles, High miles, distance-weighted average score, then travel time. Unknown coverage never becomes Low risk, and an all-ineligible result has no recommendation.

## Heatmap and operating bounds

The corridor is 30 miles wide, 15 miles either side of the union of actual route geometries. It uses a uniform local equirectangular lattice, starting at 12-mile spacing and coarsening to at most 200 cells. This is a coarse relative-hazard view, not an exact weather surface or truck clearance map. Every cell has departure+0 through departure+48 hours prefetched. Changing the UI slider does not change checkpoint ETAs/recommendations and requires no network calls. Missing cells remain unknown.

To bound public-provider usage: routes are limited to 2,000 miles, total unique checkpoint/corridor locations to 800, coordinates to latitude −70..70 and longitude −170..170, and departure to five days ahead. Weather requests batch 40 points with at most three requests in flight. Every external request has a configured timeout and no automatic retry loop. Endpoint URLs are configurable.

File caches persist across local requests and processes: geocoding 24 hours, routes one hour, weather 15 minutes. Weather keys include endpoint, UTC day and coordinates rounded to four decimal places; all load/risk/time calculations rerun from cached raw forecasts, so changing those inputs cannot reuse a stale recommendation. There is no per-slider request.

## Explicit offline demonstration

Set `mode` to `demo` and choose **Chicago, IL → Detroit, MI**. This loads saved actual OSRM routes captured 2 November 2026 and generates deterministic **synthetic weather** for UI/review testing. The third saved road route uses a Grand Rapids corridor waypoint. Source request URLs are embedded in `trip_planning/fixtures/demo_routes.json`. Every response and the React UI label the synthetic data. Other locations are rejected in demo mode. This mode works without network access and must not be presented as a live forecast or used to plan real driving.

## Verification and measured performance

`manage.py test` currently runs 25 tests, including table-driven wind/rain/snow edges, strict load thresholds, combined/unknown risk, lexicographic ranking, exposure accounting, annotated timing across midnight, all three spacings, destination uniqueness, spatial corridor coverage, unit conversions, preceding-hour selection, malformed JSON, invalid inputs, provider failure, duplicated route rejection and a complete offline demo response with all 49 slider hours. External calls are mocked in automated tests.

A live integration smoke on 2 November 2026, Chicago→Detroit at 50-mile spacing, produced three distinct road routes (280.9, 298.1 and 331.2 miles), 129 corridor cells and complete ETA/49-hour weather coverage. Measured cold processing: **9.935 seconds**, with 2 routing + 4 weather-batch + 2 geocoding HTTP requests. Immediate repetition: **0.126 seconds**, zero external requests and 2 route / 146 location-forecast / 2 geocoding cache hits. Offline demo orchestration measured **107 ms** with 132 grid cells and zero external calls. These are observations from this workstation, not latency guarantees; forecast values, snapped city coordinates and provider availability can change.

Provider references and attribution: [OSRM API](https://project-osrm.org/docs/v5.24.0/api/#route-service), [Open-Meteo forecast documentation](https://open-meteo.com/en/docs), [Open-Meteo geocoding documentation](https://open-meteo.com/en/docs/geocoding-api), [Open-Meteo plan terms](https://open-meteo.com/en/pricing), and [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Open-Meteo's public endpoint is for evaluation/noncommercial use and has quotas; a paid license or self-hosting is needed for an appropriate commercial service. The public OSRM demo endpoint has no application uptime guarantee.

Hosting, accessible GitHub/Loom links, and the actual assessment work log are tracked in the parent project documentation; this backend README makes no submission claim.
