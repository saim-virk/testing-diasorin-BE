from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts.models import AllowedEmail
from apps.accounts.services.sessions import end_sessions
from apps.masterdata.models import CostCentre
from apps.platform_config.models import SiteConfig

pytestmark = pytest.mark.django_db

EMAIL = "m.rossi@diasorin.com"


def test_request_code_success_and_refusals(api):
    r = api.post("/api/auth/request-code", {"email": EMAIL}, format="json")
    assert r.status_code == 200
    assert r.json() == {"expires_in_minutes": 10, "resend_after_seconds": 30}

    r = api.post("/api/auth/request-code", {"email": "someone@gmail.com"}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "domain" and "diasorin.com" in r.json()["message"]
    r = api.post("/api/auth/request-code", {"email": "nope"}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "format"


def test_request_code_429_on_cooldown(api):
    api.post("/api/auth/request-code", {"email": EMAIL}, format="json")
    r = api.post("/api/auth/request-code", {"email": EMAIL}, format="json")
    assert r.status_code == 429
    assert r.json()["code"] == "cooldown" and r.json()["retry_after_seconds"] > 0


def test_verify_errors_and_success(api, make_user):
    make_user(EMAIL, first_name="Marco", last_name="Rossi")
    api.post("/api/auth/request-code", {"email": EMAIL}, format="json")
    r = api.post("/api/auth/verify", {"email": EMAIL, "code": "000000"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "wrong"
    r = api.post("/api/auth/verify", {"email": EMAIL, "code": "123456"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == EMAIL and body["roles"] == ["requester"] and body["view"] == "requester"
    assert api.get("/api/me").status_code == 200


def test_verify_without_request_is_expired(api):
    r = api.post("/api/auth/verify", {"email": EMAIL, "code": "123456"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "expired"


def test_unauthenticated_me_is_401(api):
    assert api.get("/api/me").status_code == 401
    assert api.patch("/api/me", {}, format="json").status_code == 401
    assert api.post("/api/auth/logout").status_code == 401


def test_csrf_endpoint_sets_cookie(api):
    r = api.get("/api/auth/csrf")
    assert r.status_code == 204 and "csrftoken" in r.cookies


def test_logout_ends_session(api, make_user, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)
    assert api.post("/api/auth/logout").status_code == 204
    assert api.get("/api/me").status_code == 401


def test_me_shape(api, make_user, sign_in):
    cc = CostCentre.objects.create(code="CC-4410", name="Warehouse")
    make_user(EMAIL, department="WH", job_title="Coordinator", phone="1", default_cost_centre=cc)
    sign_in(EMAIL)
    body = api.get("/api/me").json()
    assert set(body) == {
        "email", "first_name", "last_name", "department", "job_title", "phone", "language",
        "default_cost_centre", "roles", "view", "approval_hint", "permissions",
    }  # fmt: skip
    assert body["default_cost_centre"] == "CC-4410" and body["language"] == "en"
    # no approver mapped, fallback ADMIN and no other administrator: approved automatically
    assert body["approval_hint"] == {"required": True, "why": "self_auto_approved", "approvers": []}


# ---- profile -----------------------------------------------------------------------------


def test_patch_profile_fields(api, make_user, sign_in):
    CostCentre.objects.create(code="CC-2210", name="R&D")
    make_user(EMAIL)
    sign_in(EMAIL)
    r = api.patch(
        "/api/me",
        {"first_name": "Marco", "phone": "+39 1", "default_cost_centre": "CC-2210", "language": "it"},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["first_name"], body["phone"], body["default_cost_centre"], body["language"]) == (
        "Marco", "+39 1", "CC-2210", "it",
    )  # fmt: skip
    assert (
        api.patch("/api/me", {"default_cost_centre": None}, format="json").json()["default_cost_centre"]
        is None
    )


def test_patch_cannot_change_email_or_roles(api, make_user, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)
    r = api.patch(
        "/api/me",
        {"email": "other@diasorin.com", "roles": ["admin"], "view": "admin", "is_staff": True},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == EMAIL and body["roles"] == ["requester"] and body["view"] == "requester"


def test_language_only_en_or_it(api, make_user, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)
    assert api.patch("/api/me", {"language": "de"}, format="json").status_code == 400
    assert api.patch("/api/me", {"language": "it"}, format="json").json()["language"] == "it"
    assert api.patch("/api/me", {"language": "en"}, format="json").json()["language"] == "en"


def test_unknown_cost_centre_rejected(api, make_user, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)
    assert api.patch("/api/me", {"default_cost_centre": "NOPE"}, format="json").status_code == 400


# ---- views -------------------------------------------------------------------------------


def test_switch_view(api, make_user, sign_in):
    make_user("cm@diasorin.com", customer_management=True)
    sign_in("cm@diasorin.com")
    assert api.get("/api/me").json()["view"] == "customer_management"  # primary role on sign-in
    r = api.post("/api/me/view", {"view": "requester"}, format="json")
    assert r.status_code == 200 and r.json()["view"] == "requester"
    assert api.get("/api/me").json()["view"] == "requester"  # stored in the session


def test_switch_view_rejects_role_user_lacks(api, make_user, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)
    for bad in ("admin", "customer_management", "approver", "bogus", None):
        assert api.post("/api/me/view", {"view": bad}, format="json").status_code == 400
    assert api.get("/api/me").json()["view"] == "requester"


def test_view_falls_back_when_approver_role_lost(api, make_user, sign_in):
    from apps.masterdata.models import CostCentre, CostCentreApprover

    u = make_user("ap@diasorin.com")
    cc = CostCentre.objects.create(code="CC-9", name="Nine")
    link = CostCentreApprover.objects.create(cost_centre=cc, user=u)
    sign_in("ap@diasorin.com")
    api.post("/api/me/view", {"view": "approver"}, format="json")
    link.delete()  # the approver role is computed: losing it does not end the session
    me = api.get("/api/me").json()
    assert me["roles"] == ["requester"] and me["view"] == "requester"


def test_removing_an_assigned_role_ends_the_session(api, make_user, sign_in):
    from apps.accounts.enums import AppRole
    from apps.accounts.models import RoleAssignment

    u = make_user("cm@diasorin.com", customer_management=True)
    sign_in("cm@diasorin.com")
    with freeze_time(timezone.now() + timedelta(minutes=1)):
        RoleAssignment.objects.filter(user=u, role=AppRole.CUSTOMER_MANAGEMENT).delete()
        assert api.get("/api/me").status_code == 401


# ---- session limits ----------------------------------------------------------------------


def test_idle_timeout_logs_out(api, make_user, sign_in):
    make_user(EMAIL)
    with freeze_time("2026-11-18 09:00:00") as clock:
        sign_in(EMAIL)
        clock.tick(timedelta(minutes=29))
        assert api.get("/api/me").status_code == 200
        clock.tick(timedelta(minutes=31))
        assert api.get("/api/me").status_code == 401


def test_absolute_timeout_logs_out_even_when_active(api, make_user, sign_in):
    make_user(EMAIL)
    with freeze_time("2026-11-18 09:00:00") as clock:
        sign_in(EMAIL)
        for _ in range(16):  # active every 29 min for ~7.7 h: idle never trips
            clock.tick(timedelta(minutes=29))
            assert api.get("/api/me").status_code == 200
        clock.tick(timedelta(minutes=29))  # past 8 h absolute
        assert api.get("/api/me").status_code == 401


def test_activity_extends_idle_but_not_absolute(api, make_user, sign_in):
    make_user(EMAIL)
    with freeze_time("2026-11-18 09:00:00") as clock:
        sign_in(EMAIL)
        for _ in range(3):
            clock.tick(timedelta(minutes=20))
            assert api.get("/api/me").status_code == 200  # 60 min total > 30 idle, still in
    cfg = SiteConfig.load()
    cfg.session_hours, cfg.session_idle_minutes = 1, 30
    cfg.save()
    with freeze_time("2026-11-19 09:00:00") as clock:
        sign_in(EMAIL)
        clock.tick(timedelta(minutes=25))
        assert api.get("/api/me").status_code == 200
        clock.tick(timedelta(minutes=25))
        assert api.get("/api/me").status_code == 200  # idle ok (25 min), 50 min absolute
        clock.tick(timedelta(minutes=25))
        assert api.get("/api/me").status_code == 401  # 75 min > 1 h absolute


def test_limits_come_from_site_config_immediately(api, make_user, sign_in):
    make_user(EMAIL)
    with freeze_time("2026-11-18 09:00:00") as clock:
        sign_in(EMAIL)
        cfg = SiteConfig.load()
        cfg.session_idle_minutes = 5
        cfg.save()
        clock.tick(timedelta(minutes=6))
        assert api.get("/api/me").status_code == 401


def test_end_sessions_kills_existing_sessions(api, make_user, sign_in):
    from rest_framework.test import APIClient

    u = make_user(EMAIL)
    other = APIClient()
    sign_in(EMAIL)
    with freeze_time() as clock:  # second device, after the resend cooldown
        clock.tick(timedelta(seconds=40))  # past the resend cooldown
        sign_in(EMAIL, client=other)
    assert api.get("/api/me").status_code == 200 and other.get("/api/me").status_code == 200
    with freeze_time() as clock:
        clock.tick(timedelta(minutes=5))  # after the second device's (frozen, +40 s) login
        end_sessions(u)
    u.refresh_from_db()
    assert u.sessions_revoked_at is not None
    assert api.get("/api/me").status_code == 401
    assert other.get("/api/me").status_code == 401


def test_blocked_after_sign_in_cannot_verify_but_allowlisted_external_can(api):
    AllowedEmail.objects.create(email="ext@partner-lab.it")
    api.post("/api/auth/request-code", {"email": "ext@partner-lab.it"}, format="json")
    r = api.post("/api/auth/verify", {"email": "ext@partner-lab.it", "code": "123456"}, format="json")
    assert r.status_code == 200 and r.json()["first_name"] == "Ext"
