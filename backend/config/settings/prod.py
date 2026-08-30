"""إعدادات الإنتاج."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

# في الإنتاج لا يجوز السقوط الصامت إلى قاعدة بيانات محلية: إما إعداد صريح أو توقف
if not DATABASE_URL and DATABASES["default"]["HOST"] in ("localhost", "127.0.0.1", ""):  # noqa: F405
    raise ImproperlyConfigured(
        "قاعدة البيانات غير مضبوطة: اضبط DATABASE_URL أو DB_HOST في متغيرات البيئة. "
        "على Railway اربط المتغير بخدمة Postgres عبر ${{Postgres.DATABASE_URL}}"
    )

if not FIELD_ENCRYPTION_KEY:  # noqa: F405
    raise ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY مطلوب في الإنتاج: 32 بايت بترميز base64. "
        "فقدانه لاحقًا يعني فقدان كل توكنات TikTok."
    )
SECURE_SSL_REDIRECT = True
# فحص الحياة يأتي من داخل الشبكة بلا ترويسة بروتوكول، فيُستثنى من التحويل إلى HTTPS
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

# في الإنتاج لا يدخل مستخدم إدارة بلا تحقق ثنائي
ADMIN_REQUIRE_TOTP = env.bool("ADMIN_REQUIRE_TOTP", default=True)  # noqa: F405
