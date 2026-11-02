# Weather-aware truck routing

React + Django implementation of Spotter's Full Stack Developer assessment. Enter origin, destination, departure time, load in pounds and a 10/25/50-mile sampling interval. Compare real road-route options, inspect arrival-time checkpoint weather and explore a forecast heatmap across the trip corridor from departure through +48 hours.

The default **Live forecast** mode uses external providers. **Offline demonstration** is an explicitly labeled Chicago–Detroit trip with saved real OSRM road geometry and synthetic weather. It works without network requests to routing/weather APIs, but map tiles still need internet. Synthetic weather is never a substitute for a live forecast.

## Prerequisites and startup

- Python 3.14; pinned Python dependencies in `backend/requirements.txt`.
- Node.js 22 with npm; pinned JavaScript dependencies and `frontend/package-lock.json`.
- Internet access for live routing, weather, geocoding and basemap tiles.

From the full-stack project directory, use one terminal for Django:

```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Use another terminal for React:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to Django on port 8001, so development and production use the same relative API URL. The weather API is stateless and requires no database or migrations. In the combined workspace, `..\start.ps1 -Project Fullstack -Setup` automates installation and starts hidden processes with local logs.

`backend/.env.example` lists environment variable names and non-secret examples. These are process environment variables; the weather backend does **not** automatically load a `.env` file. Local defaults work without configuration. Set actual values through PowerShell `$env:NAME = 'value'`, your process manager or your deployment provider. Production requires a private `SECRET_KEY`, `DEBUG=false` and the actual comma-separated `ALLOWED_HOSTS` hostnames. An optional Open-Meteo API key and provider endpoint URLs can be configured in the backend; no private credential belongs in the frontend.

## API

`GET /api/health/` returns service health. `POST /api/weather-route-plan/` accepts JSON:

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

Use a departure within the supported current window when running the example. The browser interprets its date/time input in its displayed local timezone and sends an explicit UTC timestamp. API callers must include `Z` or a numeric offset. Location strings use city search and display the selected match; explicit `{ "latitude": 41.8781, "longitude": -87.6298 }` objects avoid ambiguous names.

The response includes resolved request data; routes with GeoJSON `LineString` geometry, road distance and duration; checkpoint locations, ETAs, normalized weather and risk reasons; exposure-mile summaries; recommendation; 49-hour corridor samples; provider request/cache counts, measured elapsed time, warnings and assumptions. Errors use `{ "error": { "code": "...", "message": "..." } }` with an appropriate non-200 status. Invalid inputs, unavailable providers and incomplete forecasts remain visible.

For deterministic interface review, send the same Chicago–Detroit request with `"mode": "demo"`, or choose **Explore a sample trip** in the app. The demonstration banner and response metadata identify the saved geometries and synthetic weather.

## Risk, ETA and recommendation model

| Hazard | Moderate starts at | High starts at | Severe starts at | No Travel |
| --- | --- | --- | --- | --- |
| Sustained wind at 10 m | 25 mph | 35 mph | 45 mph | ≥55 mph |
| Rain plus showers | 0.10 in/hr | 0.25 in/hr | 0.50 in/hr | >1.00 in/hr |
| Snowfall | 0.50 in/hr | 1.00 in/hr | 2.00 in/hr | >3.00 in/hr |

Values below Moderate are Low. Shared precipitation boundaries use the higher severity; the employer's strict rain/snow No Travel thresholds remain strict. Exactly 1.00 in/hr rain and 3.00 in/hr snow are Severe. Wind 45–54.999 mph with load **>30,000 lb** is No Travel; wind 35–44.999 mph with load **>40,000 lb** is Severe. The comparisons are strict; equality at the load thresholds does not activate an override. A checkpoint uses the maximum of its individual hazard/load risks.

Checkpoints follow cumulative **road** distance and include origin and destination once. Their ETAs interpolate OSRM segment duration annotations; annotated times are rescaled to include the total route duration's turn penalties. If annotations are absent, the response discloses distance-proportional timing. Each checkpoint represents its following segment; the destination adds no extra risk miles. Hourly precipitation describes the preceding hour, so weather selection uses the first hourly timestamp at or after ETA. Rain/showers millimeters are divided by 25.4 and snowfall centimeters by 2.54; timestamps are UTC.

Routes with any No Travel or unknown checkpoint, including arrival, cannot be recommended. Remaining routes are compared lexicographically by **Severe miles, High miles, distance-weighted average risk, then travel time**. Scores for the average are Low 0, Moderate 1, High 2, Severe 3, No Travel 4. Missing weather remains Unknown. If all options are unsuitable, the app explains that no suitable route exists.

The heatmap samples a uniform grid within a **30-mile-wide corridor**, with at most 200 spatial cells. It displays relative hazard at departure + the selected 0–48 integer hour. Moving the slider changes the cached visual layer without fetching forecasts, changing checkpoint ETAs or recalculating the route recommendation. Heat intensity is a visual exposure aid; exact checkpoint/segment risk categories are shown separately.

## Providers and limits

- [OSRM Route service](https://project-osrm.org/docs/v5.24.0/api/#route-service) supplies driving routes and full geometry/annotations. Requested alternatives are not guaranteed. The backend can request an additional corridor waypoint when needed to seek a third genuinely distinct road route, and discloses the waypoint. Fewer-than-three results are reported honestly. The offline fixture's third Chicago–Detroit route passes via Grand Rapids.
- [Open-Meteo Forecast API](https://open-meteo.com/en/docs) and [geocoding](https://open-meteo.com/en/docs/geocoding-api) supply forecasts and city lookup. Forecast requests are batched, normalized and cached; the response reports actual request counts and hits. Check [current service terms/plans](https://open-meteo.com/en/pricing) for the intended deployment.
- MapLibre renders the map, overlays and heat layer. Basemap attribution remains visible on the map. External tile availability is separate from application/API availability.

Live departures are supported from one hour ago through five days ahead, leaving forecast coverage for the additional 48-hour view. Routes over 2,000 miles, polar/dateline regions, more than 800 distinct forecast locations and unsupported provider coverage are rejected or shown as unavailable. Load is validated from 0 to 100,000 lb. Provider timeouts are bounded and errors are explicit. City geocoding can be ambiguous; inspect the displayed resolved endpoints. These are general driving routes and do not certify truck height/weight clearance, hazmat rules or legal road access.

## Checks and production

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py test
cd ..\frontend
npm run build
```

Backend tests cover risk boundaries, load thresholds, road sampling, forecast interval/unit handling, recommendation priority, unknown/unsafe routes, validation and mocked provider behavior. The frontend build checks TypeScript and compiles the production assets. The backend README contains provider-probe and test details as they are verified; do not infer public deployment or current forecast coverage from a synthetic demonstration.

Verified on 2 November 2026: **26 backend tests passed**. A live Chicago–Detroit trip produced three distinct provider road routes, 129 corridor cells and coverage through all 49 heatmap hours. Measured cold planning took **9.935 seconds** (2 routing, 4 weather and 2 geocoding requests); a repeated cached call took **0.126 seconds**, with zero external requests. These are observed local measurements for one trip and forecast snapshot, not guaranteed service times. Eight US city-pair probes yielded only one or two natural OSRM alternatives, so the application can make up to two additional requests via disclosed corridor waypoints to seek a third distinct option.

The multi-stage `Dockerfile` builds React, copies its assets next to Django, and runs Gunicorn on `$PORT`. Django/WhiteNoise serve frontend assets and APIs from one origin. With a running Docker engine, from this directory:

```powershell
docker build -t spotter-weather .
docker run --rm -p 8080:8000 -e DEBUG=false -e ALLOWED_HOSTS=localhost,127.0.0.1 -e SECRET_KEY=local-container-check-only spotter-weather
```

The selected hosting target is **Dokploy**. Follow [DEPLOY-DOKPLOY.md](DEPLOY-DOKPLOY.md) for the private GitHub source, Dockerfile build path, environment values, container port 8000, domain and health check. The standalone `render.yaml` is an alternative configuration following [Render's Blueprint specification](https://render.com/docs/blueprint-spec). Configuration is provided, but a hosted application URL must be created and verified before submission. The local Docker client was found, but its Linux engine was not running during initial checks, so a container build was not verified then.

## Submission status and time record

GitHub: [azeemamjad/spotter-weather-routing](https://github.com/azeemamjad/spotter-weather-routing), created private. Grant the hiring team access before submission. A genuine hosted application URL and 5–10-minute Loom recording remain required; no Loom or deployed URL is invented by this project. Record actual applicant work/review time; concurrent agent wall-clock duration is not a verified 16-hour assessment log. Update this section with the real links and time before submission, and state any remaining limitations. Submit to the full-stack assessment's own **Show Questions** form.
