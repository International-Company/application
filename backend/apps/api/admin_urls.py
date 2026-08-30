"""مسارات لوحة الإدارة — الإصدار v1."""
from django.urls import path

from . import admin_views as v

app_name = "api_admin"

urlpatterns = [
    path("auth/csrf", v.CsrfView.as_view(), name="csrf"),
    path("auth/login", v.AdminLoginView.as_view(), name="login"),
    path("auth/logout", v.AdminLogoutView.as_view(), name="logout"),
    path("auth/me", v.AdminMeView.as_view(), name="me"),
    path("auth/totp", v.TotpSetupView.as_view(), name="totp"),
    path("account-owners", v.AccountOwnerListCreateView.as_view(), name="owners"),
    path("receiving-accounts", v.ReceivingAccountListCreateView.as_view(), name="accounts"),
    path("receiving-accounts/<uuid:pk>", v.ReceivingAccountDetailView.as_view(), name="account"),
    path(
        "receiving-accounts/<uuid:pk>/assign",
        v.ReceivingAccountAssignView.as_view(),
        name="account-assign",
    ),
    path("creators", v.AdminCreatorListView.as_view(), name="creators"),
    path("withdrawals", v.AdminWithdrawalListView.as_view(), name="withdrawals"),
    path("withdrawals/<str:code>", v.AdminWithdrawalDetailView.as_view(), name="withdrawal"),
    path("payouts", v.AdminPayoutQueueView.as_view(), name="payouts"),
    path("payouts/<str:code>/execute", v.AdminPayoutExecuteView.as_view(), name="payout-execute"),
    path("reports", v.AdminReportsView.as_view(), name="reports"),
]
