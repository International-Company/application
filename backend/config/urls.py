"""مسارات المشروع."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(_request):
    """فحص حياة الخدمة — لا يلمس قاعدة البيانات ليبقى سريعًا ورخيصًا."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("api/v1/", include("apps.api.urls")),
    path("django-admin/", admin.site.urls),
]
