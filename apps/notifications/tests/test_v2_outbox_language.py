from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts.services import otp
from apps.notifications.models import EmailOutbox, OutboxStatus
from apps.notifications.services.render import render_email
from apps.notifications.services.sender import RETRY_BACKOFF_MINUTES, send_pending

pytestmark = pytest.mark.django_db


def _row():
    return EmailOutbox.objects.create(
        template_key="submitted", to_addresses=["a@diasorin.com"], subject="s", body="b"
    )


def test_claim_sets_next_attempt_at_not_sent_at(monkeypatch):
    row = _row()
    seen = {}

    def spy(self, fail_silently=False):
        db = EmailOutbox.objects.get(pk=row.pk)
        seen["during"] = (db.sent_at, db.next_attempt_at)

    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", spy)
    start = timezone.now()
    send_pending()
    sent_at, lease = seen["during"]
    assert sent_at is None  # sent_at is only for SENT rows
    assert timedelta(minutes=4) < lease - start <= timedelta(minutes=5, seconds=5)
    row.refresh_from_db()
    assert row.status == OutboxStatus.SENT and row.sent_at is not None and row.next_attempt_at is None


def test_failed_send_schedules_the_next_attempt_with_backoff(monkeypatch):
    row = _row()

    def boom(self, fail_silently=False):
        raise OSError("smtp down")

    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", boom)
    with freeze_time() as clock:
        for attempt, minutes in enumerate(RETRY_BACKOFF_MINUTES, start=1):
            send_pending()
            row.refresh_from_db()
            assert row.status == OutboxStatus.PENDING and row.sent_at is None and row.attempts == attempt
            assert row.next_attempt_at == timezone.now() + timedelta(minutes=minutes)
            assert send_pending()["failed"] == 0  # not due yet
            clock.tick(timedelta(minutes=minutes, seconds=1))
        send_pending()  # 5th failure
    row.refresh_from_db()
    assert row.status == OutboxStatus.FAILED and row.next_attempt_at is None and row.sent_at is None
    assert RETRY_BACKOFF_MINUTES == (1, 5, 15, 60)


def test_italian_user_gets_italian_text_and_unknown_address_gets_english(make_user):
    make_user("anna@diasorin.com", language="it")
    make_user("bob@diasorin.com", language="en")
    ctx = {"request": {"reference": "SR-1"}}

    subject_it, body_it = render_email("verified", ctx, "anna@diasorin.com")
    assert subject_it == "SR-1 verificata — in preparazione" and "verificati" in body_it
    subject_en, body_en = render_email("verified", ctx, "bob@diasorin.com")
    assert subject_en == "SR-1 verified — being prepared" and "has been verified" in body_en
    subject_x, _ = render_email("verified", ctx, "stranger@example.com")
    assert subject_x == subject_en  # no user: English
    assert render_email("verified", ctx, "ANNA@diasorin.com")[0] == subject_it  # case-insensitive


def test_sign_in_email_subject_is_fixed_text_per_language(make_user):
    make_user("anna@diasorin.com", language="it")
    otp.request_code("anna@diasorin.com", None)
    row = EmailOutbox.objects.get()
    assert row.subject == "Il tuo codice di accesso Diasorin" and "123456" not in row.subject
    assert "codice di accesso" in row.body and "123456" in row.body
    otp.request_code("new.person@diasorin.com", None)
    english = EmailOutbox.objects.get(to_addresses=["new.person@diasorin.com"])
    assert english.subject == "Your Diasorin sign-in code" and "one-time sign-in code" in english.body


def test_all_sixteen_templates_have_italian_text():
    from apps.notifications.models import EmailTemplate

    for tpl in EmailTemplate.objects.all():
        assert tpl.subject_it and tpl.body_it, tpl.key
        assert tpl.subject_it != tpl.subject_en
