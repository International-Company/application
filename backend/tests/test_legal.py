"""المستندات القانونية المنشورة وارتباطها بموافقة المبدع."""
import pytest
from django.urls import reverse

from apps.legal import documents as legal

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("path", ["/terms", "/privacy"])
@pytest.mark.parametrize("lang,direction", [("ar", "rtl"), ("en", "ltr")])
def test_documents_render_in_both_languages(client, path, lang, direction):
    response = client.get(f"{path}?lang={lang}")
    assert response.status_code == 200
    body = response.content.decode()
    assert f'dir="{direction}"' in body
    assert f'lang="{lang}"' in body


def test_arabic_is_the_default_language(client):
    body = client.get("/terms").content.decode()
    assert 'dir="rtl"' in body
    assert "شروط الاستخدام" in body


def test_unknown_language_falls_back_to_arabic(client):
    assert 'dir="rtl"' in client.get("/terms?lang=fr").content.decode()


def test_json_descriptor_exposes_version_and_hash(client):
    data = client.get("/terms?format=json").json()
    assert data["version"] == legal.version(legal.TERMS)
    assert data["content_hash"] == legal.content_hash(legal.TERMS, "ar")
    assert len(data["content_hash"]) == 64


def test_hash_differs_between_languages():
    assert legal.content_hash(legal.TERMS, "ar") != legal.content_hash(legal.TERMS, "en")


def test_terms_state_the_core_financial_rule(client):
    """النص المنشور يجب أن يقول صراحةً إن الرصيد لا يُقيَّد قبل وصول المال."""
    body = client.get("/terms").content.decode()
    assert "لا يُقيَّد أي رصيد باسمك إلا بعد إثبات وصول المال" in body


def test_privacy_states_notifications_are_limited_to_tiktok(client):
    body = client.get("/privacy").content.decode()
    assert "لا نقرأ إشعارات أي تطبيق آخر غير TikTok" in body


# --- ربط الموافقة بالنص المنشور -------------------------------------------

@pytest.fixture
def creator_client(db):
    """عميل مصادَق عليه لمبدع موثّق."""
    from django.utils import timezone
    from rest_framework.test import APIClient

    from apps.api.tokens import issue_session
    from apps.creators.models import Creator
    from apps.creators.services import register_device

    creator = Creator.objects.create(
        phone="+201000009999", display_name="مبدع", phone_verified_at=timezone.now()
    )
    device = register_device(creator, device_id="d-1", integrity_token="t")
    session = issue_session(creator, device)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
    return api


def test_consent_accepts_the_published_text(creator_client):
    from apps.creators.models import CreatorConsent

    response = creator_client.post(
        reverse("api_v1:creator-consent"),
        {
            "terms_version": legal.version(legal.TERMS),
            "content_hash": legal.content_hash(legal.TERMS, "ar"),
            "language": "ar",
        },
        format="json",
    )
    assert response.status_code == 201
    assert CreatorConsent.objects.count() == 1


def test_consent_rejects_a_forged_hash(creator_client):
    from apps.creators.models import CreatorConsent

    response = creator_client.post(
        reverse("api_v1:creator-consent"),
        {"terms_version": legal.version(legal.TERMS), "content_hash": "0" * 64, "language": "ar"},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "terms_hash_mismatch"
    assert CreatorConsent.objects.count() == 0


def test_consent_rejects_an_old_version(creator_client):
    response = creator_client.post(
        reverse("api_v1:creator-consent"),
        {
            "terms_version": "0.9",
            "content_hash": legal.content_hash(legal.TERMS, "ar"),
            "language": "ar",
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "stale_terms_version"


def test_profile_exposes_current_legal_descriptors(creator_client):
    response = creator_client.get(reverse("api_v1:creator-me"))
    terms = response.data["legal"]["terms"]
    assert terms["version"] == legal.version(legal.TERMS)
    assert terms["content_hash"] == legal.content_hash(legal.TERMS, "ar")
    assert terms["url"] == "/terms"
