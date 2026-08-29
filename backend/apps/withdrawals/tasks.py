"""المهل الزمنية لطلبات السحب.

مهلتان في الوثيقة: خمس عشرة دقيقة بلا أي إشارة فيُسأل المبدع، وأربعة أيام
بعد tiktok_sent بلا تأكيد وصول فيصير الطلب not_received وتُفتح تذكرة للإدارة.
"""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.messaging.notifier import notify_creator

from . import state_machine as sm
from .models import WithdrawalRequest, WithdrawalStatus


@shared_task(name="withdrawals.ask_creator_about_stale_requests")
def ask_creator_about_stale_requests() -> int:
    """سؤال المبدع عن كل طلب مضى عليه ربع ساعة بلا إشارة."""
    cutoff = timezone.now() - timedelta(minutes=settings.WITHDRAWAL_OPEN_WINDOW_MINUTES)
    stale = WithdrawalRequest.objects.filter(
        status=WithdrawalStatus.INITIATED,
        initiated_at__lte=cutoff,
        signals__isnull=True,
        stale_prompt_sent_at__isnull=True,
    ).distinct()

    count = 0
    for request in stale:
        notify_creator(
            request.creator,
            title="هل أكملت السحب؟",
            body=f"لم تصلنا إشارة عن الطلب {request.code}. هل أتممت السحب داخل TikTok؟",
            request=request,
            data={"code": request.code, "action": "confirm_withdrawal", "answers": "yes,no"},
        )
        request.stale_prompt_sent_at = timezone.now()
        request._via_state_machine = True
        request.save(update_fields=["stale_prompt_sent_at", "updated_at"])
        request._via_state_machine = False
        audit.record(
            action="withdrawal.stale_prompt_sent",
            entity="withdrawal_request",
            entity_id=request.id,
            actor_type=ActorType.SYSTEM,
            after={"code": request.code},
        )
        count += 1
    return count


@shared_task(name="withdrawals.flag_not_received")
def flag_not_received() -> int:
    """تحويل الطلبات المرسَلة التي لم يصلها تأكيد خلال المهلة إلى not_received."""
    cutoff = timezone.now() - timedelta(days=settings.WITHDRAWAL_NOT_RECEIVED_DAYS)
    overdue = WithdrawalRequest.objects.filter(
        status=WithdrawalStatus.TIKTOK_SENT, sent_at__lte=cutoff
    )

    count = 0
    for request in overdue:
        sm.transition(
            request,
            WithdrawalStatus.NOT_RECEIVED,
            actor=sm.Actor(type=ActorType.SYSTEM, label="مهلة الوصول"),
            evidence={"days": settings.WITHDRAWAL_NOT_RECEIVED_DAYS},
        )
        count += 1
    return count


@shared_task(name="integrations.refresh_tiktok_tokens")
def refresh_tiktok_tokens() -> int:
    """تجديد التوكنات التي تقترب من الانتهاء قبل أن تنتهي."""
    from apps.integrations.models import CreatorPlatformAccount, PlatformAccountStatus
    from apps.integrations.services import refresh_account_token

    horizon = timezone.now() + timedelta(hours=settings.TOKEN_REFRESH_HORIZON_HOURS)
    accounts = CreatorPlatformAccount.objects.filter(
        status=PlatformAccountStatus.ACTIVE, token_expires_at__lte=horizon
    )
    return sum(1 for account in accounts if refresh_account_token(account) is not None)
