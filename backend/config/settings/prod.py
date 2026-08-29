"""إعدادات الإنتاج."""
from .base import *  # noqa: F401,F403

DEBUG = False
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
