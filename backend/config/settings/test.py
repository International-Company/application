"""إعدادات الاختبارات — Postgres حقيقي لأن قيود السلامة محفورة في قاعدة البيانات."""
import base64
import os

from .base import *  # noqa: F401,F403

DEBUG = False
FIELD_ENCRYPTION_KEY = base64.b64encode(b"0" * 32).decode()
CELERY_TASK_ALWAYS_EAGER = True
DATABASES["default"]["NAME"] = os.environ.get("TEST_DB_NAME", "mobde3_test")  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# الاختبارات لا تلمس الشبكة: كل مزوّد خارجي يُستبدل ببديل في الذاكرة
TIKTOK_PROVIDER = "apps.integrations.tiktok.FakeTikTokProvider"
SMS_SENDER = "apps.creators.sms.ConsoleSmsSender"
PUSH_SENDER = "apps.messaging.notifier.ConsolePushSender"
INTEGRITY_VERIFIER = "apps.creators.integrity.PermissiveIntegrityVerifier"
WHATSAPP_CHANNEL = "apps.messaging.whatsapp.FakeWhatsAppChannel"
WHATSAPP_APP_SECRET = "test-app-secret"
WHATSAPP_VERIFY_TOKEN = "test-verify-token"
ADMIN_WHATSAPP_NUMBERS = ["+201999999999"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {  # noqa: F405
    "auth": "1000/min", "setup": "1000/min", "withdrawal": "1000/min",
    "signal": "1000/min", "admin_auth": "1000/min",
}}
