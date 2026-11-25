"""Render an email template in the recipient's language (English when the address has no user)."""

from django.template import Context, Template

from apps.accounts.models import User

from ..models import EmailTemplate

LANGUAGES = ("en", "it")

# The sign-in subject is fixed text per language: it never carries the code (outbox rows are
# visible in Django Admin).
OTP_SUBJECT = {"en": "Your Diasorin sign-in code", "it": "Il tuo codice di accesso Diasorin"}
OTP_KEY = "otp"


def language_for(address: str, fallback: str | None = None, *, prefer_fallback: bool = False) -> str:
    """The user's own language; `fallback` (en/it) only when the address has no user yet.

    With `prefer_fallback`, a valid `fallback` wins even for a known user (the sign-in email uses the
    language the person is looking at); without a valid one the profile language applies.
    """
    if prefer_fallback and fallback in LANGUAGES:
        return fallback
    user = User.objects.filter(email__iexact=address.strip()).first()
    if user is not None:
        return user.language if user.language in LANGUAGES else "en"
    return fallback if fallback in LANGUAGES else "en"


def render_email(
    key: str,
    context: dict,
    to_address: str,
    fallback_language: str | None = None,
    *,
    prefer_fallback: bool = False,
) -> tuple[str, str] | None:
    """(subject, body) for `key` in the recipient's language, or None if the template does not exist.

    A missing Italian text falls back to English.
    """
    tpl = EmailTemplate.objects.filter(key=key).first()
    if tpl is None:
        return None
    lang = language_for(to_address, fallback_language, prefer_fallback=prefer_fallback)
    subject_src = getattr(tpl, f"subject_{lang}") or tpl.subject_en
    body_src = getattr(tpl, f"body_{lang}") or tpl.body_en
    ctx = Context(context, autoescape=False)  # plain-text email: no HTML escaping (O'Brien, L'approvatore)
    subject = OTP_SUBJECT[lang] if key == OTP_KEY else Template(subject_src).render(ctx)
    return subject, Template(body_src).render(ctx)
