export type Level = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel' | 'unknown';
export type Weather = { wind_mph: number; rain_in_hr: number; snow_in_hr: number; forecast_time?: string };
export type Checkpoint = { id: string; latitude: number; longitude: number; distance_miles: number; segment_miles: number; eta: string; weather: Weather | null; risk: {level: Level; score: number | null; reasons: string[]} };
export type Route = { id: string; name: string; geometry: GeoJSON.LineString; distance_miles: number; duration_seconds: number; checkpoints: Checkpoint[]; summary: { severe_miles: number; high_miles: number; no_travel_miles: number; unknown_miles: number; average_risk: number | null; coverage_percent: number; feasible: boolean; worst_risk: Level; exposure_miles: Record<Level, number> } };
export type Plan = {
 request: {origin: {name: string; latitude: number; longitude: number}; destination: {name: string; latitude: number; longitude: number}; departure_time: string; load_weight_lb: number; sample_interval_miles: number; mode: string};
 routes: Route[]; recommendation: {route_id: string | null; reason: string};
 heatmap: {base_time: string; hours: number[]; corridor_width_miles: number; points: {latitude: number; longitude: number; values: ({risk: Level; score: number | null} & Weather | null)[]}[]};
 metadata: {providers: Record<string,string>; elapsed_ms: number; provider_requests: Record<string,number>; cache_hits: Record<string,number>; warnings: string[]; assumptions: string[]; demo: boolean};
};
export const colors: Record<Level, string> = { low: '#26a787', moderate: '#d4ae48', high: '#ed8a45', severe: '#df5863', no_travel: '#9d436c', unknown: '#86929c' };
export const labels: Record<Level, string> = { low: 'Low', moderate: 'Moderate', high: 'High', severe: 'Severe', no_travel: 'No travel', unknown: 'Unknown' };
export const dateTime = (value: string) => new Date(value).toLocaleString(undefined, {month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
export const duration = (seconds: number) => `${Math.floor(Math.round(seconds/60)/60)}h ${Math.round(seconds/60)%60}m`;
