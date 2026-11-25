"""Background email sending: one SMTP session per batch, never twice, crash-safe (outbox is the truth)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from freezegun import freeze_time

from apps.notifications.models import EmailOutbox, OutboxStatus
from apps.notifications.services import dispatcher, sender
from apps.notifications.services.sender import send_pending

from .fake_backends import SlowSession

FAKE = "apps.notifications.tests.fake_backends.SlowSession"


def _rows(n=3):
    return [
        EmailOutbox.objects.create(
            template_key="submitted", to_addresses=[f"u{i}@diasorin.com"], subject=f"s{i}", body="b"
        )
        for i in range(n)
    ]


@pytest.mark.django_db
def test_three_emails_use_one_smtp_connection(settings):
    settings.EMAIL_BACKEND = FAKE
    SlowSession.reset()
    _rows(3)
    assert send_pending()["sent"] == 3
    assert SlowSession.opened == 1 and len(SlowSession.sent) == 3


@pytest.mark.django_db
def test_a_failed_row_does_not_stop_the_batch_and_the_session_reconnects(settings, monkeypatch):
    settings.EMAIL_BACKEND = FAKE
    SlowSession.reset()
    rows = _rows(3)
    real = SlowSession.send_messages

    def flaky(self, messages):
        if messages[0].subject == "s1":
            raise OSError("smtp hiccup")
        return real(self, messages)

    monkeypatch.setattr(SlowSession, "send_messages", flaky)
    assert send_pending() == {"sent": 2, "failed": 1, "skipped": 0}
    assert EmailOutbox.objects.get(pk=rows[1].pk).status == OutboxStatus.PENDING
    assert SlowSession.opened == 2  # the session was dropped after the failure and opened again


@pytest.mark.django_db
def test_no_row_is_sent_twice():
    rows = _rows(2)
    ids = [r.pk for r in rows]
    assert send_pending(ids=ids)["sent"] == 2
    assert send_pending(ids=ids)["sent"] == 0  # already SENT
    # a row another sender has claimed (lease) is left alone by send_outbox
    more = _rows(1)
    sender._claim(10, [more[0].pk])
    mail.outbox.clear()
    call_command("send_outbox")
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_crash_in_the_sender_leaves_rows_pending_for_send_outbox(monkeypatch):
    _rows(2)

    def crash(*args, **kwargs):
        raise RuntimeError("worker died")

    with monkeypatch.context() as m:
        m.setattr(sender, "_deliver", crash)
        dispatcher.dispatch(
            [r.pk for r in EmailOutbox.objects.all()]
        )  # sync in tests; the error is swallowed
    assert EmailOutbox.objects.filter(status=OutboxStatus.PENDING).count() == 2
    call_command("send_outbox")
    assert mail.outbox == []  # still leased by the dead sender
    with freeze_time(timezone.now() + timedelta(minutes=6)):
        call_command("send_outbox")
    assert len(mail.outbox) == 2
    assert EmailOutbox.objects.filter(status=OutboxStatus.SENT).count() == 2


@pytest.mark.django_db(transaction=True)
def test_the_worker_thread_survives_a_crash_and_sends_the_next_batch(settings, monkeypatch):
    settings.EMAIL_WORKER_SYNC = False
    first, second = _rows(1), _rows(1)
    with monkeypatch.context() as m:
        m.setattr(sender, "_deliver", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        dispatcher.dispatch([first[0].pk])
        assert dispatcher.wait_idle(10)
    assert dispatcher._thread.is_alive()
    dispatcher.dispatch([second[0].pk])
    assert dispatcher.wait_idle(10)
    assert EmailOutbox.objects.get(pk=second[0].pk).status == OutboxStatus.SENT
    assert EmailOutbox.objects.get(pk=first[0].pk).status == OutboxStatus.PENDING
