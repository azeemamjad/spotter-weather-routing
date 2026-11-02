"""Small, same-origin Django service; no database or user accounts required."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-before-deployment")
if not DEBUG and SECRET_KEY == "development-only-change-before-deployment":
    raise RuntimeError("Set a private SECRET_KEY when DEBUG=false.")
ALLOWED_HOSTS = [s.strip() for s in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if s.strip()]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
INSTALLED_APPS = ["django.contrib.staticfiles", "trip_planning"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.middleware.common.CommonMiddleware"]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
WHITENOISE_ROOT = FRONTEND_DIST
WHITENOISE_MAX_AGE = 3600
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache", "LOCATION": str(BASE_DIR / ".cache"), "OPTIONS": {"MAX_ENTRIES": 5000}}}
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
OPEN_METEO_GEOCODING_URL = os.environ.get("OPEN_METEO_GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1/search")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
PROVIDER_TIMEOUT_SECONDS = float(os.environ.get("PROVIDER_TIMEOUT_SECONDS", "15"))
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
