"""Data model v2: session revocation, deactivation, permission map."""

from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts import permissions as perms
from apps.accounts.permissions import HasPermission, effective_permissions, has_permission
from apps.accounts.services.sessions import end_sessions
from apps.accounts.services.users import block_email, deactivate_user
from apps.masterdata.models import CostCentre, CostCentreApprover

pytestmark = pytest.mark.django_db

A, B = "a.user@diasorin.com", "b.user@diasorin.com"


def _later(minutes=5):
    return freeze_time(timezone.now() + timedelta(minutes=minutes))


def test_end_sessions_logs_the_user_out_but_not_others(make_user, sign_in):
    ua = make_user(A)
    make_user(B)
    ca, cb = sign_in(A, APIClient()), sign_in(B, APIClient())
    assert ca.get("/api/me").status_code == 200 and cb.get("/api/me").status_code == 200
    with _later():
        end_sessions(ua)
        assert ca.get("/api/me").status_code == 401
        assert cb.get("/api/me").status_code == 200  # normal sessions unaffected


def test_a_session_started_after_the_revocation_works(make_user, sign_in):
    u = make_user(A)
    end_sessions(u)
    with _later():
        c = sign_in(A, APIClient())
        assert c.get("/api/me").status_code == 200


def test_deactivation_logs_out_and_records_who_and_when(make_user, sign_in):
    u, admin = make_user(A), make_user(B, admin=True)
    c = sign_in(A, APIClient())
    with _later():
        deactivate_user(u, by=admin)
        u.refresh_from_db()
        assert u.is_active is False and u.deactivated_by == admin and u.deactivated_at is not None
        assert u.sessions_revoked_at == u.deactivated_at
        assert c.get("/api/me").status_code == 401
    assert u.email == A  # no email scrambling


def test_blocking_an_address_logs_out_its_existing_session(make_user, sign_in):
    make_user(A)
    c = sign_in(A, APIClient())
    with _later():
        block_email(A, "left the company")
        assert c.get("/api/me").status_code == 401


def test_adding_a_role_keeps_the_session_and_shows_the_new_role(make_user, sign_in):
    from apps.accounts.enums import AppRole
    from apps.accounts.models import RoleAssignment
    from apps.accounts.services.roles import assign_role

    u = make_user(A)
    c = sign_in(A, APIClient())
    with _later():
        assign_role(u, AppRole.CUSTOMER_MANAGEMENT)
        assign_role(u, AppRole.CUSTOMER_MANAGEMENT)  # no-op when it already exists
        r = c.get("/api/me")
        assert r.status_code == 200
        assert "customer_management" in r.json()["roles"]
    assert RoleAssignment.objects.filter(user=u).count() == 1


def test_removing_a_role_ends_sessions_via_service_and_via_django_admin_path(make_user, sign_in):
    from apps.accounts.enums import AppRole
    from apps.accounts.models import RoleAssignment
    from apps.accounts.services.roles import assign_role, remove_role

    u = make_user(A)
    assign_role(u, AppRole.CUSTOMER_MANAGEMENT)
    c = sign_in(A, APIClient())
    with _later():
        remove_role(u, AppRole.CUSTOMER_MANAGEMENT)
        assert c.get("/api/me").status_code == 401

    # Django Admin deletes the row object directly (no service)
    ra = RoleAssignment.objects.create(user=u, role=AppRole.CUSTOMER_MANAGEMENT)
    with _later(10):
        c2 = sign_in(A, APIClient())
        assert c2.get("/api/me").status_code == 200
    with _later(20):
        ra.delete()
        assert c2.get("/api/me").status_code == 401


# ---- permission map

ALL_ADMIN_AREAS = [a for a in perms.AREAS if a.startswith("admin.")]


def test_permission_map_covers_every_role_and_area():
    assert set(perms.PERMISSIONS) == {"requester", "approver", "customer_management", "admin"}
    for role, areas in perms.PERMISSIONS.items():
        assert set(areas) == set(perms.AREAS), role
        for actions in areas.values():
            assert set(actions) == set(perms.ACTIONS)


def test_each_roles_map(make_user):
    requester = make_user("r@diasorin.com")
    approver = make_user("ap@diasorin.com")
    cc = CostCentre.objects.create(code="CC-1", name="One")
    CostCentreApprover.objects.create(cost_centre=cc, user=approver)
    cm = make_user("cm@diasorin.com", customer_management=True)
    admin = make_user("ad@diasorin.com", admin=True)

    assert has_permission(requester, "requests", "create")
    assert not has_permission(requester, "approvals", "view")
    assert not has_permission(requester, "workbench", "view")
    assert not any(has_permission(requester, a, "view") for a in ALL_ADMIN_AREAS)

    assert has_permission(approver, "approvals", "decide")
    assert not has_permission(approver, "workbench", "view")

    assert has_permission(cm, "workbench", "manage")
    assert not has_permission(cm, "approvals", "decide")
    assert not any(has_permission(cm, a, "view") for a in ALL_ADMIN_AREAS)

    assert all(has_permission(admin, a, "manage") for a in ALL_ADMIN_AREAS)
    assert has_permission(admin, "approvals", "decide")


def test_effective_map_merges_roles(make_user):
    cm = make_user("cm@diasorin.com", customer_management=True)
    eff = effective_permissions(cm)
    assert eff["requests"]["create"] and eff["workbench"]["view"]
    assert not eff["admin.users"]["view"]
    assert set(eff) == set(perms.AREAS)


def test_has_permission_class_allows_and_denies(make_user, rf):
    admin_cls = HasPermission.require("admin.users", "view")
    req = rf.get("/")
    req.user = make_user("r@diasorin.com")
    assert admin_cls().has_permission(req, None) is False
    req.user = make_user("ad@diasorin.com", admin=True)
    assert admin_cls().has_permission(req, None) is True


def test_me_returns_the_effective_permissions(api, make_user, sign_in):
    make_user("cm@diasorin.com", customer_management=True)
    sign_in("cm@diasorin.com")
    body = api.get("/api/me").json()
    assert body["permissions"]["workbench"]["view"] is True
    assert body["permissions"]["admin.rules"]["manage"] is False


def test_admin_only_endpoint_refuses_a_requester_and_serves_an_admin(api, make_user, sign_in):
    make_user("r@diasorin.com")
    sign_in("r@diasorin.com")
    assert api.get("/api/admin/permissions").status_code == 403
    assert APIClient().get("/api/admin/permissions").status_code == 401
    make_user("ad@diasorin.com", admin=True)
    admin_client = sign_in("ad@diasorin.com", APIClient())
    r = admin_client.get("/api/admin/permissions")
    assert r.status_code == 200
    assert set(r.json()["roles"]) == {"requester", "approver", "customer_management", "admin"}
    assert r.json()["areas"] == list(perms.AREAS)


def test_requests_are_cancelled_never_deleted():
    for role, areas in perms.PERMISSIONS.items():
        assert areas["requests"]["delete"] is False, role
        assert areas["requests"]["cancel"] is True, role
    assert not any(a["delete"] for areas in perms.PERMISSIONS.values() for a in areas.values())
    assert "cancel" in perms.ACTIONS


def test_admin_permissions_endpoint_shows_cancel(make_user, sign_in):
    make_user(A, admin=True)
    c = sign_in(A, APIClient())
    body = c.get("/api/admin/permissions").json()
    assert "cancel" in str(body) and '"delete": true' not in str(body).lower().replace("'", '"').replace(
        "true", "true"
    )


def test_block_via_django_admin_form_ends_the_session(make_user, sign_in):
    make_user(A)
    make_user(B, admin=True)
    ca, cadmin = sign_in(A, APIClient()), sign_in(B, APIClient())
    with _later():
        r = cadmin.post(
            "/django-admin/accounts/blockedemail/add/",
            {"email": A, "reason": "x", "added_at_0": "2026-01-01", "added_at_1": "10:00:00"},
        )
        assert r.status_code == 302
        assert ca.get("/api/me").status_code == 401


def test_a_blocked_row_added_without_the_signal_still_ends_the_session(make_user, sign_in):
    from apps.accounts.models import BlockedEmail

    make_user(A)
    c = sign_in(A, APIClient())
    BlockedEmail.objects.bulk_create([BlockedEmail(email=A)])  # bulk_create sends no post_save
    assert c.get("/api/me").status_code == 401


def test_api_responses_are_no_store(make_user, sign_in):
    make_user(A)
    c = sign_in(A, APIClient())
    assert c.get("/api/me")["Cache-Control"] == "no-store"
    assert APIClient().get("/api/me")["Cache-Control"] == "no-store"  # also on a 401
