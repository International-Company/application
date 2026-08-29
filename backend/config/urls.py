"""مسارات المشروع — تُملأ في المرحلة 2."""
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("django-admin/", admin.site.urls),
]
