"""مسارات المشروع — تُملأ في المرحلة 2."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def healthz(_request):
    """فحص حياة الخدمة — لا يلمس قاعدة البيانات ليبقى سريعًا ورخيصًا."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("django-admin/", admin.site.urls),
]
