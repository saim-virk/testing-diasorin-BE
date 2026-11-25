"""Section 0b: sign-in codes in the outbox, immediate send, claim-then-send."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts.services import otp
from apps.notifications.models import EmailOutbox, OutboxStatus
from apps.notifications.services.sender import send_pending
from apps.platform_config.models import SiteConfig

pytestmark = pytest.mark.django_db

EMAIL = "m.rossi@diasorin.com"
WIPED = "[sign-in code removed]"


def test_sign_in_email_is_sent_immediately_after_commit(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        otp.request_code(EMAIL, None)
    assert len(mail.outbox) == 1  # no send_outbox run needed
    assert EmailOutbox.objects.get().status == OutboxStatus.SENT


def test_failed_immediate_send_leaves_row_pending_for_retry(django_capture_on_commit_callbacks, monkeypatch):
    def boom(self, fail_silently=False):
        raise OSError("smtp down")

    with monkeypatch.context() as m:
        m.setattr("django.core.mail.message.EmailMessage.send", boom)
        with django_capture_on_commit_callbacks(execute=True):
            otp.request_code(EMAIL, None)  # the request itself still succeeds
    row = EmailOutbox.objects.get()
    assert row.status == OutboxStatus.PENDING and row.sent_at is None and "smtp down" in row.last_error
    call_command("send_outbox")
    assert mail.outbox == []  # backing off for a minute
    with freeze_time(timezone.now() + timedelta(minutes=2)):
        call_command("send_outbox")
    assert len(mail.outbox) == 1 and EmailOutbox.objects.get().status == OutboxStatus.SENT


def test_code_is_wiped_from_every_outbox_row_once_sent(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        otp.request_code(EMAIL, None)
    for row in EmailOutbox.objects.all():
        assert "123456" not in row.subject and "123456" not in row.body
    assert EmailOutbox.objects.get().body == WIPED


def test_pending_row_keeps_code_for_retry_but_never_in_subject():
    otp.request_code(EMAIL, None)  # on_commit not run in this test: still queued
    row = EmailOutbox.objects.get()
    assert row.status == OutboxStatus.PENDING and "123456" in row.body and "123456" not in row.subject


def test_failed_for_good_wipes_the_code(monkeypatch):
    otp.request_code(EMAIL, None)

    def boom(self, fail_silently=False):
        raise OSError("smtp down")

    SiteConfig.objects.filter(pk=1).update(otp_minutes=1000)  # the ticks below must not expire the code
    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", boom)
    with freeze_time() as clock:
        for _ in range(5):
            send_pending()
            clock.tick(timedelta(minutes=61))  # past every back-off
    row = EmailOutbox.objects.get()
    assert row.status == OutboxStatus.FAILED and row.body == WIPED


def test_superseded_unsent_code_is_wiped_and_skipped():
    with freeze_time("2026-11-18 10:00:00") as clock:
        otp.request_code(EMAIL, None)
        clock.tick(timedelta(seconds=31))
        otp.request_code(EMAIL, None)
    old, new = EmailOutbox.objects.order_by("created_at")
    assert (old.status, old.body) == (OutboxStatus.SKIPPED, WIPED)
    assert new.status == OutboxStatus.PENDING


def test_expired_unsent_code_is_skipped_and_wiped():
    with freeze_time("2026-11-18 10:00:00") as clock:
        otp.request_code(EMAIL, None)
        clock.tick(timedelta(minutes=11))
        call_command("send_outbox")
    row = EmailOutbox.objects.get()
    assert row.status == OutboxStatus.SKIPPED and row.body == WIPED
    assert mail.outbox == []


def test_claimed_rows_are_not_sent_twice_and_abandoned_claims_are_retaken():
    row = EmailOutbox.objects.create(template_key="x", to_addresses=["a@diasorin.com"], subject="s", body="b")
    EmailOutbox.objects.filter(pk=row.pk).update(
        next_attempt_at=timezone.now() + timedelta(minutes=4)
    )  # held
    assert send_pending() == {"sent": 0, "failed": 0, "skipped": 0}
    EmailOutbox.objects.filter(pk=row.pk).update(
        next_attempt_at=timezone.now() - timedelta(minutes=1)
    )  # lease over
    assert send_pending()["sent"] == 1


def test_smtp_send_happens_after_the_claim_transaction_has_closed(monkeypatch):
    """The claim runs in its own atomic block; nothing from the sender is open while SMTP is talking."""
    EmailOutbox.objects.create(template_key="x", to_addresses=["a@diasorin.com"], subject="s", body="b")
    depth_during_send = []
    real = mail.EmailMessage.send

    def spy(self, fail_silently=False):
        depth_during_send.append(len(connection.savepoint_ids))
        return real(self, fail_silently=fail_silently)

    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", spy)
    send_pending()
    # the test wrapper is the only open atomic block: no savepoint from the sender is still open
    assert depth_during_send == [0]
