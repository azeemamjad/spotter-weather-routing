import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from trip_planning.errors import PlanningError
from trip_planning.planner import build_plan, validate_request
from trip_planning.providers import resolve_location, get_routes, route_signature
from .test_geometry_forecasts import synthetic_route


def request(mode="demo"):
    return {"origin":"Chicago, IL","destination":"Detroit, MI","departure_time":datetime.now(timezone.utc).isoformat(),"load_weight_lb":35000,"sample_interval_miles":25,"mode":mode}


class ValidationTests(SimpleTestCase):
    def test_timezone_offset_required_and_normalized(self):
        req=request()
        req["departure_time"]="2026-11-03T08:00:00-06:00"
        self.assertEqual(validate_request(req)[0].isoformat(),"2026-11-03T14:00:00+00:00")
        req["departure_time"]="2026-11-03T08:00:00"
        with self.assertRaises(PlanningError):validate_request(req)

    def test_invalid_load_interval_and_mode(self):
        for field,value in [("load_weight_lb",float("nan")),("load_weight_lb",True),("load_weight_lb",-1),("sample_interval_miles",11),("sample_interval_miles",True),("mode","silent-fallback")]:
            req=request()
            req[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(PlanningError):validate_request(req)

    def test_live_forecast_window(self):
        req=request("live")
        req["departure_time"]=(datetime.now(timezone.utc)+timedelta(days=6)).isoformat()
        with self.assertRaises(PlanningError):validate_request(req)

    def test_coordinates_validate_without_geocoding(self):
        stats={"provider_requests":{"geocoding":0},"cache_hits":{"geocoding":0}}
        self.assertEqual(resolve_location({"latitude":42,"longitude":-88},stats)["latitude"],42)
        for value in ({"latitude":True,"longitude":-88},{"latitude":91,"longitude":0},{"latitude":"nan","longitude":0}):
            with self.assertRaises(PlanningError):resolve_location(value,stats)


class ApiTests(SimpleTestCase):
    def test_health_and_error_contracts(self):
        self.assertEqual(self.client.get("/api/health/").json()["status"],"ok")
        response=self.client.get("/api/weather-route-plan/")
        self.assertEqual(response.status_code,405)
        self.assertEqual(response.json()["error"]["code"],"method_not_allowed")
        self.assertEqual(self.client.post("/api/weather-route-plan/",data="{",content_type="application/json").status_code,400)
        self.assertEqual(self.client.post("/api/weather-route-plan/",data="[]",content_type="application/json").status_code,400)
        self.assertEqual(self.client.post("/api/weather-route-plan/",data="{}",content_type="text/plain").status_code,415)
        self.assertEqual(self.client.post("/api/weather-route-plan/",data='{"load_weight_lb":NaN}',content_type="application/json").status_code,400)
        self.assertEqual(self.client.post("/api/weather-route-plan/",data=" "*16001,content_type="application/json").status_code,413)

    @patch("trip_planning.providers.fetch_json",side_effect=AssertionError("Demo must never call a provider"))
    def test_demo_end_to_end_and_all_slider_hours(self,fetch):
        response=self.client.post("/api/weather-route-plan/",data=json.dumps(request()),content_type="application/json")
        self.assertEqual(response.status_code,200,response.content[:500])
        data=response.json()
        self.assertEqual(len(data["routes"]),3)
        self.assertEqual(len({json.dumps(r["geometry"],sort_keys=True) for r in data["routes"]}),3)
        self.assertEqual(data["metadata"]["provider_requests"],{"routing":0,"weather":0,"geocoding":0})
        self.assertTrue(data["metadata"]["demo"])
        self.assertIn("synthetic",data["metadata"]["warnings"][0].lower())
        self.assertEqual(data["heatmap"]["hours"],list(range(49)))
        self.assertTrue(data["heatmap"]["points"])
        for point in data["heatmap"]["points"]:
            self.assertEqual(len(point["values"]),49)
        self.assertNotEqual(data["heatmap"]["points"][0]["values"][0],data["heatmap"]["points"][0]["values"][48])
        for route in data["routes"]:
            self.assertAlmostEqual(sum(route["summary"]["exposure_miles"].values()),route["distance_miles"])
            self.assertEqual(route["checkpoints"][-1]["segment_miles"],0)

    def test_demo_rejects_different_route_instead_of_lying(self):
        req=request()
        req["origin"]="Boston, MA"
        response=self.client.post("/api/weather-route-plan/",data=json.dumps(req),content_type="application/json")
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()["error"]["code"],"demo_route_only")

    @patch("trip_planning.planner.get_forecasts",return_value={})
    @patch("trip_planning.planner.get_routes",return_value=[synthetic_route()])
    def test_missing_live_forecasts_are_unknown_and_not_recommended(self,routes,forecasts):
        req=request("live")
        req["origin"]={"latitude":42,"longitude":-88}
        req["destination"]={"latitude":42,"longitude":-86}
        data=build_plan(req)
        self.assertIsNone(data["recommendation"]["route_id"])
        self.assertAlmostEqual(data["routes"][0]["summary"]["unknown_miles"],100)
        self.assertIsNone(data["routes"][0]["summary"]["average_risk"])
        self.assertTrue(all(value is None for value in data["heatmap"]["points"][0]["values"]))

    @patch("trip_planning.planner.get_routes",side_effect=PlanningError("provider_unavailable","Provider unavailable",502))
    def test_provider_failure_never_substitutes_demo(self,routes):
        req=request("live")
        req["origin"]={"latitude":42,"longitude":-88}
        req["destination"]={"latitude":42,"longitude":-86}
        response=self.client.post("/api/weather-route-plan/",data=json.dumps(req),content_type="application/json")
        self.assertEqual(response.status_code,502)
        self.assertEqual(response.json()["error"]["code"],"provider_unavailable")

    @patch("trip_planning.providers._route_request")
    def test_provider_duplicates_are_not_three_options(self,route_request):
        route=synthetic_route()
        route_request.return_value={"routes":[route,route,route]}
        stats={"provider_requests":{"routing":0},"cache_hits":{"routing":0}}
        warnings=[]
        routes=get_routes({"latitude":42,"longitude":-88},{"latitude":42,"longitude":-86},stats,warnings)
        self.assertEqual(len(routes),1)
        self.assertTrue(any("Only 1 distinct" in value for value in warnings))
