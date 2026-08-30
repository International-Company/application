"""مسارات الإصدار v1 لتطبيق المبدع."""
from django.urls import include, path

from . import views

app_name = "api_v1"

urlpatterns = [
    path("auth/tiktok/exchange", views.TikTokExchangeView.as_view(), name="tiktok-exchange"),
    path("auth/phone/verify", views.PhoneVerifyView.as_view(), name="phone-verify"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("creators/me", views.CreatorMeView.as_view(), name="creator-me"),
    path("creators/me/consent", views.ConsentView.as_view(), name="creator-consent"),
    path("creators/me/devices", views.DeviceView.as_view(), name="creator-devices"),
    path("setup/autofill-dataset", views.AutofillDatasetView.as_view(), name="autofill-dataset"),
    path("setup/complete", views.SetupCompleteView.as_view(), name="setup-complete"),
    path("withdrawals", views.WithdrawalListCreateView.as_view(), name="withdrawals"),
    path("withdrawals/signals", views.WithdrawalSignalView.as_view(), name="withdrawal-signals"),
    path("withdrawals/<str:code>", views.WithdrawalDetailView.as_view(), name="withdrawal-detail"),
    path("health", views.HealthView.as_view(), name="health"),
    path("admin/", include("apps.api.admin_urls")),
]
