"""إعدادات الاختبارات — Postgres حقيقي لأن قيود السلامة محفورة في قاعدة البيانات."""
import base64
import os

from .base import *  # noqa: F401,F403

DEBUG = False
FIELD_ENCRYPTION_KEY = base64.b64encode(b"0" * 32).decode()
CELERY_TASK_ALWAYS_EAGER = True
DATABASES["default"]["NAME"] = os.environ.get("TEST_DB_NAME", "mobde3_test")  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
