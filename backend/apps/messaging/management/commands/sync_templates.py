"""إنشاء قوالب الرسائل الافتراضية في قاعدة البيانات."""
from django.core.management.base import BaseCommand

from apps.messaging.services import sync_templates


class Command(BaseCommand):
    help = "إنشاء قوالب رسائل واتساب الافتراضية بلغتيها"

    def handle(self, *args, **options):
        created = sync_templates()
        self.stdout.write(self.style.SUCCESS(f"أُنشئ {created} قالبًا جديدًا"))
