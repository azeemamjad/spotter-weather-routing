from django.urls import path
from trip_planning.views import health, plan, frontend

urlpatterns = [
    path("api/health/", health),
    path("api/weather-route-plan/", plan),
    path("", frontend),
]
