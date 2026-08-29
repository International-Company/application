"""تشفير الحقول الحساسة."""
import pytest
from django.utils import timezone

from apps.common import crypto
from apps.integrations.models import CreatorPlatformAccount


def test_encrypt_then_decrypt_roundtrip():
    token = crypto.encrypt("سر-التوكن-123")
    assert token != "سر-التوكن-123"
    assert crypto.decrypt(token) == "سر-التوكن-123"


def test_two_encryptions_differ():
    """الـ nonce عشوائي، فالنص نفسه يعطي ناتجًا مختلفًا في كل مرة."""
    assert crypto.encrypt("نفس النص") != crypto.encrypt("نفس النص")


@pytest.mark.django_db
def test_token_stored_encrypted_in_database(creator):
    """التوكن يُخزَّن مشفَّرًا في القاعدة ويُقرأ نصًا عبر الـ ORM."""
    account = CreatorPlatformAccount.objects.create(
        creator=creator,
        open_id="open-id-1",
        access_token_enc="access-token-plain",
        token_expires_at=timezone.now(),
    )
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT access_token_enc FROM creator_platform_accounts WHERE id = %s",
            [str(account.id)],
        )
        raw = cur.fetchone()[0]

    assert raw != "access-token-plain"
    stored = CreatorPlatformAccount.objects.get(pk=account.pk)
    assert stored.access_token_enc == "access-token-plain"
