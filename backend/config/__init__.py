"""حزمة الإعدادات العليا. تحميل تطبيق Celery مع بدء Django."""
from .celery import app as celery_app

__all__ = ("celery_app",)
