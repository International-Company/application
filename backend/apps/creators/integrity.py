"""فحص سلامة الجهاز عبر Play Integrity — خلف واجهة.

القرار الأمني هنا: الجهاز غير الموثوق يُرفض عند طلب السحب، لا عند التصفح.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings

from .models import IntegrityVerdict


class IntegrityVerifier(ABC):
    """العقد: تحويل رمز Play Integrity إلى حكم."""

    @abstractmethod
    def verify(self, token: str, *, device_id: str = "") -> str:
        """يعيد قيمة من IntegrityVerdict."""


@dataclass
class PermissiveIntegrityVerifier(IntegrityVerifier):
    """بديل التطوير: يقبل أي رمز غير فارغ. لا يُستعمل في الإنتاج."""

    checked: list = field(default_factory=list)

    def verify(self, token: str, *, device_id: str = "") -> str:
        self.checked.append((device_id, token))
        if not token:
            return IntegrityVerdict.UNKNOWN
        if token.startswith("untrusted"):
            return IntegrityVerdict.UNTRUSTED
        return IntegrityVerdict.TRUSTED


def get_integrity_verifier() -> IntegrityVerifier:
    from django.utils.module_loading import import_string

    return import_string(settings.INTEGRITY_VERIFIER)()
