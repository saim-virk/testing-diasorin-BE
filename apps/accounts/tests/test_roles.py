import pytest

from apps.accounts.enums import AppRole
from apps.accounts.models import RoleAssignment
from apps.accounts.services import roles
from apps.masterdata.models import CostCentre, CostCentreApprover
from apps.shipments.enums import RoundState
from apps.shipments.models import ApprovalRound, ShipmentRequest

pytestmark = pytest.mark.django_db


def test_everyone_is_a_requester(make_user):
    u = make_user()
    assert roles.roles_for(u) == ["requester"]
    assert roles.primary_role(u) == "requester"


def test_approver_via_cost_centre_mapping(make_user):
    u = make_user("g.ferrari@diasorin.com")
    cc = CostCentre.objects.create(code="CC-1", name="One")
    CostCentreApprover.objects.create(cost_centre=cc, user=u)
    assert roles.roles_for(u) == ["requester", "approver"]
    assert roles.primary_role(u) == "approver"


def test_approver_via_pending_round_eligibility_only(make_user):
    requester = make_user("req@diasorin.com")
    boss = make_user("boss@diasorin.com")
    assert roles.roles_for(boss) == ["requester"]
    req = ShipmentRequest.objects.create(reference="DSF-2026-0001", requester=requester)
    rnd = ApprovalRound.objects.create(request=req, round_number=1, state=RoundState.PENDING)
    rnd.eligible_approvers.add(boss)
    assert "approver" in roles.roles_for(boss)
    # once the round is decided the eligibility no longer counts
    rnd.state = RoundState.APPROVED
    rnd.save()
    assert roles.roles_for(boss) == ["requester"]


def test_customer_management_and_admin(make_user):
    cm = make_user("cm@diasorin.com", customer_management=True)
    adm = make_user("adm@diasorin.com", admin=True)
    assert roles.roles_for(cm) == ["requester", "customer_management"]
    assert roles.roles_for(adm) == ["requester", "admin"]


def test_primary_role_priority(make_user):
    u = make_user("all@diasorin.com", admin=True, customer_management=True)
    cc = CostCentre.objects.create(code="CC-1", name="One")
    CostCentreApprover.objects.create(cost_centre=cc, user=u)
    assert roles.roles_for(u) == ["requester", "approver", "customer_management", "admin"]
    assert roles.primary_role(u) == "admin"
    roles.remove_role(u, AppRole.ADMIN)
    assert roles.primary_role(u) == "customer_management"
    roles.remove_role(u, AppRole.CUSTOMER_MANAGEMENT)
    assert roles.primary_role(u) == "approver"


def test_admin_role_toggles_staff_and_superuser(make_user):
    u = make_user("a@diasorin.com")
    assert (u.is_staff, u.is_superuser) == (False, False)
    roles.assign_role(u, AppRole.ADMIN)
    u.refresh_from_db()
    assert (u.is_staff, u.is_superuser) == (True, True)
    roles.remove_role(u, AppRole.ADMIN)
    u.refresh_from_db()
    assert (u.is_staff, u.is_superuser) == (False, False)


def test_other_roles_do_not_touch_flags(make_user):
    u = make_user("cm@diasorin.com")
    roles.assign_role(u, AppRole.CUSTOMER_MANAGEMENT)
    u.refresh_from_db()
    assert (u.is_staff, u.is_superuser) == (False, False)


def test_flags_follow_role_rows_created_outside_the_service(make_user):
    """Django Admin / shell create RoleAssignment rows directly; a signal keeps the flags in step."""
    u = make_user("a@diasorin.com")
    ra = RoleAssignment.objects.create(user=u, role=AppRole.ADMIN)
    u.refresh_from_db()
    assert u.is_staff and u.is_superuser
    ra.delete()
    u.refresh_from_db()
    assert not u.is_staff and not u.is_superuser


def test_seed_demo_admin_is_superuser():
    from django.core.management import call_command

    from apps.accounts.models import User

    call_command("seed_demo", verbosity=0)
    admin = User.objects.get(email="admin@diasorin.com")
    assert admin.is_staff and admin.is_superuser
    assert not User.objects.get(email="p.moretti@diasorin.com").is_staff
