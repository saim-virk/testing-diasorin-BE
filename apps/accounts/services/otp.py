"""One-time-code sign-in (REQUIREMENTS section 2)."""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import EmailOutbox, OutboxStatus
from apps.notifications.services import dispatcher
from apps.notifications.services.render import OTP_SUBJECT, language_for, render_email
from apps.platform_config.models import SiteConfig

from ..models import OTPChallenge, User
from .access import access_decision, normalize_email

logger = logging.getLogger(__name__)

RESEND_COOLDOWN_SECONDS = 30
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_MINUTES = 15


class AccessRefused(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


class RateLimited(Exception):
    def __init__(self, code: str, retry_after_seconds: int):
        self.code, self.retry_after_seconds = code, retry_after_seconds
        super().__init__(code)


class OTPError(Exception):
    """code is wrong | expired | locked"""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def hash_code(email: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def _render_email(email: str, code: str, minutes: int, language: str | None = None) -> tuple[str, str]:
    """Subject and body in the recipient's language (the subject never carries the code)."""
    rendered = render_email("otp", {"code": code, "minutes": minutes}, email, language, prefer_fallback=True)
    if rendered:
        return rendered
    lang = language_for(email, language, prefer_fallback=True)
    return (
        OTP_SUBJECT[lang],
        f"Your one-time sign-in code is {code}.\nIt expires in {minutes} minutes and can be used once.",
    )


@transaction.atomic
def request_code(email: str, ip: str | None, language: str | None = None) -> dict:
    """`language` (en/it) is the language the person is looking at: the sign-in email uses it, even for a
    known user. Without it the profile language applies, then English."""
    email = normalize_email(email)
    language = language if language in ("en", "it") else ""
    decision = access_decision(email)
    if not decision.ok:
        raise AccessRefused(decision.code, decision.message)
    user = User.objects.filter(email__iexact=email).first()
    if user and not user.is_active:
        raise AccessRefused("blocked", "This account has been deactivated.")

    cfg = SiteConfig.load()
    now = timezone.now()

    latest = OTPChallenge.objects.filter(email=email).order_by("-created_at").first()
    if latest:
        wait = RESEND_COOLDOWN_SECONDS - (now - latest.created_at).total_seconds()
        if wait > 0:
            raise RateLimited("cooldown", int(wait) + 1)

    since = now - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    if OTPChallenge.objects.filter(email=email, created_at__gte=since).count() >= RATE_LIMIT_REQUESTS:
        raise RateLimited("rate_limit", RATE_LIMIT_WINDOW_MINUTES * 60)
    if (
        ip
        and OTPChallenge.objects.filter(ip_address=ip, created_at__gte=since).count() >= RATE_LIMIT_REQUESTS
    ):
        raise RateLimited("rate_limit", RATE_LIMIT_WINDOW_MINUTES * 60)

    # a new request invalidates every earlier open code
    OTPChallenge.objects.filter(email=email, consumed_at__isnull=True).update(consumed_at=now)

    code = f"{secrets.randbelow(10**6):06d}"
    OTPChallenge.objects.create(
        email=email,
        code_hash=hash_code(email, code),
        created_at=now,
        expires_at=now + timedelta(minutes=cfg.otp_minutes),
        ip_address=ip or None,
        language=language,
    )
    subject, body = _render_email(email, code, cfg.otp_minutes, language)
    # an unsent older code is superseded: never send it, and wipe it
    EmailOutbox.objects.filter(template_key="otp", to_addresses=[email], status=OutboxStatus.PENDING).update(
        status=OutboxStatus.SKIPPED, body="[sign-in code removed]"
    )
    row = EmailOutbox.objects.create(template_key="otp", to_addresses=[email], subject=subject, body=body)
    # the background sender picks it up once the challenge is committed; if that fails the row stays PENDING for send_outbox
    dispatcher.after_commit([row.pk])
    return {"expires_in_minutes": cfg.otp_minutes, "resend_after_seconds": RESEND_COOLDOWN_SECONDS}


def _guess_names(email: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"[._\-+]+", email.split("@")[0]) if p]
    parts = [re.sub(r"\d+", "", p) for p in parts]
    parts = [p.capitalize() for p in parts if p]
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def verify_code(email: str, code: str) -> User:
    """Check a code. Errors are raised *after* the transaction commits so the attempt counter sticks."""
    result = _verify(email, code)
    if isinstance(result, Exception):
        raise result
    return result


@transaction.atomic
def _verify(email: str, code: str) -> "User | Exception":
    email = normalize_email(email)
    code = (code or "").strip()
    cfg = SiteConfig.load()
    now = timezone.now()

    challenge = (
        OTPChallenge.objects.select_for_update()
        .filter(email=email, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if challenge is None:
        # nothing open: never requested, already used, or superseded by a newer request
        return OTPError("expired")
    if challenge.attempts >= cfg.otp_max_attempts:
        return OTPError("locked")
    if now > challenge.expires_at:
        return OTPError("expired")

    if not hmac.compare_digest(challenge.code_hash, hash_code(email, code)):
        challenge.attempts += 1
        challenge.save(update_fields=["attempts"])
        return OTPError("locked" if challenge.attempts >= cfg.otp_max_attempts else "wrong")

    decision = access_decision(email)
    if not decision.ok:
        return AccessRefused(decision.code, decision.message)
    user = User.objects.filter(email__iexact=email).first()
    if user is not None and not user.is_active:
        return AccessRefused("blocked", "This account has been deactivated.")

    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])
    if user is None:
        first, last = _guess_names(email)
        user = User.objects.create_user(
            email=email, first_name=first, last_name=last, language=challenge.language or "en"
        )
    user.last_login = now
    user.save(update_fields=["last_login"])
    return user
