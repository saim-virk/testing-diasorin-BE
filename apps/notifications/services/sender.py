"""Deliver queued EmailOutbox rows through Django's configured email backend (console / SMTP).

Rows are *claimed* in a short transaction and sent outside it, so a slow SMTP server never holds
database locks. The claim is a lease in `next_attempt_at` (now + CLAIM_TIMEOUT): a sender that dies
leaves the row to be picked up again once the lease runs out. After a failed send the same column holds
the retry back-off (1, 5, 15, 60 minutes). `sent_at` is set only when the row is SENT.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import get_connection
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.platform_config.models import SiteConfig

from ..models import EmailOutbox, EmailTemplate, OutboxStatus
from .mailconfig import build_message

MAX_ATTEMPTS = 5
CLAIM_TIMEOUT = timedelta(minutes=5)
RETRY_BACKOFF_MINUTES = (1, 5, 15, 60)  # wait after failed attempt 1, 2, 3, 4
OTP_KEY = "otp"
CODE_REMOVED = "[sign-in code removed]"


def scrub(row: EmailOutbox) -> None:
    """Sign-in codes must not outlive their email: wipe the body (the subject never carries the code)."""
    row.body = CODE_REMOVED


def backoff_for(attempts: int) -> timedelta:
    index = min(max(attempts, 1), len(RETRY_BACKOFF_MINUTES)) - 1
    return timedelta(minutes=RETRY_BACKOFF_MINUTES[index])


def _claim(limit: int, ids: list[int] | None) -> list[EmailOutbox]:
    now = timezone.now()
    with transaction.atomic():
        qs = EmailOutbox.objects.select_for_update(skip_locked=True).filter(status=OutboxStatus.PENDING)
        qs = qs.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        if ids is not None:
            qs = qs.filter(pk__in=ids)
        rows = list(qs.order_by("created_at")[:limit])
        if rows:
            lease = now + CLAIM_TIMEOUT
            EmailOutbox.objects.filter(pk__in=[r.pk for r in rows]).update(next_attempt_at=lease)
    return rows


def send_pending(limit: int = 100, ids: list[int] | None = None) -> dict:
    """Send PENDING rows that are due (all, or only `ids`). Returns counts {sent, failed, skipped}."""
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    rows = _claim(limit, ids)
    if not rows:
        return counts

    config = SiteConfig.load()
    sender = config.sender_email or settings.DEFAULT_FROM_EMAIL
    otp_minutes = config.otp_minutes
    disabled = set(EmailTemplate.objects.filter(enabled=False).values_list("key", flat=True))
    now = timezone.now()
    connection = get_connection()  # one SMTP session (SSL + login) for every row of this batch

    try:
        _deliver(rows, connection, counts, sender, otp_minutes, disabled, now)
    finally:
        _close(connection)
    return counts


def _close(connection) -> None:
    try:
        connection.close()
    except Exception:  # noqa: BLE001 - a broken session is already gone
        pass


def _deliver(rows, connection, counts, sender, otp_minutes, disabled, now) -> None:
    for row in rows:  # no transaction is open here
        is_otp = row.template_key == OTP_KEY
        stale_code = is_otp and now > row.created_at + timedelta(minutes=otp_minutes)
        if stale_code or (row.template_key in disabled and not is_otp):
            # an expired code is useless; the sign-in code is never suppressed by a template switch
            row.status, row.next_attempt_at = OutboxStatus.SKIPPED, None
            if is_otp:
                scrub(row)
            row.save(update_fields=["status", "next_attempt_at", "body"])
            counts["skipped"] += 1
            continue

        row.attempts += 1
        try:
            message = build_message(row.subject, row.body, sender, list(row.to_addresses))
            message.connection = connection
            connection.open()  # no-op while the session is open; reconnects after a failed row
            message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - record any transport error on the row
            _close(connection)
            row.last_error = str(exc)
            if row.attempts >= MAX_ATTEMPTS:
                row.status, row.next_attempt_at = OutboxStatus.FAILED, None
                if is_otp:
                    scrub(row)
            else:
                row.status = OutboxStatus.PENDING
                row.next_attempt_at = timezone.now() + backoff_for(row.attempts)
            counts["failed"] += 1
        else:
            row.status, row.sent_at = OutboxStatus.SENT, timezone.now()
            row.next_attempt_at, row.last_error = None, None
            if is_otp:
                scrub(row)
            counts["sent"] += 1
        row.save(update_fields=["attempts", "status", "sent_at", "next_attempt_at", "last_error", "body"])
