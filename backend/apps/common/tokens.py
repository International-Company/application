"""إصدار رموز المبدعين والتحقق منها.

ثلاثة أنواع: preauth قصير جدًا بعد ربط TikTok وقبل تأكيد الهاتف، وaccess
للعمل اليومي، وrefresh مربوط بجهاز واحد ويُدوَّر عند كل استعمال.
"""
import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from .errors import DomainError

ALGORITHM = "HS256"

TYPE_PREAUTH = "preauth"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"


class InvalidToken(DomainError):
    """رمز غير صالح أو منتهٍ."""


@dataclass(frozen=True)
class TokenPayload:
    """محتوى الرمز بعد التحقق."""

    subject: str
    token_type: str
    device_id: str
    jti: str


def _lifetime(token_type: str) -> timedelta:
    return {
        TYPE_PREAUTH: timedelta(minutes=settings.PREAUTH_TOKEN_MINUTES),
        TYPE_ACCESS: timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        TYPE_REFRESH: timedelta(days=settings.REFRESH_TOKEN_DAYS),
    }[token_type]


def issue(subject: str, token_type: str, *, device_id: str = "") -> tuple[str, str]:
    """إصدار رمز. يعيد (الرمز، معرّفه الفريد)."""
    now = timezone.now()
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(subject),
        "typ": token_type,
        "did": device_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + _lifetime(token_type)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM), jti


def verify(token: str, expected_type: str) -> TokenPayload:
    """التحقق من رمز ونوعه. يرفع InvalidToken عند أي خلل."""
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidToken("انتهت صلاحية الرمز") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidToken("رمز غير صالح") from exc

    if data.get("typ") != expected_type:
        raise InvalidToken("نوع الرمز لا يطابق المطلوب")

    return TokenPayload(
        subject=data["sub"],
        token_type=data["typ"],
        device_id=data.get("did", ""),
        jti=data.get("jti", ""),
    )


def hash_token(token: str) -> str:
    """بصمة الرمز للتخزين — لا يُخزَّن الرمز نفسه أبدًا."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
