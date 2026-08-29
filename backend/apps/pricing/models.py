"""جداول الرسوم وأسعار الصرف — تُدار من لوحة الإدارة ولا تُحسب في الكود."""
from decimal import Decimal

from django.db import models

from apps.common.enums import Currency
from apps.common.models import TimestampedModel
from apps.common.money import quantize


class FeeSchedule(TimestampedModel):
    """جدول رسوم فعّال في فترة زمنية. الرسم = نسبة + مبلغ ثابت، ضمن حد أدنى وأقصى."""

    name = models.CharField(max_length=100)
    percent = models.DecimalField(
        max_digits=6, decimal_places=4, default=0, help_text="نسبة مئوية، مثال 5.0000 تعني ٥٪"
    )
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EGP)
    min_fee = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    max_fee = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "fee_schedules"
        indexes = [models.Index(fields=["is_active", "effective_from"])]

    def compute_fee(self, amount: Decimal) -> Decimal:
        """حساب الرسم على مبلغ بعملة الجدول."""
        fee = quantize(Decimal(amount) * self.percent / Decimal("100") + self.fixed_amount)
        if fee < self.min_fee:
            fee = quantize(self.min_fee)
        if self.max_fee is not None and fee > self.max_fee:
            fee = quantize(self.max_fee)
        return fee


class FxRateSource(models.TextChoices):
    TIKTOK = "tiktok", "سعر TikTok"
    MANUAL = "manual", "إدخال يدوي"
    BANK = "bank", "سعر البنك"


class FxRate(TimestampedModel):
    """سعر صرف الدولار مقابل الجنيه في لحظة معينة."""

    base_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    quote_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EGP)
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    source = models.CharField(
        max_length=10, choices=FxRateSource.choices, default=FxRateSource.MANUAL
    )
    effective_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "fx_rates"
        constraints = [
            models.CheckConstraint(condition=models.Q(rate__gt=0), name="fx_rate_positive"),
            models.UniqueConstraint(
                fields=["base_currency", "quote_currency", "source", "effective_at"],
                name="uniq_fx_rate_point",
            ),
        ]

    def convert(self, amount: Decimal) -> Decimal:
        """تحويل مبلغ من العملة الأساس إلى عملة التسعير."""
        return quantize(Decimal(amount) * self.rate)
