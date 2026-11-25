from django.conf import settings
from django.db import models
from django.utils import timezone


class AccessMode(models.TextChoices):
    DOMAIN = "DOMAIN", "Allowed domains"
    ALLOWLIST = "ALLOWLIST", "Allow-list only"


class NoApproverFallback(models.TextChoices):
    ADMIN = "ADMIN", "Escalate to administrators"
    SKIP = "SKIP", "Skip approval"
    HOLD = "HOLD", "Hold until an admin reassigns"


class SelfApprovalMode(models.TextChoices):
    ROUTE_TO_OTHERS = "ROUTE_TO_OTHERS", "Route to other approvers"
    AUTO_APPROVE = "AUTO_APPROVE", "Approve automatically"


class SingletonModel(models.Model):
    """Exactly one row, pk=1. The DB constraint stops a second row; `load()` creates the first."""

    class Meta:
        abstract = True

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class OnMissing(models.TextChoices):
    DEACTIVATE = "deactivate", "Deactivate"
    KEEP = "keep", "Keep"


class SiteConfig(SingletonModel):
    access_mode = models.CharField(max_length=10, choices=AccessMode.choices, default=AccessMode.DOMAIN)
    otp_minutes = models.PositiveSmallIntegerField(default=10)
    otp_max_attempts = models.PositiveSmallIntegerField(default=5)
    session_hours = models.PositiveSmallIntegerField(default=8)
    session_idle_minutes = models.PositiveSmallIntegerField(default=30)

    approval_global_enabled = models.BooleanField(default=True)
    reject_comment_required = models.BooleanField(default=True)
    self_approval_mode = models.CharField(
        max_length=20, choices=SelfApprovalMode.choices, default=SelfApprovalMode.ROUTE_TO_OTHERS
    )
    no_approver_fallback = models.CharField(
        max_length=5, choices=NoApproverFallback.choices, default=NoApproverFallback.ADMIN
    )
    sla_hours = models.PositiveSmallIntegerField(default=24)
    reminder_hours = models.PositiveSmallIntegerField(default=24)
    escalate_hours = models.PositiveSmallIntegerField(default=48)

    po_mandatory_us = models.BooleanField(default=True)
    msds_required_other_hazard = models.BooleanField(default=True)
    max_parcel_lines = models.PositiveSmallIntegerField(default=6)

    customer_mgmt_mailbox = models.EmailField(default="logistica@diasorin.com")
    ticketing_url = models.CharField(max_length=500, blank=True)
    sender_email = models.EmailField(default="noreply-shipments@diasorin.com")

    # Inventory sync (credentials come from the environment, never the database)
    sync_host = models.CharField(max_length=200, blank=True)
    sync_path = models.CharField(max_length=300, default="/inventory/outbound/")
    sync_pattern = models.CharField(max_length=100, default="inventory_*.csv")
    sync_archive_path = models.CharField(max_length=300, default="/inventory/processed/")
    sync_every_minutes = models.PositiveSmallIntegerField(default=15)
    sync_alert_hours = models.PositiveSmallIntegerField(default=24)
    sync_on_missing = models.CharField(max_length=12, choices=OnMissing.choices, default=OnMissing.DEACTIVATE)
    sync_notify_admins = models.BooleanField(default=True)

    class Meta:
        verbose_name = "site configuration"
        verbose_name_plural = "site configuration"
        constraints = [models.CheckConstraint(condition=models.Q(pk=1), name="siteconfig_singleton")]

    def __str__(self):
        return "Site configuration"


class ConfigAuditLog(models.Model):
    at = models.DateTimeField(default=timezone.now, db_index=True)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=100)
    detail = models.CharField(max_length=500, blank=True)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action}"


class ConfigSnapshot(models.Model):
    """Go-live snapshot of the configuration, used by the reset (DSF-09.12)."""

    label = models.CharField(max_length=100)
    taken_at = models.DateTimeField(default=timezone.now)
    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    data = models.JSONField()

    class Meta:
        ordering = ["-taken_at"]

    def __str__(self):
        return f"{self.label} ({self.taken_at:%Y-%m-%d %H:%M})"
