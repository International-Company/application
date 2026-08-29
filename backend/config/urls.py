"""مسارات المشروع."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.legal.views import legal_document


def healthz(_request):
    """فحص حياة الخدمة — لا يلمس قاعدة البيانات ليبقى سريعًا ورخيصًا."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("api/v1/", include("apps.api.urls")),
    path("terms", legal_document, {"document": "terms"}, name="terms"),
    path("privacy", legal_document, {"document": "privacy"}, name="privacy"),
    path("django-admin/", admin.site.urls),
]
