import logging

import pytest
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import get_connection
from django.core.management import call_command

from apps.notifications.models import EmailOutbox
from apps.notifications.services.mailconfig import build_message, check_email_settings
from apps.notifications.services.sender import send_pending

pytestmark = pytest.mark.django_db

SMTP = "django.core.mail.backends.smtp.EmailBackend"


def test_no_redirect_when_unset(settings):
    settings.EMAIL_REDIRECT_TO = ""
    settings.EMAIL_FROM_OVERRIDE = ""
    msg = build_message("Hello", "Body", "noreply@diasorin.com", ["a@diasorin.com", "b@diasorin.com"])
    assert msg.to == ["a@diasorin.com", "b@diasorin.com"]
    assert msg.subject == "Hello" and msg.body == "Body"
    assert msg.from_email == "noreply@diasorin.com"


def test_redirect_rewrites_recipients_subject_and_body(settings):
    settings.EMAIL_REDIRECT_TO = "me@example.com"
    msg = build_message("Hello", "Body", "noreply@diasorin.com", ["a@diasorin.com", "b@diasorin.com"])
    assert msg.to == ["me@example.com"] and msg.cc == [] and msg.bcc == []
    assert msg.subject == "[TEST → a@diasorin.com, b@diasorin.com] Hello"
    assert msg.body.startswith("Originally to: a@diasorin.com, b@diasorin.com\n\n")
    assert msg.body.endswith("Body")


def test_from_override_applied(settings):
    settings.EMAIL_FROM_OVERRIDE = "owned@example.com"
    msg = build_message("s", "b", "noreply@diasorin.com", ["a@diasorin.com"])
    assert msg.from_email == "owned@example.com"


def test_redirect_and_override_apply_through_the_outbox_sender(settings):
    settings.EMAIL_REDIRECT_TO = "me@example.com"
    settings.EMAIL_FROM_OVERRIDE = "owned@example.com"
    EmailOutbox.objects.create(
        template_key="submitted", to_addresses=["x@diasorin.com"], subject="s", body="b"
    )
    assert send_pending()["sent"] == 1
    msg = mail.outbox[0]
    assert msg.to == ["me@example.com"] and msg.from_email == "owned@example.com"
    assert "Originally to: x@diasorin.com" in msg.body


def test_ssl_and_tls_flags_reach_the_smtp_backend(settings):
    settings.EMAIL_BACKEND = SMTP
    settings.EMAIL_USE_SSL, settings.EMAIL_USE_TLS, settings.EMAIL_TIMEOUT = True, False, 20
    conn = get_connection()
    assert conn.use_ssl is True and conn.use_tls is False and conn.timeout == 20
    settings.EMAIL_USE_SSL, settings.EMAIL_USE_TLS = False, True
    conn = get_connection()
    assert conn.use_ssl is False and conn.use_tls is True


def test_tls_and_ssl_together_are_refused(settings):
    settings.EMAIL_USE_SSL = settings.EMAIL_USE_TLS = True
    with pytest.raises(ImproperlyConfigured):
        check_email_settings()


def test_loud_warning_for_real_smtp_in_debug_without_redirect(settings, caplog):
    settings.DEBUG, settings.EMAIL_REDIRECT_TO = True, ""
    settings.EMAIL_BACKEND, settings.EMAIL_HOST = SMTP, "smtp.gmail.com"
    settings.EMAIL_USE_SSL, settings.EMAIL_USE_TLS = False, True
    with caplog.at_level(logging.WARNING):
        check_email_settings()
    assert "EMAIL_REDIRECT_TO" in caplog.text
    caplog.clear()
    settings.EMAIL_REDIRECT_TO = "me@example.com"
    with caplog.at_level(logging.WARNING):
        check_email_settings()
    assert caplog.text == ""


def test_send_test_email_command(settings):
    settings.EMAIL_REDIRECT_TO = "me@example.com"
    call_command("send_test_email")
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["me@example.com"]
    mail.outbox.clear()
    settings.EMAIL_REDIRECT_TO = ""
    call_command("send_test_email", "--to", "you@example.com")
    assert mail.outbox[0].to == ["you@example.com"]


def test_send_test_email_needs_a_recipient_when_no_redirect(settings):
    from django.core.management.base import CommandError

    settings.EMAIL_REDIRECT_TO = ""
    with pytest.raises(CommandError):
        call_command("send_test_email")
    assert mail.outbox == []


def test_send_test_email_reports_smtp_error(monkeypatch, capsys):
    def boom(self, fail_silently=False):
        raise OSError("connection refused")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", boom)
    with pytest.raises(SystemExit):
        call_command("send_test_email", "--to", "you@example.com")
    assert "connection refused" in capsys.readouterr().err
