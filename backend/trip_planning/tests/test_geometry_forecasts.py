from datetime import datetime, timezone
from django.test import SimpleTestCase
from trip_planning.geometry import sample_route, corridor_grid, METERS_PER_MILE
from trip_planning.providers import normalize_forecast, forecast_at


def synthetic_route():
    return {"distance":100*METERS_PER_MILE,"duration":1200,
            "geometry":{"type":"LineString","coordinates":[[-88,42],[-87,42],[-86,42]]},
            "legs":[{"annotation":{"distance":[10*METERS_PER_MILE,90*METERS_PER_MILE],"duration":[900,100]}}]}


class GeometryAndTimeTests(SimpleTestCase):
    def test_all_sampling_intervals_include_destination_once(self):
        dep=datetime(2026,11,2,23,55,tzinfo=timezone.utc)
        for interval,count in [(10,11),(25,5),(50,3)]:
            checkpoints,annotated=sample_route(synthetic_route(),interval,dep,"r")
            self.assertTrue(annotated)
            self.assertEqual(len(checkpoints),count)
            self.assertEqual(checkpoints[-1]["segment_miles"],0)
            self.assertAlmostEqual(checkpoints[-1]["distance_miles"],100)
            self.assertAlmostEqual(sum(p["segment_miles"] for p in checkpoints),100)
            self.assertEqual(checkpoints[-1]["eta"],"2026-11-03T00:15:00Z")

    def test_interpolation_uses_road_distance_and_annotated_duration(self):
        dep=datetime(2026,11,2,tzinfo=timezone.utc)
        points,_=sample_route(synthetic_route(),10,dep,"r")
        self.assertAlmostEqual(points[1]["longitude"],-87)
        self.assertEqual(points[1]["eta"],"2026-11-02T00:18:00Z")
        self.assertAlmostEqual(points[2]["longitude"],-87+10/90)

    def test_missing_annotations_use_disclosed_approximation(self):
        route=synthetic_route()
        del route["legs"]
        points,annotated=sample_route(route,50,datetime(2026,11,2,tzinfo=timezone.utc),"r")
        self.assertFalse(annotated)
        self.assertEqual(points[1]["eta"],"2026-11-02T00:10:00Z")

    def test_corridor_is_spatial_grid_off_the_route(self):
        points,spacing=corridor_grid([synthetic_route()])
        self.assertTrue(points)
        self.assertLessEqual(len(points),200)
        self.assertTrue(any(abs(p["latitude"]-42)>.01 for p in points))
        self.assertGreater(spacing,0)


class ForecastTests(SimpleTestCase):
    def provider(self):
        return {"hourly_units":{"wind_speed_10m":"km/h","rain":"mm","showers":"mm","snowfall":"cm"},
                "hourly":{"time":[3600,7200,10800],"wind_speed_10m":[16.09344,32.18688,None],"rain":[12.7,25.4,0],"showers":[12.7,0,0],"snowfall":[2.54,5.08,0]}}

    def test_units_and_liquid_rain_plus_showers(self):
        values=normalize_forecast(self.provider())["values"]
        self.assertAlmostEqual(values[0]["wind_mph"],10)
        self.assertAlmostEqual(values[0]["rain_in_hr"],1)
        self.assertAlmostEqual(values[0]["snow_in_hr"],1)
        self.assertIsNone(values[2])

    def test_precipitation_preceding_hour_selection_and_horizon(self):
        series=normalize_forecast(self.provider())
        self.assertAlmostEqual(forecast_at(series,datetime.fromtimestamp(3600,tz=timezone.utc))["wind_mph"],10)
        self.assertAlmostEqual(forecast_at(series,datetime.fromtimestamp(3601,tz=timezone.utc))["wind_mph"],20)
        self.assertIsNone(forecast_at(series,datetime.fromtimestamp(10801,tz=timezone.utc)))
        self.assertIsNone(forecast_at(series,datetime.fromtimestamp(0,tz=timezone.utc)))
        self.assertIsNone(forecast_at({},datetime.now(timezone.utc)))

    def test_unknown_units_do_not_create_low_risk_weather(self):
        data=self.provider()
        data["hourly_units"]["snowfall"]="m of snow depth"
        self.assertIsNone(normalize_forecast(data)["values"][0])
