"""Roles are computed, never stored on the user (REQUIREMENTS §1). Admin flag sync lives here too."""

from django.db import transaction

from apps.masterdata.models import CostCentreApprover
from apps.shipments.enums import RoundState
from apps.shipments.models import ApprovalRound

from ..enums import AppRole
from ..models import RoleAssignment, User

REQUESTER = AppRole.REQUESTER.value
APPROVER = AppRole.APPROVER.value
CUSTOMER_MANAGEMENT = AppRole.CUSTOMER_MANAGEMENT.value
ADMIN = AppRole.ADMIN.value

# highest priority first
PRIORITY = [ADMIN, CUSTOMER_MANAGEMENT, APPROVER, REQUESTER]


def roles_for(user: User) -> list[str]:
    """Role names for this user, in display order: requester, approver, customer_management, admin."""
    assigned = set(RoleAssignment.objects.filter(user=user).values_list("role", flat=True))
    roles = [REQUESTER]
    is_approver = (
        CostCentreApprover.objects.filter(user=user).exists()
        or ApprovalRound.objects.filter(state=RoundState.PENDING, eligible_approvers=user).exists()
    )
    if is_approver:
        roles.append(APPROVER)
    if CUSTOMER_MANAGEMENT in assigned:
        roles.append(CUSTOMER_MANAGEMENT)
    if ADMIN in assigned:
        roles.append(ADMIN)
    return roles


def primary_role(user: User) -> str:
    roles = roles_for(user)
    return next(r for r in PRIORITY if r in roles)


def sync_admin_flags(user: User) -> None:
    """is_staff / is_superuser mirror the admin role (Django Admin needs both)."""
    is_admin = RoleAssignment.objects.filter(user=user, role=ADMIN).exists()
    if user.is_staff != is_admin or user.is_superuser != is_admin:
        user.is_staff = is_admin
        user.is_superuser = is_admin
        user.save(update_fields=["is_staff", "is_superuser"])


@transaction.atomic
def assign_role(user: User, role: str, added_by: User | None = None) -> RoleAssignment:
    # Roles are recomputed on every request: adding one needs no revocation (AC-09.04.1).
    obj, _ = RoleAssignment.objects.get_or_create(user=user, role=role, defaults={"added_by": added_by})
    if role == ADMIN:
        sync_admin_flags(user)
    return obj


@transaction.atomic
def remove_role(user: User, role: str) -> None:
    # the RoleAssignment post_delete signal revokes sessions (so Django Admin removal does too)
    RoleAssignment.objects.filter(user=user, role=role).delete()
    if role == ADMIN:
        sync_admin_flags(user)
