from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .enums import ASSIGNABLE_ROLE_CHOICES


class Language(models.TextChoices):
    EN = "en", "English"
    IT = "it", "Italiano"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    default_cost_centre = models.ForeignKey(
        "masterdata.CostCentre", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.EN)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    # Sessions that started before this moment are logged out (block, deactivation, role change).
    sessions_revoked_at = models.DateTimeField(null=True, blank=True)
    # Skips the approval step (DSF-09.04). Who/when changed it is recorded in ConfigAuditLog.
    approval_exempt = models.BooleanField(default=False)
    # Users are deactivated, never deleted: the audit trail keeps pointing at the right person.
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.first_name or self.email

    def __str__(self):
        return self.full_name


class RoleAssignment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.CharField(max_length=20, choices=ASSIGNABLE_ROLE_CHOICES)
    added_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role")]

    def __str__(self):
        return f"{self.user.email}: {self.role}"


class AllowedDomain(models.Model):
    domain = models.CharField(max_length=190, unique=True)
    added_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["domain"]

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.domain


class AllowedEmail(models.Model):
    email = models.EmailField(unique=True)
    note = models.CharField(max_length=255, blank=True)
    added_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["email"]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class BlockedEmail(models.Model):
    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=255, blank=True)
    added_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["email"]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class OTPChallenge(models.Model):
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    # language chosen on the sign-in page; used only to create a first-time user (en/it or blank)
    language = models.CharField(max_length=2, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.email} @ {self.created_at:%Y-%m-%d %H:%M}"
