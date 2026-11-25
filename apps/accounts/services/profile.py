"""Profile helpers shared by /api/me and the cost-centre list."""

from apps.masterdata.models import CostCentre

from ..models import User


def approval_hint(user: User, cost_centre: CostCentre | None) -> dict | None:
    """What submit would do for this cost centre: {required, why, approvers}.

    Delegates to the routing function in dry-run mode, so the hint can never disagree with submit.
    """
    from apps.shipments.services.routing import hint

    return hint(user, cost_centre)
