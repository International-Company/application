"""مستخدمو لوحة الإدارة والأدوار والتحقق الثنائي."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.common.fields import EncryptedTextField
from apps.common.models import TimestampedModel


class AdminRole(models.TextChoices):
    """أدوار الإدارة — تحدد ما يراه المستخدم وما يستطيع اعتماده."""

    SUPERADMIN = "superadmin", "مدير عام"
    FINANCE = "finance", "مالية"
    SUPPORT = "support", "دعم"
    VIEWER = "viewer", "مطالعة فقط"


class AdminUserManager(BaseUserManager):
    """مدير إنشاء مستخدمي الإدارة."""

    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("البريد الإلكتروني مطلوب")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", AdminRole.SUPERADMIN)
        return self.create_user(email, password, **extra)


class AdminUser(TimestampedModel, AbstractBaseUser, PermissionsMixin):
    """مستخدم لوحة الإدارة — لا علاقة له بحسابات المبدعين إطلاقًا."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=AdminRole.choices, default=AdminRole.VIEWER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # سر TOTP للتحقق الثنائي — مشفَّر ولا يُعرض أبدًا بعد التفعيل
    totp_secret_enc = EncryptedTextField(blank=True, default="")
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = AdminUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "admin_users"
        verbose_name = "مستخدم إدارة"
        verbose_name_plural = "مستخدمو الإدارة"

    def __str__(self) -> str:
        return self.email

    @property
    def totp_enabled(self) -> bool:
        return bool(self.totp_secret_enc) and self.totp_confirmed_at is not None


class AdminLoginAttempt(TimestampedModel):
    """محاولات الدخول — للكشف عن التخمين وتطبيق قواعد السرعة."""

    email = models.EmailField()
    succeeded = models.BooleanField(default=False)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    attempted_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "admin_login_attempts"
        indexes = [models.Index(fields=["email", "attempted_at"])]
