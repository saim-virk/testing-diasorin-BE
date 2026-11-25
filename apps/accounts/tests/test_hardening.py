"""Section 0b: open redirect, login CSRF, admin hides sign-in emails, session cleanup."""

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.notifications.models import EmailOutbox

pytestmark = pytest.mark.django_db

EMAIL = "m.rossi@diasorin.com"


def test_open_redirect_is_blocked(api, make_user, sign_in):
    make_user("admin@diasorin.com", admin=True)
    sign_in("admin@diasorin.com")
    for evil in ("//evil.example", "https://evil.example/x", "/\\evil.example", "javascript:alert(1)"):
        r = api.get("/django-admin/login/", {"next": evil})
        assert r.status_code == 302 and r["Location"] == "/django-admin/", evil
    r = api.get("/django-admin/login/", {"next": "/django-admin/accounts/user/"})
    assert r["Location"] == "/django-admin/accounts/user/"


def test_outbox_admin_hides_sign_in_email(api, make_user, sign_in):
    make_user("admin@diasorin.com", admin=True)
    victim = make_user("victim@diasorin.com")
    sign_in("admin@diasorin.com")
    row = EmailOutbox.objects.create(
        template_key="otp", to_addresses=[victim.email], subject="Your sign-in code", body="code 987654"
    )
    listing = api.get("/django-admin/notifications/emailoutbox/").content.decode()
    detail = api.get(f"/django-admin/notifications/emailoutbox/{row.pk}/change/").content.decode()
    searched = api.get("/django-admin/notifications/emailoutbox/?q=987654")
    assert "987654" not in listing and "987654" not in detail
    assert "[hidden: sign-in email]" in detail
    assert "0 results" in searched.content.decode()  # body is not searchable (the box just echoes the query)


def test_request_code_and_verify_require_csrf_token():
    c = APIClient(enforce_csrf_checks=True)
    assert c.post("/api/auth/request-code", {"email": EMAIL}, format="json").status_code == 403
    assert c.post("/api/auth/verify", {"email": EMAIL, "code": "123456"}, format="json").status_code == 403
    token = c.get("/api/auth/csrf").cookies["csrftoken"].value
    r = c.post("/api/auth/request-code", {"email": EMAIL}, format="json", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200
    r = c.post("/api/auth/verify", {"email": EMAIL, "code": "123456"}, format="json", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200


def test_full_flow_with_csrf_enforced_including_token_rotation(make_user):
    make_user(EMAIL)
    c = APIClient(enforce_csrf_checks=True)
    token = c.get("/api/auth/csrf").cookies["csrftoken"].value
    c.post("/api/auth/request-code", {"email": EMAIL}, format="json", HTTP_X_CSRFTOKEN=token)
    r = c.post("/api/auth/verify", {"email": EMAIL, "code": "123456"}, format="json", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200
    new_token = c.cookies["csrftoken"].value  # rotated on login; the SPA re-reads the cookie
    assert c.patch("/api/me", {"phone": "1"}, format="json").status_code == 403
    assert c.patch("/api/me", {"phone": "1"}, format="json", HTTP_X_CSRFTOKEN=new_token).status_code == 200
    assert c.post("/api/auth/logout", HTTP_X_CSRFTOKEN=new_token).status_code == 204


def test_csrf_endpoint_itself_needs_no_token():
    assert APIClient(enforce_csrf_checks=True).get("/api/auth/csrf").status_code == 204


def test_cleanup_sessions_removes_expired_sessions_only(make_user, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)
    call_command("cleanup_sessions", verbosity=0)
    assert Session.objects.count() == 1  # the live session survives
    Session.objects.update(expire_date="2020-01-01T00:00:00Z")  # now expired
    call_command("cleanup_sessions", verbosity=0)
    assert Session.objects.count() == 0
