"""واجهة TikTok — نقاط OAuth الرسمية فقط.

لا يوجد أي واجهة من TikTok لقراءة الرصيد أو تنفيذ السحب، ولا تُخترع هنا.
المتاح رسميًا: تبادل كود Login Kit، تجديد التوكن، وقراءة الملف الشخصي.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.common.errors import DomainError

TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_ENDPOINT = "https://open.tiktokapis.com/v2/user/info/"
USER_INFO_FIELDS = "open_id,union_id,display_name,avatar_url,profile_deep_link,follower_count"


class TikTokError(DomainError):
    """فشل في التخاطب مع TikTok."""


@dataclass(frozen=True)
class TikTokTokens:
    """ناتج تبادل الكود أو تجديد التوكن."""

    open_id: str
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    scope: str = ""

    @property
    def expires_at(self):
        return timezone.now() + timedelta(seconds=self.expires_in)

    @property
    def refresh_expires_at(self):
        return timezone.now() + timedelta(seconds=self.refresh_expires_in)


@dataclass(frozen=True)
class TikTokProfile:
    """الملف الشخصي كما تعيده TikTok."""

    open_id: str
    union_id: str = ""
    display_name: str = ""
    avatar_url: str = ""
    profile_url: str = ""
    follower_count: int = 0


class TikTokProvider(ABC):
    """العقد الذي تعتمد عليه بقية المنصة."""

    @abstractmethod
    def exchange_code(
        self, code: str, *, redirect_uri: str = "", code_verifier: str = ""
    ) -> TikTokTokens: ...

    @abstractmethod
    def refresh(self, refresh_token: str) -> TikTokTokens: ...

    @abstractmethod
    def fetch_profile(self, access_token: str) -> TikTokProfile: ...


class HttpTikTokProvider(TikTokProvider):
    """التنفيذ الحقيقي عبر نقاط TikTok الموثّقة."""

    def __init__(self, client_key: str = "", client_secret: str = ""):
        self.client_key = client_key or settings.TIKTOK_CLIENT_KEY
        self.client_secret = client_secret or settings.TIKTOK_CLIENT_SECRET

    def _post_token(self, data: dict) -> TikTokTokens:
        import requests  # يُستورد عند الاستعمال فقط ليبقى الاختبار بلا شبكة

        if not self.client_key or not self.client_secret:
            raise TikTokError("مفاتيح TikTok غير مضبوطة في البيئة")

        payload = {"client_key": self.client_key, "client_secret": self.client_secret, **data}
        response = requests.post(
            TOKEN_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=settings.TIKTOK_HTTP_TIMEOUT,
        )
        body = response.json()
        if response.status_code != 200 or "access_token" not in body:
            raise TikTokError(f"فشل تبادل التوكن مع TikTok: {body.get('error_description', body)}")

        return TikTokTokens(
            open_id=body["open_id"],
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", ""),
            expires_in=int(body.get("expires_in", 0)),
            refresh_expires_in=int(body.get("refresh_expires_in", 0)),
            scope=body.get("scope", ""),
        )

    def exchange_code(
        self, code: str, *, redirect_uri: str = "", code_verifier: str = ""
    ) -> TikTokTokens:
        data = {"code": code, "grant_type": "authorization_code"}
        # redirect_uri إلزامي، وcode_verifier إلزامي لتطبيقات الهاتف (PKCE)
        data["redirect_uri"] = redirect_uri or settings.TIKTOK_REDIRECT_URI
        if code_verifier:
            data["code_verifier"] = code_verifier
        return self._post_token(data)

    def refresh(self, refresh_token: str) -> TikTokTokens:
        return self._post_token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def fetch_profile(self, access_token: str) -> TikTokProfile:
        import requests

        response = requests.get(
            USER_INFO_ENDPOINT,
            params={"fields": USER_INFO_FIELDS},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.TIKTOK_HTTP_TIMEOUT,
        )
        body = response.json()
        user = (body.get("data") or {}).get("user")
        if response.status_code != 200 or not user:
            raise TikTokError(f"تعذّرت قراءة ملف TikTok: {body}")

        return TikTokProfile(
            open_id=user.get("open_id", ""),
            union_id=user.get("union_id", "") or "",
            display_name=user.get("display_name", "") or "",
            avatar_url=user.get("avatar_url", "") or "",
            profile_url=user.get("profile_deep_link", "") or "",
            follower_count=int(user.get("follower_count") or 0),
        )


@dataclass
class FakeTikTokProvider(TikTokProvider):
    """بديل للاختبارات والتطوير — لا يلمس الشبكة."""

    tokens: TikTokTokens | None = None
    profile: TikTokProfile | None = None
    calls: list = field(default_factory=list)

    def _default_tokens(self, suffix: str = "1") -> TikTokTokens:
        return TikTokTokens(
            open_id=f"open-id-{suffix}",
            access_token=f"access-{suffix}",
            refresh_token=f"refresh-{suffix}",
            expires_in=86400,
            refresh_expires_in=31536000,
            scope="user.info.basic,user.info.profile,user.info.stats",
        )

    def exchange_code(
        self, code: str, *, redirect_uri: str = "", code_verifier: str = ""
    ) -> TikTokTokens:
        self.calls.append(("exchange_code", code, redirect_uri, code_verifier))
        if code == "invalid":
            raise TikTokError("كود غير صالح")
        return self.tokens or self._default_tokens()

    def refresh(self, refresh_token: str) -> TikTokTokens:
        self.calls.append(("refresh", refresh_token))
        return self.tokens or self._default_tokens()

    def fetch_profile(self, access_token: str) -> TikTokProfile:
        self.calls.append(("fetch_profile", access_token))
        return self.profile or TikTokProfile(
            open_id="open-id-1", display_name="مبدع تجريبي", follower_count=1000
        )


def get_provider() -> TikTokProvider:
    """يُختار المزوّد من الإعدادات ليسهل استبداله في الاختبارات."""
    from django.utils.module_loading import import_string

    return import_string(settings.TIKTOK_PROVIDER)()
