"""بيانات تشغيل أولية للتجربة المحلية.

تُنشئ ما تضعه الإدارة عادةً من لوحة التحكم (المرحلة 3): صاحب حساب مصري،
حساب استلام، جدول رسوم، وسعر صرف. لا تلمس أي بيانات مبدعين.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payouts.models import PayoutMethod
from apps.pricing.models import FeeSchedule, FxRate, FxRateSource
from apps.receiving.models import AccountOwner, ReceivingAccount, ReceivingAccountType


class Command(BaseCommand):
    help = "إنشاء بيانات تشغيل أولية للتجربة المحلية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--accounts", type=int, default=2, help="عدد حسابات الاستلام المُنشأة"
        )

    def handle(self, *args, **options):
        owner, _ = AccountOwner.objects.get_or_create(
            whatsapp_phone="+201111111111",
            defaults={"full_name": "صاحب حساب تجريبي", "whatsapp_verified_at": timezone.now()},
        )

        for index in range(1, options["accounts"] + 1):
            ReceivingAccount.objects.get_or_create(
                type=ReceivingAccountType.IPA,
                identifier=f"demo{index}@instapay",
                defaults={
                    "owner": owner,
                    "display_label": f"حساب الاستلام {index}",
                    "beneficiary_name": owner.full_name,
                    "bank_name": "بنك تجريبي",
                    "daily_limit_egp": Decimal("100000"),
                    "monthly_limit_egp": Decimal("1000000"),
                    "max_creators": 3,
                },
            )

        FeeSchedule.objects.get_or_create(
            name="الرسوم القياسية",
            defaults={
                "percent": Decimal("5.0000"),
                "fixed_amount": Decimal("0"),
                "effective_from": timezone.now() - timedelta(days=1),
                "is_active": True,
            },
        )

        FxRate.objects.get_or_create(
            source=FxRateSource.MANUAL,
            effective_at=timezone.now().replace(microsecond=0),
            defaults={"rate": Decimal("48.500000")},
        )

        PayoutMethod.objects.get_or_create(
            name="إنستاباي يدوي", defaults={"provider": "manual"}
        )

        self.stdout.write(
            self.style.SUCCESS(
                "جاهز: "
                f"{ReceivingAccount.objects.count()} حساب استلام، "
                f"{FeeSchedule.objects.filter(is_active=True).count()} جدول رسوم، "
                f"{FxRate.objects.count()} سعر صرف، "
                f"{PayoutMethod.objects.count()} وسيلة دفع"
            )
        )
