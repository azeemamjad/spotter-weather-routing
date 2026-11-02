import json
from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from .errors import PlanningError
from .planner import build_plan


@require_GET
def health(request):
    return JsonResponse({"status":"ok","service":"spotter-weather-routing","version":"1.0.0"})


@csrf_exempt
def plan(request):
    # Public stateless API: there is no cookie session or privileged operation.
    # Same-origin production serving and Vite's /api development proxy need no
    # broad CORS permission. CSRF tokens would add no authorization here.
    if request.method != "POST":
        response=JsonResponse({"error":{"code":"method_not_allowed","message":"Use POST with a JSON request body."}},status=405)
        response["Allow"]="POST"
        return response
    if request.content_type != "application/json":
        return JsonResponse({"error":{"code":"unsupported_media_type","message":"Use Content-Type: application/json."}},status=415)
    if len(request.body)>16000:
        return JsonResponse({"error":{"code":"request_too_large","message":"Request body exceeds 16 KB."}},status=413)
    try:
        data=json.loads(request.body,parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
    except (ValueError,UnicodeDecodeError):
        return JsonResponse({"error":{"code":"invalid_json","message":"Request body must contain valid JSON with finite numbers."}},status=400)
    try:
        return JsonResponse(build_plan(data),json_dumps_params={"allow_nan":False,"separators":(",",":")})
    except PlanningError as exc:
        error={"code":exc.code,"message":exc.message}
        if exc.details is not None:
            error["details"]=exc.details
        return JsonResponse({"error":error},status=exc.status)


@require_GET
def frontend(request):
    index=settings.FRONTEND_DIST/"index.html"
    if not index.is_file():
        return JsonResponse({"service":"Spotter weather routing API","frontend":"Start Vite on port 5173, or run npm run build in frontend to serve the app here.","health":"/api/health/"})
    response=FileResponse(index.open("rb"),content_type="text/html")
    response["Cache-Control"]="no-cache"
    return response
