import pytest
from django.core import mail
from django.core.management import call_command

from apps.accounts.services import otp
from apps.notifications.models import EmailOutbox, EmailTemplate, OutboxStatus

pytestmark = pytest.mark.django_db


def test_otp_email_is_delivered_by_send_outbox():
    otp.request_code("m.rossi@diasorin.com", None)
    assert mail.outbox == []  # queued, not sent yet
    call_command("send_outbox")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["m.rossi@diasorin.com"] and "123456" not in msg.subject and "123456" in msg.body
    row = EmailOutbox.objects.get()
    assert row.status == OutboxStatus.SENT and row.sent_at is not None and row.attempts == 1
    call_command("send_outbox")
    assert len(mail.outbox) == 1  # not re-sent


def test_disabled_template_is_skipped_but_never_the_sign_in_code():
    EmailTemplate.objects.filter(key="otp").update(enabled=False)
    otp.request_code("m.rossi@diasorin.com", None)
    EmailOutbox.objects.create(
        template_key="submitted", to_addresses=["a@diasorin.com"], subject="s", body="b"
    )
    EmailTemplate.objects.filter(key="submitted").update(enabled=False)
    call_command("send_outbox")
    assert len(mail.outbox) == 1
    assert EmailOutbox.objects.get(template_key="submitted").status == OutboxStatus.SKIPPED


def test_transport_failure_is_recorded_and_retried(monkeypatch):
    otp.request_code("m.rossi@diasorin.com", None)

    def boom(self, fail_silently=False):
        raise OSError("smtp down")

    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", boom)
    call_command("send_outbox")
    row = EmailOutbox.objects.get()
    assert row.status == OutboxStatus.PENDING and row.attempts == 1 and "smtp down" in row.last_error
