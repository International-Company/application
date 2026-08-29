"""اختيار جدول الرسوم وسعر الصرف السارِيين لحظة الحاجة."""
from decimal import Decimal

from django.utils import timezone

from apps.common.enums import Currency
from apps.common.money import quantize

from .models import FeeSchedule, FxRate


def active_fee_schedule(at=None) -> FeeSchedule | None:
    """جدول الرسوم الساري في لحظة معينة."""
    moment = at or timezone.now()
    return (
        FeeSchedule.objects.filter(is_active=True, effective_from__lte=moment)
        .filter(effective_to__isnull=True)
        .order_by("-effective_from")
        .first()
        or FeeSchedule.objects.filter(
            is_active=True, effective_from__lte=moment, effective_to__gte=moment
        )
        .order_by("-effective_from")
        .first()
    )


def latest_fx_rate(
    at=None, base: str = Currency.USD, quote: str = Currency.EGP
) -> FxRate | None:
    """آخر سعر صرف معتمد قبل لحظة معينة."""
    moment = at or timezone.now()
    return (
        FxRate.objects.filter(
            base_currency=base, quote_currency=quote, effective_at__lte=moment
        )
        .order_by("-effective_at")
        .first()
    )


def compute_fee(amount_egp: Decimal, at=None) -> Decimal:
    """الرسم على مبلغ بالجنيه وفق الجدول الساري. بلا جدول ساري فلا رسم."""
    schedule = active_fee_schedule(at)
    if schedule is None:
        return Decimal("0.0000")
    return schedule.compute_fee(quantize(amount_egp))
