"""إعدادات التطوير المحلي."""
from .base import *  # noqa: F401,F403

DEBUG = True

# التطوير المحلي يعمل بلا مفاتيح خارجية: بدائل في الذاكرة ما لم تُضبط البيئة
TIKTOK_PROVIDER = env(  # noqa: F405
    "TIKTOK_PROVIDER", default="apps.integrations.tiktok.FakeTikTokProvider"
)
SMS_SENDER = env("SMS_SENDER", default="apps.creators.sms.ConsoleSmsSender")  # noqa: F405
PUSH_SENDER = env("PUSH_SENDER", default="apps.messaging.notifier.ConsolePushSender")  # noqa: F405
INTEGRITY_VERIFIER = env(  # noqa: F405
    "INTEGRITY_VERIFIER", default="apps.creators.integrity.PermissiveIntegrityVerifier"
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "mobde3": {"handlers": ["console"], "level": "INFO"},
        "mobde3.sms": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "mobde3.push": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
