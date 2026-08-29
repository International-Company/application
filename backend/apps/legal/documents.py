"""المستندات القانونية المنشورة وبصماتها.

ما يوقّع عليه المبدع في التطبيق هو نفسه المنشور على الويب: تُحسب بصمة SHA-256
من ملف المستند ذاته، فلا مجال لفجوة بين النص المعروض والنص المسجَّل في الموافقة.
"""
import hashlib
from functools import lru_cache
from pathlib import Path

from django.conf import settings

TERMS = "terms"
PRIVACY = "privacy"

VERSIONS = {TERMS: "1.0", PRIVACY: "1.0"}
LANGUAGES = ("ar", "en")

TITLES = {
    (TERMS, "ar"): "شروط الاستخدام",
    (TERMS, "en"): "Terms of Service",
    (PRIVACY, "ar"): "سياسة الخصوصية",
    (PRIVACY, "en"): "Privacy Policy",
}


def template_path(document: str, language: str) -> Path:
    """مسار ملف المستند."""
    return Path(settings.BASE_DIR) / "templates" / "legal" / f"{document}_{language}.html"


@lru_cache(maxsize=16)
def content_hash(document: str, language: str = "ar") -> str:
    """بصمة المستند كما هو منشور."""
    return hashlib.sha256(template_path(document, language).read_bytes()).hexdigest()


def version(document: str) -> str:
    """نسخة المستند الحالية."""
    return VERSIONS[document]


def descriptor(document: str, language: str = "ar") -> dict:
    """ما يحتاجه التطبيق ليعرض المستند ويسجّل الموافقة عليه."""
    return {
        "document": document,
        "version": version(document),
        "language": language,
        "content_hash": content_hash(document, language),
        "url": f"/{document}",
    }
