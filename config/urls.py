from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.patients.urls")),
    path("api/v1/", include("apps.workflows.urls")),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.escalations.urls")),
    path("api/v1/", include("apps.intelligence.urls")),
    path("api/v1/", include("apps.integrations.urls")),
    path("api/v1/", include("apps.communications.urls")),
]
