"""ربط حساب TikTok بمبدع، وتجديد التوكنات."""
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.creators.models import Creator

from .models import CreatorPlatformAccount, Platform, PlatformAccountStatus, SyncLog, SyncOutcome
from .tiktok import TikTokProvider, get_provider


@transaction.atomic
def link_tiktok_account(
    code: str, *, provider: TikTokProvider | None = None, ip: str | None = None
):
    """تبادل كود Login Kit وربطه بمبدع. يعيد (المبدع، الحساب، هل هو جديد)."""
    provider = provider or get_provider()
    tokens = provider.exchange_code(code)
    profile = provider.fetch_profile(tokens.access_token)

    account = (
        CreatorPlatformAccount.objects.select_for_update()
        .filter(open_id=tokens.open_id, platform=Platform.TIKTOK)
        .first()
    )
    created = account is None

    if created:
        # مبدع جديد بلا هاتف بعد؛ الهاتف يُوثَّق في الخطوة التالية
        creator = Creator.objects.create(phone="", display_name=profile.display_name)
        account = CreatorPlatformAccount(creator=creator, platform=Platform.TIKTOK)
    else:
        creator = account.creator

    account.open_id = tokens.open_id
    account.union_id = profile.union_id
    account.display_name = profile.display_name
    account.avatar_url = profile.avatar_url
    account.profile_url = profile.profile_url
    account.follower_count = profile.follower_count
    account.access_token_enc = tokens.access_token
    account.refresh_token_enc = tokens.refresh_token
    account.token_expires_at = tokens.expires_at
    account.refresh_expires_at = tokens.refresh_expires_at
    account.scopes = tokens.scope
    account.status = PlatformAccountStatus.ACTIVE
    account.last_synced_at = timezone.now()
    account.save()

    if profile.display_name and creator.display_name != profile.display_name:
        creator.display_name = profile.display_name
        creator.save(update_fields=["display_name", "updated_at"])

    audit.record(
        action="tiktok.linked" if created else "tiktok.relinked",
        entity="creator_platform_account",
        entity_id=account.id,
        actor_type=ActorType.CREATOR,
        actor_id=creator.id,
        after={"open_id": tokens.open_id, "scopes": tokens.scope},
        ip=ip,
    )
    return creator, account, created


def refresh_account_token(
    account: CreatorPlatformAccount, *, provider: TikTokProvider | None = None
):
    """تجديد توكن حساب واحد وتسجيل النتيجة."""
    provider = provider or get_provider()
    try:
        tokens = provider.refresh(account.refresh_token_enc)
    except Exception as exc:  # noqa: BLE001 — الفشل يُسجَّل ولا يُسقط المهمة كلها
        account.status = PlatformAccountStatus.TOKEN_EXPIRED
        account.save(update_fields=["status", "updated_at"])
        SyncLog.objects.create(
            account=account,
            operation="refresh_token",
            outcome=SyncOutcome.FAILED,
            detail=str(exc)[:500],
        )
        return None

    account.access_token_enc = tokens.access_token
    account.refresh_token_enc = tokens.refresh_token or account.refresh_token_enc
    account.token_expires_at = tokens.expires_at
    account.refresh_expires_at = tokens.refresh_expires_at
    account.status = PlatformAccountStatus.ACTIVE
    account.last_synced_at = timezone.now()
    account.save()
    SyncLog.objects.create(account=account, operation="refresh_token", outcome=SyncOutcome.SUCCESS)
    return account
