from datetime import timedelta

import pytest
from freezegun import freeze_time

from apps.accounts.models import OTPChallenge, User
from apps.accounts.services import otp
from apps.notifications.models import EmailOutbox
from apps.platform_config.models import SiteConfig

pytestmark = pytest.mark.django_db

EMAIL = "m.rossi@diasorin.com"


def test_request_creates_hashed_challenge_and_outbox_email():
    out = otp.request_code(EMAIL, "10.0.0.1")
    assert out == {"expires_in_minutes": 10, "resend_after_seconds": 30}
    ch = OTPChallenge.objects.get()
    assert ch.code_hash and "123456" not in ch.code_hash  # never plaintext
    assert ch.ip_address == "10.0.0.1"
    mail = EmailOutbox.objects.get(template_key="otp")
    assert mail.to_addresses == [EMAIL]
    assert "123456" in mail.body and "10 minutes" in mail.body


def test_refused_address_creates_nothing():
    with pytest.raises(otp.AccessRefused) as e:
        otp.request_code("someone@gmail.com", None)
    assert e.value.code == "domain"
    assert not OTPChallenge.objects.exists() and not EmailOutbox.objects.exists()


def test_wrong_code_increments_attempts_then_locks():
    otp.request_code(EMAIL, None)
    max_attempts = SiteConfig.load().otp_max_attempts
    for i in range(1, max_attempts):
        with pytest.raises(otp.OTPError) as e:
            otp.verify_code(EMAIL, "000000")
        assert e.value.code == "wrong"
        assert OTPChallenge.objects.get().attempts == i
    with pytest.raises(otp.OTPError) as e:
        otp.verify_code(EMAIL, "000000")
    assert e.value.code == "locked"
    # locked: even the right code no longer works
    with pytest.raises(otp.OTPError) as e:
        otp.verify_code(EMAIL, "123456")
    assert e.value.code == "locked"


def test_expiry():
    with freeze_time("2026-11-18 10:00:00") as clock:
        otp.request_code(EMAIL, None)
        clock.tick(timedelta(minutes=10, seconds=1))
        with pytest.raises(otp.OTPError) as e:
            otp.verify_code(EMAIL, "123456")
        assert e.value.code == "expired"


def test_code_is_single_use():
    otp.request_code(EMAIL, None)
    otp.verify_code(EMAIL, "123456")
    with pytest.raises(otp.OTPError) as e:
        otp.verify_code(EMAIL, "123456")
    assert e.value.code == "expired"


def test_new_request_invalidates_the_old_code():
    with freeze_time("2026-11-18 10:00:00") as clock:
        otp.request_code(EMAIL, None)
        first = OTPChallenge.objects.get()
        clock.tick(timedelta(seconds=31))
        otp.request_code(EMAIL, None)
        first.refresh_from_db()
        assert first.consumed_at is not None
        assert OTPChallenge.objects.filter(consumed_at__isnull=True).count() == 1


def test_resend_cooldown_30_seconds():
    with freeze_time("2026-11-18 10:00:00") as clock:
        otp.request_code(EMAIL, None)
        clock.tick(timedelta(seconds=10))
        with pytest.raises(otp.RateLimited) as e:
            otp.request_code(EMAIL, None)
        assert e.value.code == "cooldown" and 0 < e.value.retry_after_seconds <= 30
        clock.tick(timedelta(seconds=21))
        otp.request_code(EMAIL, None)


def test_rate_limit_per_email():
    with freeze_time("2026-11-18 10:00:00") as clock:
        for _ in range(5):
            otp.request_code(EMAIL, None)
            clock.tick(timedelta(seconds=31))
        with pytest.raises(otp.RateLimited) as e:
            otp.request_code(EMAIL, None)
        assert e.value.code == "rate_limit"
        clock.tick(timedelta(minutes=15))
        otp.request_code(EMAIL, None)  # window passed


def test_rate_limit_per_ip():
    with freeze_time("2026-11-18 10:00:00") as clock:
        for i in range(5):
            otp.request_code(f"user{i}@diasorin.com", "10.9.9.9")
            clock.tick(timedelta(seconds=1))
        with pytest.raises(otp.RateLimited) as e:
            otp.request_code("another@diasorin.com", "10.9.9.9")
        assert e.value.code == "rate_limit"
        otp.request_code("another@diasorin.com", "10.1.1.1")  # a different address is unaffected


def test_unknown_allowed_address_creates_user_with_guessed_names():
    otp.request_code("anna.maria.greco@diasorin.com", None)
    user = otp.verify_code("anna.maria.greco@diasorin.com", "123456")
    assert (user.first_name, user.last_name) == ("Anna", "Maria Greco")
    assert user.last_login is not None and not user.has_usable_password()
    otp.request_code("j.doe@diasorin.com", None)
    u2 = otp.verify_code("J.Doe@diasorin.com", "123456")
    assert (u2.first_name, u2.last_name) == ("J", "Doe")


def test_known_user_is_reused_case_insensitively(make_user):
    make_user("g.ferrari@diasorin.com", first_name="Giulia")
    otp.request_code("G.Ferrari@diasorin.com", None)
    user = otp.verify_code("g.ferrari@diasorin.com", "123456")
    assert User.objects.count() == 1 and user.first_name == "Giulia"


def test_deactivated_user_refused(make_user):
    make_user(EMAIL, is_active=False)
    with pytest.raises(otp.AccessRefused):
        otp.request_code(EMAIL, None)


def test_first_time_user_gets_the_sign_in_email_in_the_chosen_language():
    from apps.accounts.models import User
    from apps.notifications.models import EmailOutbox

    email = "nuovo.utente@diasorin.com"
    otp.request_code(email, None, "it")
    assert (
        EmailOutbox.objects.filter(to_addresses=[email]).latest("id").subject
        == "Il tuo codice di accesso Diasorin"
    )
    # the language is kept on the challenge and saved on the new user at verify
    from apps.accounts.models import OTPChallenge

    ch = OTPChallenge.objects.get(email=email)
    assert ch.language == "it"
    code = "123456"
    ch.code_hash = otp.hash_code(email, code)
    ch.save()
    assert otp.verify_code(email, code).language == "it"
    assert User.objects.get(email=email).language == "it"


def test_known_user_gets_the_language_of_the_request(make_user):
    make_user("en.user@diasorin.com")  # profile language en
    otp.request_code("en.user@diasorin.com", None, "it")
    mail = EmailOutbox.objects.latest("id")
    assert mail.subject == "Il tuo codice di accesso Diasorin"
    assert "codice" in mail.body.lower()


def test_without_a_request_language_the_profile_language_is_used(make_user):
    make_user("it.user@diasorin.com", language="it")
    otp.request_code("it.user@diasorin.com", None)
    assert EmailOutbox.objects.latest("id").subject == "Il tuo codice di accesso Diasorin"
    make_user("en2.user@diasorin.com")
    otp.request_code("en2.user@diasorin.com", None, "")
    assert EmailOutbox.objects.latest("id").subject == "Your Diasorin sign-in code"


def test_unknown_address_with_italian_gets_italian():
    otp.request_code("new.person@diasorin.com", None, "it")
    assert EmailOutbox.objects.latest("id").subject == "Il tuo codice di accesso Diasorin"


def test_other_emails_keep_the_profile_language(make_user):
    from apps.notifications.services.render import language_for

    make_user("en.user@diasorin.com")
    assert language_for("en.user@diasorin.com", "it") == "en"


def test_unknown_language_falls_back_to_english():
    from apps.notifications.models import EmailOutbox

    otp.request_code("x.y@diasorin.com", None, "de")
    assert EmailOutbox.objects.latest("id").subject == "Your Diasorin sign-in code"
