"""ثوابت مشتركة."""
from django.db import models


class Currency(models.TextChoices):
    USD = "USD", "دولار أمريكي"
    EGP = "EGP", "جنيه مصري"


class ActorType(models.TextChoices):
    CREATOR = "creator", "مبدع"
    ADMIN = "admin", "إدارة"
    SYSTEM = "system", "النظام"
    OWNER = "owner", "صاحب حساب استلام"
