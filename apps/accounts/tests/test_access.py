import pytest

from apps.accounts.models import AllowedEmail, BlockedEmail
from apps.accounts.services.access import access_decision
from apps.platform_config.models import AccessMode, SiteConfig

pytestmark = pytest.mark.django_db


def set_mode(mode):
    cfg = SiteConfig.load()
    cfg.access_mode = mode
    cfg.save()


def test_malformed_address():
    for bad in ["", "plain", "a@b", "a b@c.com", "@x.com"]:
        d = access_decision(bad)
        assert (d.ok, d.code) == (False, "format"), bad


def test_blocked_in_both_modes_with_reason():
    BlockedEmail.objects.create(email="gone@diasorin.com", reason="Left")
    for mode in (AccessMode.DOMAIN, AccessMode.ALLOWLIST):
        set_mode(mode)
        d = access_decision("gone@diasorin.com")
        assert (d.ok, d.code) == (False, "blocked")
        assert "Left" in d.message


def test_allowed_domain_and_disallowed_domain():
    assert access_decision("x@diasorin.com").code == "domain"
    assert access_decision("x@diasorin.com").ok
    d = access_decision("x@gmail.com")
    assert (d.ok, d.code) == (False, "domain")
    assert "diasorin.com" in d.message  # names the allowed domains


def test_allow_listed_external_address():
    AllowedEmail.objects.create(email="ext@partner.it")
    d = access_decision("ext@partner.it")
    assert (d.ok, d.code) == (True, "allowlist")


def test_role_holder_on_disallowed_domain_in_allowlist_mode(make_user):
    make_user("boss@elsewhere.org", admin=True)
    set_mode(AccessMode.ALLOWLIST)
    d = access_decision("boss@elsewhere.org")
    assert (d.ok, d.code) == (True, "allowlist")


def test_not_listed_in_allowlist_mode_even_on_allowed_domain():
    set_mode(AccessMode.ALLOWLIST)
    d = access_decision("x@diasorin.com")
    assert (d.ok, d.code) == (False, "notlisted")


def test_emails_are_case_insensitive(make_user):
    AllowedEmail.objects.create(email="Ext@Partner.it")
    BlockedEmail.objects.create(email="Gone@Diasorin.com")
    assert access_decision("EXT@PARTNER.IT").ok
    assert access_decision("  gone@DIASORIN.com ").code == "blocked"
    assert access_decision("X@DIASORIN.COM").ok
