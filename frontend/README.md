# Spotter React interface

React 19 + TypeScript + Vite + MapLibre. Run `npm ci` then `npm run dev` after starting the Django weather backend on port 8001. Open http://127.0.0.1:5173. `npm run build` type-checks and creates `dist/` for same-origin Django production hosting.

The form supports 10/25/50-mile sampling, pounds, and an explicit departure in the browser timezone, converted to UTC. A live forecast and an explicitly labeled offline demonstration are available. The demonstration uses Chicago–Detroit saved road geometry and synthetic weather; it must never be presented as current conditions.

Route cards show distance-weighted exposure and coverage. Selected checkpoint popups and details use ETA weather. The 0–48h heatmap independently shows one absolute time across the corridor. It uses relative intensity, with constant per-point weighting adjusted by severity; it is not a calibrated categorical surface. Unknown forecasts are omitted and coverage is shown. The map instance persists between route and slider changes, and only a new plan changes its bounds.

Basemap attribution: OpenStreetMap contributors. Public tiles and external Google Fonts require network access. If tiles cannot load, route data remains usable. Generic driving routes do not establish commercial truck road legality or clearance.
