"""تشفير الحقول الحساسة بـ AES-256-GCM.

المفتاح يأتي من متغير البيئة FIELD_ENCRYPTION_KEY ولا يُخزَّن في قاعدة البيانات.
الصيغة المخزَّنة: base64( nonce[12] || ciphertext || tag ).
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

NONCE_SIZE = 12


def _key() -> bytes:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY غير مضبوط في البيئة")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY يجب أن يكون 32 بايت بترميز base64")
    return key


def encrypt(plaintext: str, *, aad: bytes | None = None) -> str:
    """تشفير نص وإرجاعه بترميز base64."""
    nonce = os.urandom(NONCE_SIZE)
    blob = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return base64.b64encode(nonce + blob).decode("ascii")


def decrypt(token: str, *, aad: bytes | None = None) -> str:
    """فك تشفير نص مُخزَّن بصيغة base64."""
    raw = base64.b64decode(token)
    nonce, blob = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, blob, aad).decode("utf-8")
