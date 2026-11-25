from django.db import models
from django.utils import timezone


class EmailTemplate(models.Model):
    key = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    recipients_description = models.CharField(max_length=200)
    trigger_description = models.CharField(max_length=300)
    subject_en = models.CharField(max_length=300)
    body_en = models.TextField()
    subject_it = models.CharField(max_length=300, blank=True)
    body_it = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.key} — {self.name}"


class OutboxStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped (template disabled)"


class EmailOutbox(models.Model):
    template_key = models.CharField(max_length=40)
    request = models.ForeignKey(
        "shipments.ShipmentRequest", null=True, blank=True, on_delete=models.SET_NULL, related_name="emails"
    )
    to_addresses = models.JSONField(default=list)
    subject = models.CharField(max_length=300)
    body = models.TextField()
    status = models.CharField(max_length=8, choices=OutboxStatus.choices, default=OutboxStatus.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)  # set only when SENT
    # Claim lease while a sender works on the row, then retry back-off (1, 5, 15, 60 min).
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=100, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "email outbox"

    def __str__(self):
        return f"{self.template_key} → {', '.join(self.to_addresses)} ({self.status})"
