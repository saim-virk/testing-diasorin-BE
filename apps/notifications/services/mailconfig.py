"""Outgoing-mail settings: safety net for real-SMTP testing, From override, startup checks.

Every email goes through `build_message`, so the redirect and the From override apply to every
template (sign-in codes, notifications, the test command).
"""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def build_message(subject: str, body: str, sender: str, to: list[str]) -> EmailMessage:
    """Apply EMAIL_FROM_OVERRIDE and EMAIL_REDIRECT_TO, then build the message."""
    from_email = getattr(settings, "EMAIL_FROM_OVERRIDE", "") or sender
    redirect = getattr(settings, "EMAIL_REDIRECT_TO", "")
    if redirect:
        originals = ", ".join(to) or "(nobody)"
        subject = f"[TEST → {originals}] {subject}"
        body = f"Originally to: {originals}\n\n{body}"
        to = [redirect]
    return EmailMessage(subject, body, from_email, list(to))


def check_email_settings() -> None:
    """Run at startup: reject contradictory flags, warn loudly about unsafe test setups."""
    if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
        raise ImproperlyConfigured(
            "EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive: use TLS (STARTTLS, port 587) "
            "or SSL (port 465), not both."
        )
    is_smtp = settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")
    local = settings.EMAIL_HOST in LOCAL_HOSTS
    if settings.DEBUG and is_smtp and not local and not settings.EMAIL_REDIRECT_TO:
        log.warning(
            "EMAIL SAFETY: DEBUG=True with a real SMTP server (%s) and no EMAIL_REDIRECT_TO. "
            "Seed data uses real-looking @diasorin.com addresses; test emails could reach real "
            "people. Set EMAIL_REDIRECT_TO to your own address.",
            settings.EMAIL_HOST,
        )
