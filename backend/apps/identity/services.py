"""دخول الإدارة: كلمة المرور، التحقق الثنائي، وقواعد السرعة."""
from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.common.errors import DomainError

from .models import AdminLoginAttempt, AdminUser

ISSUER = "منصة المبدعين"


class LoginError(DomainError):
    """فشل تسجيل دخول الإدارة."""


class TotpRequired(DomainError):
    """كلمة المرور صحيحة ويلزم رمز التحقق الثنائي."""


def _too_many_failures(email: str, ip: str | None) -> bool:
    """حد المحاولات الفاشلة لكل بريد خلال نافذة زمنية."""
    window = timezone.now() - timedelta(minutes=settings.ADMIN_LOGIN_WINDOW_MINUTES)
    failures = AdminLoginAttempt.objects.filter(
        email=email, succeeded=False, attempted_at__gte=window
    ).count()
    return failures >= settings.ADMIN_LOGIN_MAX_FAILURES


def _record(email: str, *, succeeded: bool, ip: str | None, user_agent: str = "") -> None:
    AdminLoginAttempt.objects.create(
        email=email, succeeded=succeeded, ip=ip, user_agent=user_agent[:300]
    )


def verify_totp(user: AdminUser, code: str) -> bool:
    """التحقق من رمز TOTP مع سماح نافذة واحدة لفارق الساعة."""
    if not user.totp_secret_enc:
        return False
    return pyotp.TOTP(user.totp_secret_enc).verify(code or "", valid_window=1)


def login(
    *, email: str, password: str, totp_code: str = "", ip: str | None = None, user_agent: str = ""
) -> AdminUser:
    """التحقق من بيانات الدخول. يرفع TotpRequired إذا لزم الرمز الثنائي."""
    email = (email or "").strip().lower()
    if _too_many_failures(email, ip):
        raise LoginError("تجاوزت عدد المحاولات المسموح بها؛ حاول لاحقًا")

    user = authenticate(username=email, password=password)
    if user is None or not user.is_active:
        _record(email, succeeded=False, ip=ip, user_agent=user_agent)
        raise LoginError("بيانات الدخول غير صحيحة")

    if user.totp_enabled:
        if not totp_code:
            raise TotpRequired("يلزم رمز التحقق الثنائي")
        if not verify_totp(user, totp_code):
            _record(email, succeeded=False, ip=ip, user_agent=user_agent)
            raise LoginError("رمز التحقق الثنائي غير صحيح")
    elif settings.ADMIN_REQUIRE_TOTP:
        raise LoginError("يلزم تفعيل التحقق الثنائي قبل الدخول")

    _record(email, succeeded=True, ip=ip, user_agent=user_agent)
    user.last_login_ip = ip
    user.save(update_fields=["last_login_ip", "updated_at"])
    audit.record(
        action="admin.login",
        entity="admin_user",
        entity_id=user.id,
        actor_type=ActorType.ADMIN,
        actor_id=user.id,
        actor_label=user.email,
        ip=ip,
    )
    return user


def start_totp_setup(user: AdminUser) -> dict:
    """توليد سر جديد وإرجاع رابط الإعداد. لا يُفعَّل حتى يؤكَّد برمز صحيح."""
    if user.totp_enabled:
        raise DomainError("التحقق الثنائي مفعَّل بالفعل")
    secret = pyotp.random_base32()
    user.totp_secret_enc = secret
    user.totp_confirmed_at = None
    user.save(update_fields=["totp_secret_enc", "totp_confirmed_at", "updated_at"])
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    return {"secret": secret, "otpauth_uri": uri}


def confirm_totp_setup(user: AdminUser, code: str) -> AdminUser:
    """تأكيد التفعيل برمز من التطبيق."""
    if not user.totp_secret_enc:
        raise DomainError("ابدأ إعداد التحقق الثنائي أولًا")
    if not verify_totp(user, code):
        raise DomainError("الرمز غير صحيح")
    user.totp_confirmed_at = timezone.now()
    user.save(update_fields=["totp_confirmed_at", "updated_at"])
    audit.record(
        action="admin.totp_enabled",
        entity="admin_user",
        entity_id=user.id,
        actor_type=ActorType.ADMIN,
        actor_id=user.id,
        actor_label=user.email,
    )
    return user
