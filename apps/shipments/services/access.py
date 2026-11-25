"""Who may see which request, and which events of it (REQUIREMENTS section 1 and the day-4 visibility rules).

One definition feeds the detail page (`can_view`), the approver queue and the nav counts, so they cannot
disagree. Requester: own requests. Approver: requests of their cost centres and rounds they are eligible on.
Customer management: everything that is not a Draft. Administrator: the same, plus every action.
"""

from django.db.models import Q

from apps.accounts.enums import AppRole
from apps.accounts.permissions import has_permission
from apps.accounts.services.roles import roles_for

from ..enums import EventKind, RoundState, Status
from ..models import ShipmentRequest

_SUBMITTED = ~Q(status=Status.DRAFT)


def _approver_q(user) -> Q:
    return _SUBMITTED & (
        Q(approval_rounds__eligible_approvers=user) | Q(cost_centre_ref__approvers__user=user)
    )


def approver_requests(user):
    """Requests in the approver's cost centres or with a round they are (or were) eligible on."""
    return ShipmentRequest.objects.filter(_approver_q(user)).distinct()


def pending_for(user):
    """Requests waiting for this user's decision (one open PENDING round that lists them)."""
    return ShipmentRequest.objects.filter(
        status=Status.PENDING_APPROVAL,
        approval_rounds__state=RoundState.PENDING,
        approval_rounds__eligible_approvers=user,
    ).distinct()


def queue_requests(user):
    """The approver's "all" filter: their scope plus anything they decided (an admin skip, for one)."""
    return ShipmentRequest.objects.filter(_approver_q(user) | Q(approval_rounds__decided_by=user)).distinct()


def decided_by(user):
    return ShipmentRequest.objects.filter(approval_rounds__decided_by=user).distinct()


def visible_to(user):
    q = Q(requester=user)
    if has_permission(user, "workbench", "view") or has_permission(user, "requests", "manage"):
        q |= _SUBMITTED
    else:
        q |= _approver_q(user)
    return ShipmentRequest.objects.filter(q).distinct()


def can_view(user, req: ShipmentRequest) -> bool:
    return visible_to(user).filter(pk=req.pk).exists()


def sees_internal_notes(user, req: ShipmentRequest) -> bool:
    """The requester never sees internal notes (approver / customer-management notes), unless they also
    work the request as customer management or administrator."""
    if req.requester_id != user.pk:
        return True
    roles = roles_for(user)
    return AppRole.CUSTOMER_MANAGEMENT.value in roles or AppRole.ADMIN.value in roles


def visible_events(user, req: ShipmentRequest) -> list:
    """The request's events this user may see, oldest first (uses a prefetched `events` when present)."""
    events = list(req.events.all())
    if sees_internal_notes(user, req):
        return events
    return [e for e in events if e.kind != EventKind.NOTE]
