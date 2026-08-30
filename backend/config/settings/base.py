"""الإعدادات المشتركة لكل البيئات."""
from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# منصات الاستضافة تمنح نطاقًا عامًا وقت التشغيل — يُضاف تلقائيًا دون تعديل الإعدادات
PUBLIC_DOMAIN = env("RAILWAY_PUBLIC_DOMAIN", default="") or env("PUBLIC_DOMAIN", default="")
if PUBLIC_DOMAIN and PUBLIC_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(PUBLIC_DOMAIN)

# على Railway يتغير النطاق مع كل بيئة، وفحص الحياة يأتي بترويسة مضيف خاصة به
ON_RAILWAY = bool(
    env("RAILWAY_ENVIRONMENT_NAME", default="") or env("RAILWAY_PROJECT_ID", default="")
)
if ON_RAILWAY:
    for host in (".up.railway.app", "healthcheck.railway.app"):
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

# النقطة البادئة صيغة Django للنطاقات الفرعية، وCSRF يريدها بنجمة
CSRF_TRUSTED_ORIGINS = [
    "https://" + (host.replace(".", "*.", 1) if host.startswith(".") else host)
    for host in ALLOWED_HOSTS
    if host not in ("localhost", "127.0.0.1")
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # وحدات المنصة
    "apps.common",
    "apps.api",
    "apps.identity",
    "apps.creators",
    "apps.integrations",
    "apps.receiving",
    "apps.pricing",
    "apps.withdrawals",
    "apps.reconciliation",
    "apps.ledger",
    "apps.payouts",
    "apps.messaging",
    "apps.audit",
    "apps.legal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # يخدم الملفات الساكنة دون nginx — لازم على منصات الاستضافة المُدارة
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# المنصات المُدارة تمرّر DATABASE_URL جاهزًا؛ وإلا تُقرأ المتغيرات المنفصلة
DATABASE_URL = env("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {"default": env.db_url("DATABASE_URL")}
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="mobde3"),
            "USER": env("DB_USER", default="postgres"),
            "PASSWORD": env("DB_PASSWORD", default="postgres"),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
        }
    }
DATABASES["default"]["ATOMIC_REQUESTS"] = False

AUTH_USER_MODEL = "identity.AdminUser"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# التوطين: العربية هي الأصل والإنجليزية بديل قابل للتبديل
LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", "العربية"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# تشفير الحقول الحساسة (AES-256-GCM) — المفتاح من البيئة فقط ولا يُخزَّن في القاعدة
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = False

# قواعد الأعمال — قابلة للضبط دون تعديل الكود
WITHDRAWAL_OPEN_WINDOW_MINUTES = env.int("WITHDRAWAL_OPEN_WINDOW_MINUTES", default=15)
WITHDRAWAL_NOT_RECEIVED_DAYS = env.int("WITHDRAWAL_NOT_RECEIVED_DAYS", default=4)
RECONCILIATION_AMOUNT_TOLERANCE = Decimal(
    str(env.float("RECONCILIATION_AMOUNT_TOLERANCE", default=0.03))
)
RECONCILIATION_MIN_CONFIDENCE = Decimal("0.9")
OWNER_CONFIRMATION_MAX_AMOUNT_USD = Decimal(
    str(env.float("OWNER_CONFIRMATION_MAX_AMOUNT_USD", default=100))
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.creators.authentication.CreatorJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("THROTTLE_AUTH", default="10/min"),
        "setup": env("THROTTLE_SETUP", default="30/hour"),
        "withdrawal": env("THROTTLE_WITHDRAWAL", default="10/hour"),
        "signal": env("THROTTLE_SIGNAL", default="120/hour"),
        "admin_auth": env("THROTTLE_ADMIN_AUTH", default="20/min"),
    },
    "UNAUTHENTICATED_USER": None,
}

# --- رموز المبدعين ---
ACCESS_TOKEN_MINUTES = env.int("ACCESS_TOKEN_MINUTES", default=15)
REFRESH_TOKEN_DAYS = env.int("REFRESH_TOKEN_DAYS", default=30)
PREAUTH_TOKEN_MINUTES = env.int("PREAUTH_TOKEN_MINUTES", default=10)

# --- تحقق الهاتف ---
OTP_LENGTH = env.int("OTP_LENGTH", default=6)
OTP_TTL_MINUTES = env.int("OTP_TTL_MINUTES", default=5)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_SECONDS = env.int("OTP_RESEND_SECONDS", default=60)

# --- قواعد السرعة على طلبات السحب ---
MAX_WITHDRAWALS_PER_DAY = env.int("MAX_WITHDRAWALS_PER_DAY", default=3)
MAX_WITHDRAWALS_PER_MONTH = env.int("MAX_WITHDRAWALS_PER_MONTH", default=30)
REQUIRE_DEVICE_INTEGRITY = env.bool("REQUIRE_DEVICE_INTEGRITY", default=True)
TOKEN_REFRESH_HORIZON_HOURS = env.int("TOKEN_REFRESH_HORIZON_HOURS", default=24)

# --- دخول الإدارة ---
ADMIN_LOGIN_MAX_FAILURES = env.int("ADMIN_LOGIN_MAX_FAILURES", default=5)
ADMIN_LOGIN_WINDOW_MINUTES = env.int("ADMIN_LOGIN_WINDOW_MINUTES", default=15)
ADMIN_REQUIRE_TOTP = env.bool("ADMIN_REQUIRE_TOTP", default=False)

# --- حزم TikTok المعتمدة: أي إشعار من غيرها لا يُصدَّق ---
TIKTOK_PACKAGE_NAMES = env.list(
    "TIKTOK_PACKAGE_NAMES",
    default=["com.zhiliaoapp.musically", "com.ss.android.ugc.trill"],
)
TIKTOK_CLIENT_KEY = env("TIKTOK_CLIENT_KEY", default="")
TIKTOK_CLIENT_SECRET = env("TIKTOK_CLIENT_SECRET", default="")
TIKTOK_HTTP_TIMEOUT = env.int("TIKTOK_HTTP_TIMEOUT", default=15)
TIKTOK_REDIRECT_URI = env("TIKTOK_REDIRECT_URI", default="")

# --- المزوّدون الخارجيون: يُستبدل كل واحد بسطر في البيئة ---
TIKTOK_PROVIDER = env("TIKTOK_PROVIDER", default="apps.integrations.tiktok.HttpTikTokProvider")
SMS_SENDER = env("SMS_SENDER", default="apps.creators.sms.ConsoleSmsSender")
PUSH_SENDER = env("PUSH_SENDER", default="apps.messaging.notifier.ConsolePushSender")
INTEGRITY_VERIFIER = env(
    "INTEGRITY_VERIFIER", default="apps.creators.integrity.PermissiveIntegrityVerifier"
)

# --- جدولة المهام الدورية ---
CELERY_BEAT_SCHEDULE = {
    "ask-creator-about-stale-requests": {
        "task": "withdrawals.ask_creator_about_stale_requests",
        "schedule": 300.0,
    },
    "flag-not-received": {"task": "withdrawals.flag_not_received", "schedule": 3600.0},
    "refresh-tiktok-tokens": {"task": "integrations.refresh_tiktok_tokens", "schedule": 21600.0},
}
