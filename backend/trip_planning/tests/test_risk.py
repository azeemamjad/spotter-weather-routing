from django.test import SimpleTestCase
from trip_planning.risk import classify, summarize, recommend


def weather(wind=0,rain=0,snow=0):
    return {"wind_mph":wind,"rain_in_hr":rain,"snow_in_hr":snow}


class RiskRulesTests(SimpleTestCase):
    def test_employer_wind_boundaries(self):
        for value,level in [(24.9,"low"),(25,"moderate"),(34.9,"moderate"),(35,"high"),(44.9,"high"),(45,"severe"),(54.9,"severe"),(55,"no_travel")]:
            with self.subTest(wind=value):
                self.assertEqual(classify(weather(wind=value),0)["level"],level)

    def test_rain_boundaries_keep_strict_no_travel(self):
        for value,level in [(.099,"low"),(.1,"moderate"),(.25,"high"),(.5,"severe"),(1,"severe"),(1.001,"no_travel")]:
            with self.subTest(rain=value):
                self.assertEqual(classify(weather(rain=value),0)["level"],level)

    def test_snow_boundaries_keep_strict_no_travel(self):
        for value,level in [(.499,"low"),(.5,"moderate"),(1,"high"),(2,"severe"),(3,"severe"),(3.001,"no_travel")]:
            with self.subTest(snow=value):
                self.assertEqual(classify(weather(snow=value),0)["level"],level)

    def test_load_comparisons_are_strict(self):
        for wind,load,level in [(45,30000,"severe"),(45,30000.01,"no_travel"),(35,40000,"high"),(35,40000.01,"severe"),(44.9,40001,"severe"),(54.9,30001,"no_travel")]:
            with self.subTest(wind=wind,load=load):
                self.assertEqual(classify(weather(wind=wind),load)["level"],level)
        for load in (0,30000,40000,100000):
            self.assertEqual(classify(weather(wind=55),load)["level"],"no_travel")

    def test_combination_and_missing_forecasts(self):
        self.assertEqual(classify(weather(wind=25,rain=.5,snow=1),35000)["level"],"severe")
        for value in (None,{},weather(wind=float("nan")),weather(rain=-1)):
            self.assertEqual(classify(value,35000)["level"],"unknown")

    def test_exposure_uses_miles_not_dot_count(self):
        cps=[{"segment_miles":10,"risk":classify(weather(wind=45),0)},
             {"segment_miles":40,"risk":classify(weather(wind=35),0)},
             {"segment_miles":0,"risk":classify(weather(),0)}]
        summary=summarize(cps,50)
        self.assertEqual(summary["severe_miles"],10)
        self.assertEqual(summary["high_miles"],40)
        self.assertEqual(summary["average_risk"],2.2)
        self.assertEqual(sum(summary["exposure_miles"].values()),50)

    def test_unknown_or_unsafe_destination_excludes_recommendation(self):
        for risk in (classify(None,0),classify(weather(wind=55),0)):
            summary=summarize([{"segment_miles":20,"risk":classify(weather(),0)},{"segment_miles":0,"risk":risk}],20)
            self.assertFalse(summary["feasible"])

    def test_ranking_is_lexicographic_and_filters_unsafe(self):
        def route(id,severe,high,average,time=100,feasible=True):
            return {"id":id,"duration_seconds":time,"summary":{"feasible":feasible,"severe_miles":severe,"high_miles":high,"average_risk":average}}
        cases=[
            ([route("a",1,0,0,1),route("b",0,100,3,1000)],"b"),
            ([route("a",0,1,0,1),route("b",0,0,3,1000)],"b"),
            ([route("a",0,0,2,1),route("b",0,0,1,1000)],"b"),
            ([route("a",0,0,1,100),route("b",0,0,1,50)],"b"),
            ([route("a",0,0,0,1,False),route("b",5,100,3,1000)],"b"),
        ]
        for routes,expected in cases:
            self.assertEqual(recommend(routes)["route_id"],expected)
        self.assertIsNone(recommend([route("a",0,0,0,1,False)])["route_id"])
