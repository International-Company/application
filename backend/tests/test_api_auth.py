"""ربط TikTok، تحقق الهاتف، الجلسات، وفصل صلاحيات المبدع عن الإدارة."""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.creators.models import Creator, CreatorDevice
from apps.creators.sms import ConsoleSmsSender
from apps.integrations.models import CreatorPlatformAccount

pytestmark = pytest.mark.django_db

DEVICE = "device-abc-123"
PHONE = "+201234567890"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def captured_sms(monkeypatch):
    """التقاط رسائل SMS لقراءة الرمز دون تسريبه في الاستجابة."""
    sender = ConsoleSmsSender()
    monkeypatch.setattr("apps.creators.services.get_sms_sender", lambda: sender)
    return sender


def last_otp(captured_sms) -> str:
    return captured_sms.sent[-1][1].split(":")[-1].strip()


def link(client, code="valid-code", device_id=DEVICE):
    return client.post(
        reverse("api_v1:tiktok-exchange"), {"code": code, "device_id": device_id}, format="json"
    )


def verified_session(client, captured_sms, device_id=DEVICE, phone=PHONE):
    """الرحلة الكاملة: ربط ثم إرسال رمز ثم تأكيده — تعيد الجلسة."""
    preauth = link(client, device_id=device_id).data["preauth_token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {preauth}")
    client.post(reverse("api_v1:phone-verify"), {"phone": phone}, format="json")
    response = client.post(
        reverse("api_v1:phone-verify"),
        {"phone": phone, "code": last_otp(captured_sms), "device_id": device_id},
        format="json",
    )
    client.credentials()
    return response.data["session"]


def authed(client, session) -> APIClient:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
    return client


# --- ربط TikTok -----------------------------------------------------------

def test_exchange_creates_creator_and_links_account(client):
    response = link(client)
    assert response.status_code == 200
    assert response.data["is_new"] is True
    assert response.data["phone_verified"] is False
    assert "preauth_token" in response.data
    # لا يُعاد أي توكن من TikTok إلى الجهاز
    assert "access_token" not in str(response.data)
    assert CreatorPlatformAccount.objects.count() == 1


def test_exchange_stores_tokens_encrypted(client):
    link(client)
    account = CreatorPlatformAccount.objects.get()
    assert account.access_token_enc == "access-1"
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT access_token_enc FROM creator_platform_accounts")
        assert cur.fetchone()[0] != "access-1"


def test_exchange_is_idempotent_for_same_open_id(client):
    link(client)
    link(client)
    assert Creator.objects.count() == 1
    assert CreatorPlatformAccount.objects.count() == 1


def test_exchange_rejects_invalid_code(client):
    response = link(client, code="invalid")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "tiktok_error"


# --- تحقق الهاتف ----------------------------------------------------------

def test_phone_verification_requires_preauth_token(client):
    response = client.post(reverse("api_v1:phone-verify"), {"phone": PHONE}, format="json")
    assert response.status_code == 401


def test_otp_is_never_returned_in_response(client, captured_sms):
    preauth = link(client).data["preauth_token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {preauth}")
    response = client.post(reverse("api_v1:phone-verify"), {"phone": PHONE}, format="json")
    assert response.data == {"otp_sent": True, "expires_in": 300}
    assert last_otp(captured_sms) not in str(response.data)


def test_wrong_otp_is_rejected(client, captured_sms):
    preauth = link(client).data["preauth_token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {preauth}")
    client.post(reverse("api_v1:phone-verify"), {"phone": PHONE}, format="json")
    response = client.post(
        reverse("api_v1:phone-verify"), {"phone": PHONE, "code": "000000"}, format="json"
    )
    assert response.status_code == 400
    assert Creator.objects.get().phone_verified_at is None


def test_successful_verification_issues_session(client, captured_sms):
    session = verified_session(client, captured_sms)
    assert session["access"] and session["refresh"]
    assert session["expires_in"] == 900
    creator = Creator.objects.get()
    assert creator.phone == PHONE
    assert creator.phone_verified_at is not None
    assert CreatorDevice.objects.filter(creator=creator, device_id=DEVICE).exists()


def test_phone_cannot_be_claimed_by_two_creators(client, captured_sms, monkeypatch):
    verified_session(client, captured_sms)

    from apps.integrations.tiktok import FakeTikTokProvider, TikTokProfile, TikTokTokens

    other = FakeTikTokProvider(
        tokens=TikTokTokens("open-id-2", "access-2", "refresh-2", 86400, 31536000),
        profile=TikTokProfile(open_id="open-id-2", display_name="مبدع ثانٍ"),
    )
    monkeypatch.setattr("apps.integrations.services.get_provider", lambda: other)

    client2 = APIClient()
    preauth = link(client2, device_id="device-2").data["preauth_token"]
    client2.credentials(HTTP_AUTHORIZATION=f"Bearer {preauth}")

    # يستطيع الثاني طلب رمز، لكن لا يستطيع الاستيلاء على رقم موثّق لغيره
    assert client2.post(
        reverse("api_v1:phone-verify"), {"phone": PHONE}, format="json"
    ).status_code == 200
    response = client2.post(
        reverse("api_v1:phone-verify"),
        {"phone": PHONE, "code": last_otp(captured_sms), "device_id": "device-2"},
        format="json",
    )
    assert response.status_code == 400
    assert Creator.objects.filter(phone=PHONE).count() == 1
    assert Creator.objects.get(phone=PHONE).platform_accounts.first().open_id == "open-id-1"


# --- الجلسات والتجديد -----------------------------------------------------

def test_access_token_grants_access_to_profile(client, captured_sms):
    session = verified_session(client, captured_sms)
    response = authed(client, session).get(reverse("api_v1:creator-me"))
    assert response.status_code == 200
    assert response.data["phone_verified"] is True
    assert response.data["balance_egp"] == "0.0000"


def test_no_token_is_rejected(client):
    assert client.get(reverse("api_v1:creator-me")).status_code == 401


def test_tampered_token_is_rejected(client, captured_sms):
    session = verified_session(client, captured_sms)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access'][:-4]}abcd")
    assert client.get(reverse("api_v1:creator-me")).status_code == 401


def test_refresh_rotates_and_old_token_dies(client, captured_sms):
    session = verified_session(client, captured_sms)
    first = client.post(
        reverse("api_v1:refresh"), {"refresh": session["refresh"]}, format="json"
    )
    assert first.status_code == 200
    new_session = first.data["session"]
    assert new_session["refresh"] != session["refresh"]

    replay = client.post(
        reverse("api_v1:refresh"), {"refresh": session["refresh"]}, format="json"
    )
    assert replay.status_code == 401
    # إعادة استعمال رمز مُبطَل تُبطل كل جلسات الجهاز
    after = client.post(
        reverse("api_v1:refresh"), {"refresh": new_session["refresh"]}, format="json"
    )
    assert after.status_code == 401


def test_suspended_creator_is_locked_out(client, captured_sms):
    session = verified_session(client, captured_sms)
    creator = Creator.objects.get()
    creator.status = "suspended"
    creator.save()
    assert authed(client, session).get(reverse("api_v1:creator-me")).status_code == 401


def test_deactivated_device_is_locked_out(client, captured_sms):
    session = verified_session(client, captured_sms)
    CreatorDevice.objects.update(is_active=False)
    assert authed(client, session).get(reverse("api_v1:creator-me")).status_code == 401


# --- فصل الصلاحيات ---------------------------------------------------------

def test_admin_session_cannot_use_creator_routes(client, db):
    from apps.identity.models import AdminUser

    admin = AdminUser.objects.create_superuser("admin@example.com", "pass1234")
    client.force_authenticate(user=admin)
    response = client.get(reverse("api_v1:creator-me"))
    assert response.status_code == 403


def test_creator_token_fails_admin_permission(client, captured_sms):
    from apps.common.permissions import IsAdminSession
    from apps.creators.authentication import CreatorPrincipal

    verified_session(client, captured_sms)
    principal = CreatorPrincipal(Creator.objects.get())

    class FakeRequest:
        user = principal

    assert IsAdminSession().has_permission(FakeRequest(), None) is False
